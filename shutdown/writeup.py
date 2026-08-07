"""Regenerates docs/evaluation_report.md from the most recent finalized run
in shutdown.db, using metrics.render_narrative_report. Run after any demo
run so the submission doc reflects real numbers, not stale ones.

Run: python -m shutdown.writeup
"""

from __future__ import annotations

from pathlib import Path

from .db import Store
from .metrics import render_narrative_report, report_for_run

DOCS_DIR = Path(__file__).parent.parent / "docs"


def main() -> None:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    store = Store("shutdown.db")
    run = store.read_one("SELECT * FROM runs WHERE status = 'finalized' ORDER BY started_at DESC")
    if not run:
        print("no finalized run found -- run `python -m shutdown.main` first")
        return
    report = report_for_run(store, run["run_id"])
    doc = render_narrative_report(report, question=run["question"], run_id=run["run_id"])
    DOCS_DIR.mkdir(exist_ok=True)
    out_path = DOCS_DIR / "evaluation_report.md"
    out_path.write_text(doc, encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
