"""Long-term project memory: source summaries, unresolved questions, and the
run outputs (verdict/synthesis) already written elsewhere -- with real expiry.

`expires_at` existed as a schema column from the start but nothing ever set
it to anything but None, and nothing ever read it: memory never actually
expired, it just accumulated forever. This module is the one place that
computes a real expiry and the one place that enforces it, so "unresolved
questions... with expiry rules" (AE-02) means something rather than being a
column that's always null.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import Store, dumps, new_id, now

# How long each memory type stays live before prune_expired() removes it.
# An unresolved question is worth re-surfacing for a month, then it's stale --
# if nobody investigated it by then, carrying it forever just clutters memory
# with dead leads. A source summary lives longer: what a source said doesn't
# change, so it's useful as a citation lookup well after the run that found
# it. Verdicts/synthesis (written directly by main.py, not through here)
# intentionally have no expiry -- a past verdict is a historical record, not
# a lead to chase.
_DEFAULT_TTL_DAYS = {
    "unresolved_question": 30,
    "source_summary": 90,
}


def _expiry(ttl_days: int | None) -> str | None:
    if not ttl_days:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()


def remember(store: Store, memory_type: str, run_id: str | None, content: dict, provenance: str,
             ttl_days: int | None = None) -> str:
    """Write one memory row. `ttl_days` overrides the type's default; pass 0
    explicitly for "never expires" on a type that normally does."""
    if ttl_days is None:
        ttl_days = _DEFAULT_TTL_DAYS.get(memory_type)
    memory_id = new_id()
    store.insert("memory", {
        "memory_id": memory_id, "memory_type": memory_type, "run_id": run_id,
        "content": dumps(content), "provenance": provenance,
        "created_at": now(), "expires_at": _expiry(ttl_days),
    })
    return memory_id


def remember_unresolved_questions(store: Store, run_id: str, hyps: list) -> list[str]:
    """A hypothesis that ended the run neither eliminated nor survived is
    genuinely unresolved -- the evidence gathered wasn't enough to call it
    either way. Worth remembering as a lead for a follow-up run, worth
    forgetting if nobody follows up within the TTL."""
    ids = []
    for h in hyps:
        if h.status != "alive":
            continue
        ids.append(remember(store, "unresolved_question", run_id, {
            "hypothesis_id": h.hypothesis_id,
            "statement": h.statement,
            "confidence": h.confidence_current,
            "stop_condition": h.stop_condition,
        }, provenance="run_investigation"))
    return ids


def remember_source_summary(store: Store, run_id: str, question: str, sources: list[dict]) -> str | None:
    """One rollup memory per run of what was actually consulted -- grounded in
    the real `sources` rows for this run, not a description of the run."""
    if not sources:
        return None
    by_type: dict[str, int] = {}
    for s in sources:
        by_type[s["source_type"]] = by_type.get(s["source_type"], 0) + 1
    return remember(store, "source_summary", run_id, {
        "question": question,
        "source_counts": by_type,
        "locators": [s["url_or_path"] for s in sources][:12],
    }, provenance="run_investigation")


def prune_expired(store: Store) -> int:
    """Actually deletes rows whose expiry has passed. Called at the start of
    a run (see main.py) so memory doesn't grow forever with stale leads --
    without this, `expires_at` would just be a column nothing ever acted on,
    which is the exact gap this module exists to close."""
    cutoff = now()
    with store.write() as cur:
        cur.execute("DELETE FROM memory WHERE expires_at IS NOT NULL AND expires_at < ?", (cutoff,))
        return cur.rowcount


def active_memory(store: Store, memory_type: str | None = None, limit: int = 50) -> list[dict]:
    """Non-expired memory, most recent first. Expiry is enforced at read time
    too (not just via prune_expired) so a row that expired between prune
    calls is never served as if it were still live."""
    cutoff = now()
    if memory_type:
        rows = store.read(
            "SELECT * FROM memory WHERE memory_type = ? AND (expires_at IS NULL OR expires_at >= ?) "
            "ORDER BY created_at DESC LIMIT ?",
            (memory_type, cutoff, limit),
        )
    else:
        rows = store.read(
            "SELECT * FROM memory WHERE (expires_at IS NULL OR expires_at >= ?) "
            "ORDER BY created_at DESC LIMIT ?",
            (cutoff, limit),
        )
    return [dict(r) for r in rows]
