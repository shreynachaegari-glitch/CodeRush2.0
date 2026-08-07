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
    store_run_id: str | None = None  # the real run_id, once the run has one


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


def _investigate(client_run_id: str, question: str, pdf_path: Path | None, use_demo_assets: bool) -> None:
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
                                            "model": getattr(llm, "_model_name", "mock"),
                                            "fallback_reason": getattr(llm, "fallback_reason", None)})

        def sink(event: str, payload: dict) -> None:
            if event == "run_started":
                ch.store_run_id = payload.get("run_id")
            _publish(client_run_id, event, payload)

        real_run_id = run_investigation(
            store, llm, question, profile, emit=sink, spec_pdf=pdf_path,
            use_demo_assets=use_demo_assets,
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
    # explicit opt-in only -- the bundled satellite PDF/CSV must never attach
    # itself to a run just because no document was uploaded
    use_demo_assets = (form.get("demo") or "").strip() == "1"
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

    threading.Thread(target=_investigate, args=(client_run_id, question, pdf_path, use_demo_assets), daemon=True).start()
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
        # set only when a configured key existed but the real client still
        # failed to construct -- distinct from "no key configured at all"
        "fallback_reason": getattr(llm, "fallback_reason", None),
    })


async def list_runs(request: Request) -> JSONResponse:
    store = Store(DB_PATH)
    rows = store.read("SELECT * FROM runs ORDER BY started_at DESC LIMIT 40")
    out = []
    for r in rows:
        n = store.read_one("SELECT COUNT(*) c FROM hypotheses WHERE run_id = ?", (r["run_id"],))
        v = store.read_one(
            "SELECT content FROM memory WHERE memory_type = 'verdict' AND run_id = ? LIMIT 1", (r["run_id"],))
        out.append({
            "run_id": r["run_id"], "question": r["question"], "status": r["status"],
            "started_at": r["started_at"], "tokens": r["total_cost_tokens"],
            "hypotheses": n["c"] if n else 0,
            "verdict": json.loads(v["content"]) if v and v["content"] else None,
        })
    return JSONResponse(out)


async def strategies(request: Request) -> JSONResponse:
    store = Store(DB_PATH)
    versions = [dict(r) for r in store.read(
        "SELECT * FROM strategy_versions ORDER BY created_at DESC LIMIT 40")]
    tickets = [dict(r) for r in store.read(
        "SELECT * FROM evolution_tickets ORDER BY rowid DESC LIMIT 40")]
    rollbacks = [dict(r) for r in store.read(
        "SELECT * FROM memory WHERE memory_type = 'rollback_event' ORDER BY created_at DESC LIMIT 20")]
    return JSONResponse({"versions": versions, "tickets": tickets, "rollbacks": rollbacks})


routes = [
    Route("/", index),
    Route("/api/health", health),
    Route("/api/run", start_run, methods=["POST"]),
    Route("/api/events/{run_id}", stream),
    Route("/api/runs", list_runs),
    Route("/api/strategies", strategies),
    Mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static"),
]

app = Starlette(routes=routes)


def main() -> None:
    import uvicorn

    print("Shutdown UI  ->  http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
