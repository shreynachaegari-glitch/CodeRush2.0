"""Evidence graph: typed edges (supports/weakens/refutes/unknown) linking a
hypothesis to a source, each carrying confidence, timestamp, and how the
evidence was derived.
"""

from __future__ import annotations

from .contradiction import content_hash
from .db import Store, new_id, now

RELATIONS = ("supports", "weakens", "refutes", "unknown")

# Confidence-update rule: explicit and small, not a hidden heuristic.
# A refuting piece of evidence pulls confidence down hard; supporting
# evidence nudges it up; weakening evidence nudges it down softly.
_DELTA = {"supports": +0.12, "weakens": -0.08, "refutes": -0.35, "unknown": 0.0}


def add_source(store: Store, run_id: str, url_or_path: str, source_type: str, content: str,
                injection_flagged: bool, injection_detail: str) -> str:
    source_id = new_id()
    store.insert(
        "sources",
        {
            "source_id": source_id,
            "run_id": run_id,
            "url_or_path": url_or_path,
            "fetched_at": now(),
            "source_type": source_type,
            "content_hash": content_hash(content),
            "injection_flagged": int(injection_flagged),
            "injection_detail": injection_detail,
        },
    )
    return source_id


def add_evidence(store: Store, hypothesis_id: str, source_id: str, relation: str,
                  contradiction_class: str | None, confidence: float, transformation: str) -> str:
    assert relation in RELATIONS
    evidence_id = new_id()
    store.insert(
        "evidence",
        {
            "evidence_id": evidence_id,
            "hypothesis_id": hypothesis_id,
            "source_id": source_id,
            "relation": relation,
            "contradiction_class": contradiction_class,
            "confidence": confidence,
            "transformation": transformation,
            "timestamp": now(),
        },
    )
    return evidence_id


def update_confidence(store: Store, hypothesis_id: str, relation: str, deltas: dict | None = None) -> float:
    """`deltas` lets the active Strategy Evaluator version override the default
    confidence-update rule at runtime; falls back to the built-in rule if omitted."""
    deltas = deltas or _DELTA
    row = store.read_one("SELECT confidence_current FROM hypotheses WHERE hypothesis_id = ?", (hypothesis_id,))
    current = row["confidence_current"] if row else 0.5
    new_conf = round(max(0.0, min(1.0, current + deltas.get(relation, 0.0))), 6)
    status = "eliminated" if new_conf <= 0.15 else ("survived" if new_conf >= 0.85 else "alive")
    store.update("hypotheses", "hypothesis_id", hypothesis_id, {"confidence_current": new_conf, "status": status})
    return new_conf


def graph_for_run(store: Store, run_id: str) -> dict:
    hyps = store.read("SELECT * FROM hypotheses WHERE run_id = ?", (run_id,))
    out = {"run_id": run_id, "hypotheses": []}
    for h in hyps:
        ev_rows = store.read(
            "SELECT e.*, s.url_or_path, s.source_type FROM evidence e "
            "JOIN sources s ON e.source_id = s.source_id WHERE e.hypothesis_id = ? ORDER BY e.timestamp",
            (h["hypothesis_id"],),
        )
        out["hypotheses"].append(
            {
                "hypothesis_id": h["hypothesis_id"],
                "statement": h["statement"],
                "confidence": h["confidence_current"],
                "status": h["status"],
                "evidence": [dict(e) for e in ev_rows],
            }
        )
    return out
