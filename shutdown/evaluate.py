"""Standalone reproducible evaluation runner.

Scores the currently-active strategy against the held-out labeled set
without running a full LLM-costing investigation -- satisfies the
handbook's "evaluation report" requirement with something that can be
re-run for free, as often as needed, independent of a live API key.

Run: python -m shutdown.evaluate
"""

from __future__ import annotations

import json
from pathlib import Path

from .db import Store
from .strategy import DEFAULT_STRATEGY, active_strategy, load_held_out_set, score_strategy

HELD_OUT_PATH = Path(__file__).parent / "held_out_set.json"


def evaluate(db_path: str = "shutdown.db") -> dict:
    store = Store(db_path)
    held_out = load_held_out_set(HELD_OUT_PATH)
    active = active_strategy(store)

    default_result = score_strategy(DEFAULT_STRATEGY, held_out)
    active_result = score_strategy(active["strategy"], held_out)

    return {
        "held_out_cases": len(held_out),
        "default_strategy": default_result,
        "active_strategy": {"version_id": active["version_id"], **active_result},
        "active_vs_default_delta": round(active_result["accuracy"] - default_result["accuracy"], 3),
    }


def main() -> None:
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result = evaluate()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
