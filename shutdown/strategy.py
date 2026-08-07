"""Strategy Evaluator: the meta-agent. The only component allowed to change
the parameters the control plane uses (currently: the confidence-update
deltas in evidence.py, and retrieval_diversity used by search reranking).

Evaluation is deterministic, not LLM-judged -- avoids the self-grading bias
where the same model that proposes a strategy also scores it. Score = exact
match against pre-labeled held-out outcomes.

Scope guard: self-evolution here only ever touches config numbers
(confidence deltas / retrieval weighting). It can never rewrite the trusted
control flow (approval gates, the auto-reject policy check itself, or model
weights). A ticket whose diff touches a disallowed field is auto-rejected
and logged -- no approval requested, because that's a scope violation, not
a judgment call.
"""

from __future__ import annotations

import json
from pathlib import Path

from .db import Store, dumps, new_id, now
from .evidence import classify as _classify

DISALLOWED_DIFF_FIELDS = {
    "permissions", "network_allowlist", "trusted_control", "approval_policy", "sandbox_limits",
}

DEFAULT_STRATEGY = {
    "confidence_deltas": {"supports": 0.12, "weakens": -0.08, "refutes": -0.35, "unknown": 0.0},
    "retrieval_diversity": 0.7,
}


def _deepcopy(obj: dict) -> dict:
    """Strategies are plain JSON-shaped dicts, so a round-trip is a correct
    (and dependency-free) deep copy."""
    return json.loads(json.dumps(obj))


