"""Web UI server for Shutdown.

Deliberately dependency-light: Starlette + uvicorn (both already present as
transitive deps) rather than adding a framework, and a hand-written frontend
served as static files rather than a build toolchain. Nothing here is fetched
from a CDN at runtime -- a demo shouldn't depend on venue wifi.

The investigation itself is synchronous and blocking, so each run executes on
a worker thread and publishes events into a queue that the SSE endpoint
drains. That keeps `run_investigation` free of any async plumbing: it just
calls `emit(...)`.

Run: python -m shutdown.web   (then open http://127.0.0.1:8000)
"""

from __future__ import annotations

import asyncio
import json
import queue
import tempfile
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .db import Store
from .llm import get_default_client
from .main import PROFILE_PATH, _load_dotenv, run_investigation
from .metrics import report_for_run
from .trace import build_research_package, render_trace_html

STATIC_DIR = Path(__file__).parent / "static"
OUTPUT_DIR = Path("shutdown_output")
DB_PATH = "shutdown.db"

_SENTINEL = object()


@dataclass
class RunChannel:
    """Live event buffer for one run. `history` lets a client that connects
    late (or reconnects) replay what it missed instead of showing a blank
    pipeline."""
    events: queue.Queue = field(default_factory=queue.Queue)
    history: list = field(default_factory=list)
    done: bool = False
    error: str | None = None


_channels: dict[str, RunChannel] = {}
_channels_lock = threading.Lock()


def _publish(run_id: str, event: str, payload: dict) -> None:
    with _channels_lock:
        ch = _channels.get(run_id)
    if ch is None:
        return
    item = {"event": event, "data": payload}
    ch.history.append(item)
    ch.events.put(item)


def _investigate(client_run_id: str, question: str, pdf_path: Path | None) -> None:
    """Runs on a worker thread. Every exit path must mark the channel done, or
    the browser sits on an open stream waiting for events that never come."""
    with _channels_lock:
        ch = _channels[client_run_id]
    try:
        _load_dotenv()
        store = Store(DB_PATH)
        llm = get_default_client()
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

        _publish(client_run_id, "backend", {"llm": type(llm).__name__,
                                            "model": getattr(llm, "_model_name", "mock")})

        real_run_id = run_investigation(
            store, llm, question, profile,
            emit=lambda e, p: _publish(client_run_id, e, p),
            spec_pdf=pdf_path,
        )

        report = report_for_run(store, real_run_id)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / f"trace_{real_run_id}.html").write_text(
            render_trace_html(store, real_run_id), encoding="utf-8")
        build_research_package(store, real_run_id, OUTPUT_DIR,
                               extra_files={"evaluation_report.json": report})
        _publish(client_run_id, "package", {"run_id": real_run_id})
    except Exception as exc:  # surfaced in the UI rather than only in the console
        ch.error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        _publish(client_run_id, "error", {"message": ch.error})
    finally:
        ch.done = True
        ch.events.put(_SENTINEL)


async def start_run(request: Request) -> JSONResponse:
    form = await request.form()
    question = (form.get("question") or "").strip()
    if not question:
        return JSONResponse({"error": "A research question is required."}, status_code=400)

    pdf_path = None
    upload = form.get("document")
    if upload is not None and getattr(upload, "filename", ""):
        if not upload.filename.lower().endswith(".pdf"):
            return JSONResponse({"error": "Only PDF documents are supported."}, status_code=400)
        tmp_dir = Path(tempfile.mkdtemp(prefix="shutdown_upload_"))
        pdf_path = tmp_dir / Path(upload.filename).name
        pdf_path.write_bytes(await upload.read())

    from .db import new_id
    client_run_id = new_id()
    with _channels_lock:
        _channels[client_run_id] = RunChannel()

    threading.Thread(target=_investigate, args=(client_run_id, question, pdf_path), daemon=True).start()
    return JSONResponse({"run_id": client_run_id, "document": pdf_path.name if pdf_path else None})


async def stream(request: Request):
    from sse_starlette.sse import EventSourceResponse

    client_run_id = request.path_params["run_id"]
    with _channels_lock:
        ch = _channels.get(client_run_id)
    if ch is None:
        return JSONResponse({"error": "unknown run"}, status_code=404)

    async def gen():
        # replay anything that landed before this stream opened
        for item in list(ch.history):
            yield {"event": item["event"], "data": json.dumps(item["data"])}
        replayed = len(ch.history)

        while True:
            if await request.is_disconnected():
                break
            try:
                item = await asyncio.to_thread(ch.events.get, True, 0.5)
            except queue.Empty:
                continue
            if item is _SENTINEL:
                yield {"event": "close", "data": json.dumps({"error": ch.error})}
                break
            # history replay above may already have covered this item
            if replayed:
                replayed -= 1
                continue
            yield {"event": item["event"], "data": json.dumps(item["data"])}

    return EventSourceResponse(gen())


async def index(request: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


async def health(request: Request) -> JSONResponse:
    _load_dotenv()
    llm = get_default_client()
    return JSONResponse({
        "backend": type(llm).__name__,
        "model": getattr(llm, "_model_name", "mock"),
        "live": type(llm).__name__ != "MockLLM",
    })


routes = [
    Route("/", index),
    Route("/api/health", health),
    Route("/api/run", start_run, methods=["POST"]),
    Route("/api/events/{run_id}", stream),
    Mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static"),
]

app = Starlette(routes=routes)


def main() -> None:
    import uvicorn

    print("Shutdown UI  ->  http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