def load_held_out_set(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _apply_delta(confidence: float, relation: str, deltas: dict) -> float:
    return max(0.0, min(1.0, confidence + deltas.get(relation, 0.0)))


def score_strategy(strategy: dict, held_out_set: list[dict]) -> dict:
    """Deterministic pass over labeled cases. Each case: a starting confidence,
    a sequence of evidence relations applied in order, and an expected final
    status. No LLM involved in grading -- pure arithmetic + string compare.
    """
    deltas = strategy.get("confidence_deltas", DEFAULT_STRATEGY["confidence_deltas"])
    correct = 0
    for case in held_out_set:
        conf = case["start_confidence"]
        for relation in case["evidence_sequence"]:
            conf = _apply_delta(conf, relation, deltas)
        predicted = _classify(conf)
        if predicted == case["expected_status"]:
            correct += 1
    n = max(1, len(held_out_set))
    return {
        "accuracy": correct / n,
        "n_cases": len(held_out_set),
        "n_correct": correct,
    }


def is_policy_violation(diff: dict) -> bool:
    return any(field in DISALLOWED_DIFF_FIELDS for field in diff.keys())


def raise_ticket(store: Store, *, run_id: str, failure_description: str, root_cause: str,
                  hypothesis: str, proposed_diff: dict, expected_gain: str, risk: str,
                  eval_metric: str = "held_out_accuracy") -> str:
    ticket_id = new_id()
    store.insert(
        "evolution_tickets",
        {
            "ticket_id": ticket_id,
            "raised_from_run_id": run_id,
            "failure_description": failure_description,
            "root_cause": root_cause,
            "hypothesis": hypothesis,
            "proposed_version_id": None,
            "expected_gain": expected_gain,
            "risk": risk,
            "eval_metric": eval_metric,
            "held_out_result_before": None,
            "held_out_result_after": None,
            "decision": "pending",
            "cost_tokens_spent": 0,
        },
    )

    if is_policy_violation(proposed_diff):
        store.update(
            "evolution_tickets", "ticket_id", ticket_id,
            {"decision": "auto_rejected_scope_violation"},
        )
        return ticket_id

    current = _current_active_strategy(store)
    version_id = new_id()
    store.insert(
        "strategy_versions",
        {
            "version_id": version_id,
            "parent_version_id": current["version_id"],
            "created_at": now(),
            "diff_json": dumps(proposed_diff),
            "status": "proposed",
        },
    )
    store.update("evolution_tickets", "ticket_id", ticket_id, {"proposed_version_id": version_id})
    return ticket_id


def evaluate_ticket(store: Store, ticket_id: str, held_out_set: list[dict]) -> dict:
    ticket = store.read_one("SELECT * FROM evolution_tickets WHERE ticket_id = ?", (ticket_id,))
    if ticket["decision"] == "auto_rejected_scope_violation":
        return {"decision": "auto_rejected_scope_violation"}

    current = _current_active_strategy(store)
    proposed_version = store.read_one(
        "SELECT * FROM strategy_versions WHERE version_id = ?", (ticket["proposed_version_id"],)
    )
    proposed_strategy = _merge_diff(current["strategy"], json.loads(proposed_version["diff_json"]))

    before = score_strategy(current["strategy"], held_out_set)
    after = score_strategy(proposed_strategy, held_out_set)

    store.update(
        "evolution_tickets", "ticket_id", ticket_id,
        {"held_out_result_before": dumps(before), "held_out_result_after": dumps(after)},
    )
    return {"before": before, "after": after, "improved": after["accuracy"] > before["accuracy"]}


def finalize_ticket(store: Store, ticket_id: str, *, approved: bool) -> None:
    """Promotes the proposed version to active (demoting the previous active
    version to 'superseded' so exactly one version is ever active -- but kept
    queryable, which is what makes rollback possible), or marks it rejected."""
    ticket = store.read_one("SELECT * FROM evolution_tickets WHERE ticket_id = ?", (ticket_id,))
    decision = "accepted" if approved else "rejected"
    store.update("evolution_tickets", "ticket_id", ticket_id, {"decision": decision})
    if not ticket["proposed_version_id"]:
        return
    if approved:
        prev_active = store.read_one("SELECT version_id FROM strategy_versions WHERE status = 'active'")
        if prev_active:
            store.update("strategy_versions", "version_id", prev_active["version_id"], {"status": "superseded"})
        store.update("strategy_versions", "version_id", ticket["proposed_version_id"], {"status": "active"})
    else:
        store.update("strategy_versions", "version_id", ticket["proposed_version_id"], {"status": "rejected"})


def rollback(store: Store, to_version_id: str, *, run_id: str | None = None, reason: str = "") -> None:
    """Explicit rollback: reactivate a prior (superseded) version. Logged into
    `memory` (memory_type='rollback_event') so metrics.py can compute a
    rollback-frequency count without a dedicated table. `run_id` attributes
    the event to the run that triggered it -- without it the metric can only
    report a lifetime total, which reads as "this run rolled back N times"."""
    prev_active = store.read_one("SELECT version_id FROM strategy_versions WHERE status = 'active'")
    if prev_active:
        store.update("strategy_versions", "version_id", prev_active["version_id"], {"status": "superseded"})
    store.update("strategy_versions", "version_id", to_version_id, {"status": "active"})
    store.insert(
        "memory",
        {
            "memory_id": new_id(),
            "memory_type": "rollback_event",
            "run_id": run_id,
            "content": dumps({"rolled_back_to": to_version_id, "from": prev_active["version_id"] if prev_active else None, "reason": reason}),
            "provenance": "strategy.rollback",
            "created_at": now(),
            "expires_at": None,
        },
    )


def _resolve_strategy(store: Store, version_id: str) -> dict:
    """Walk the parent chain root-to-leaf, replaying each version's diff onto
    DEFAULT_STRATEGY. Needed so an approved change actually changes what
    later evaluations score against, instead of every version silently
    resolving back to the same defaults."""
    chain = []
    vid = version_id
    seen = set()
    while vid and vid not in seen:
        seen.add(vid)
        row = store.read_one("SELECT * FROM strategy_versions WHERE version_id = ?", (vid,))
        if not row:
            break
        chain.append(row)
        vid = row["parent_version_id"]
    chain.reverse()  # root first

    strategy = _deepcopy(DEFAULT_STRATEGY)
    for row in chain:
        strategy = _merge_diff(strategy, json.loads(row["diff_json"]))
    return strategy


def active_strategy(store: Store) -> dict:
    """The active version id plus its fully-resolved parameters. This is how
    the control plane gets the confidence deltas it should score evidence
    with -- the one point where the meta plane's output actually reaches it."""
    return _current_active_strategy(store)


def active_version_id(store: Store) -> str:
    """Public accessor -- callers that just need to remember "the version
    active right now" (e.g. to roll back to it later) shouldn't reach into
    the private helper."""
    return _current_active_strategy(store)["version_id"]


def _current_active_strategy(store: Store) -> dict:
    row = store.read_one("SELECT * FROM strategy_versions WHERE status = 'active' ORDER BY created_at DESC")
    if not row:
        version_id = new_id()
        store.insert(
            "strategy_versions",
            {
                "version_id": version_id,
                "parent_version_id": None,
                "created_at": now(),
                "diff_json": dumps({}),
                "status": "active",
            },
        )
        # a copy, not DEFAULT_STRATEGY itself -- callers mutating the returned
        # dict must not be able to edit the module-level baseline
        return {"version_id": version_id, "strategy": _deepcopy(DEFAULT_STRATEGY)}
    return {"version_id": row["version_id"], "strategy": _resolve_strategy(store, row["version_id"])}


def _merge_diff(base: dict, diff: dict) -> dict:
    merged = _deepcopy(base)
    for k, v in diff.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged
