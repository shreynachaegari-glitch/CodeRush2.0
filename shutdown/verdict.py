"""Verdict synthesis and the Teacher (self-critique) module.

Two things the design called for that the pipeline previously skipped:

1. **A verdict.** The run used to end with a set of confidence numbers and no
   answer. Confidence is not a conclusion -- a reader wants "the claim holds,
   here is why, here is what would still overturn it". `synthesize_verdict`
   reads the finished evidence graph and states that, ranking each hypothesis
   as supported / falsified / undetermined with the reason and its citations.

2. **A Teacher.** The evolution ticket used to be hardcoded -- the same
   sentence every run, regardless of what actually happened. That is not
   self-improvement, it is a fixture. `critique_run` shows the model what the
   run actually did (weak evidence, refused sources, unresolved contradictions,
   dead ends) and asks it to name the real failure and propose a parameter
   change. The proposal is still bounded by the scope guard in strategy.py and
   still has to beat the held-out set before anything is promoted.

Both degrade to a deterministic fallback if the model returns unusable JSON,
so a run always produces *something* honest rather than raising.
"""

from __future__ import annotations

import json
import re

from .db import Store
from .evidence import graph_for_run
from .llm import LLMClient

VERDICT_SYSTEM = (
    "You are the Verdict writer inside Shutdown, a falsification-driven research agent. "
    "You are given a research question and the full evidence graph from an investigation: "
    "competing hypotheses, their final confidence, and every piece of evidence with its "
    "relation (supports/weakens/refutes/unknown) and source. "
    "Judge what the evidence actually shows. A hypothesis with only weak or irrelevant "
    "evidence is UNDETERMINED, not supported -- absence of contradiction is not proof. "
    "Be willing to say the investigation was inconclusive; that is a valid scientific result "
    "and far better than overclaiming. Never invent evidence or sources not listed. "
    "Respond with ONLY JSON, no prose, no markdown fences:\n"
    '{"answer": str (2-3 sentences answering the question directly), '
    '"confidence": "high"|"moderate"|"low", '
    '"rulings": [{"hypothesis_id": str, "ruling": "supported"|"falsified"|"undetermined", '
    '"why": str (1 sentence citing what decided it)}], '
    '"what_would_change_it": str (1 sentence: the evidence that would overturn this), '
    '"caveats": str (1 sentence on the weakest part of this investigation)}'
)

TEACHER_SYSTEM = (
    "You are the Teacher inside Shutdown, a self-evolving research agent. You review a "
    "COMPLETED investigation and diagnose how the agent's own strategy let it down -- not "
    "what the answer was, but how the process failed. Look for: evidence that was weak or "
    "off-topic, sources refused or unusable, hypotheses that never moved, contradictions "
    "left unresolved, confidence that swung too hard or not hard enough. "
    "Then propose ONE concrete change to the agent's numeric parameters. "
    "You may ONLY propose changes to these fields:\n"
    '  confidence_deltas: {supports, weakens, refutes, unknown}  (floats, -1..1)\n'
    "  retrieval_diversity: float 0..1\n"
    "You may NOT propose changes to approval policy, sandbox limits, permissions, or "
    "network access -- such proposals are auto-rejected. "
    "Be specific and quantitative. Respond with ONLY JSON, no prose, no fences:\n"
    '{"failure_description": str, "root_cause": str, "hypothesis": str, '
    '"proposed_diff": {"confidence_deltas": {...}} or {"retrieval_diversity": float}, '
    '"expected_gain": str, "risk": str}'
)


SYNTHESIS_SYSTEM = (
    "You are the Synthesist inside Shutdown, a falsification-driven research agent. "
    "The investigation is finished: some hypotheses survived, some were falsified. Your job "
    "is not to summarise it again -- it is to propose what to DO about it. Generate 2-3 "
    "concrete, original proposals that are consistent with every surviving piece of evidence "
    "and that would not be falsified by the evidence that killed the losing hypotheses.\n"
    "Rules: each proposal must be specific enough to act on (a mechanism, a parameter, an "
    "experiment -- not 'do more research'). Each must say which evidence constrains it and "
    "how it could be tested or falsified. Ground every proposal in the evidence given; if the "
    "evidence is too thin to support any proposal, say so in `limitation` and return fewer. "
    "Do not invent sources. Respond with ONLY JSON, no prose, no fences:\n"
    '{"proposals": [{"title": str, "proposal": str (2-3 sentences), '
    '"grounded_in": str (which evidence constrains it), '
    '"how_to_test": str (the experiment or measurement that would falsify it), '
    '"novelty": "incremental"|"substantive" }], '
    '"limitation": str (1 sentence on what the evidence could not support)}'
)


def _parse_json(raw: str) -> dict:
    """Models wrap JSON in fences despite instructions; recover the object."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _evidence_digest(store: Store, run_id: str) -> tuple[list[dict], dict]:
    """Flatten the graph into something a model can read, plus counters the
    deterministic fallbacks use."""
    graph = graph_for_run(store, run_id)
    stats = {"supports": 0, "refutes": 0, "weakens": 0, "unknown": 0,
             "refused": 0, "unusable": 0, "total": 0}
    digest = []
    for h in graph["hypotheses"]:
        items = []
        for e in h["evidence"]:
            rel = e["relation"]
            stats[rel] = stats.get(rel, 0) + 1
            stats["total"] += 1
            note = (e["transformation"] or "")
            if "injection detected" in note:
                stats["refused"] += 1
            if "no usable content" in note:
                stats["unusable"] += 1
            items.append({
                "relation": rel,
                "source": e["url_or_path"],
                "source_type": e["source_type"],
                "weight": round(e["confidence"], 2),
                "note": note[:180],
            })
        digest.append({
            "hypothesis_id": h["hypothesis_id"],
            "statement": h["statement"],
            "final_confidence": round(h["confidence"], 3),
            "status": h["status"],
            "evidence": items,
        })
    return digest, stats


# ── verdict ──────────────────────────────────────────────────────────────

def _fallback_verdict(digest: list[dict]) -> dict:
    """Deterministic verdict when the model is unavailable or returns junk.
    Deliberately conservative: it rules on confidence alone and says so."""
    rulings = []
    for h in digest:
        supports = sum(1 for e in h["evidence"] if e["relation"] == "supports")
        if h["status"] == "eliminated":
            ruling = "falsified"
        elif h["status"] == "survived" and supports >= 2:
            ruling = "supported"
        else:
            ruling = "undetermined"
        rulings.append({
            "hypothesis_id": h["hypothesis_id"], "ruling": ruling,
            "why": f"final confidence {h['final_confidence']:.2f} from {len(h['evidence'])} evidence item(s)",
        })
    lead = max(digest, key=lambda h: h["final_confidence"], default=None)
    return {
        "answer": (f"Leading hypothesis: {lead['statement']}" if lead else "No hypotheses were framed."),
        "confidence": "low",
        "rulings": rulings,
        "what_would_change_it": "Independent measurement under the same stated conditions.",
        "caveats": "Generated without model synthesis — rulings reflect confidence arithmetic only.",
        "synthesized": False,
    }


def synthesize_verdict(store: Store, llm: LLMClient, run_id: str, question: str) -> dict:
    digest, _ = _evidence_digest(store, run_id)
    if not digest:
        return _fallback_verdict(digest)

    prompt = (
        f"Research question: {question}\n\n"
        f"Evidence graph:\n{json.dumps(digest, indent=1)[:9000]}\n\n"
        "Return the JSON verdict now."
    )
    parsed = _parse_json(llm.complete(prompt, system=VERDICT_SYSTEM))
    if not parsed.get("answer") or not isinstance(parsed.get("rulings"), list):
        return _fallback_verdict(digest)

    # keep only rulings that name a hypothesis this run actually had
    valid = {h["hypothesis_id"] for h in digest}
    parsed["rulings"] = [r for r in parsed["rulings"] if r.get("hypothesis_id") in valid]
    if not parsed["rulings"]:
        return _fallback_verdict(digest)
    parsed["synthesized"] = True
    return parsed


# ── synthesis (original proposals) ───────────────────────────────────────

def propose_solutions(store: Store, llm: LLMClient, run_id: str, question: str,
                      final_verdict: dict) -> dict:
    """Generate original, evidence-constrained proposals.

    Judging claims is not the same as producing an idea. This is the step that
    proposes something new -- but bounded: every proposal must be consistent
    with the surviving evidence and must state how it could be falsified, which
    is the same standard the agent held the hypotheses to. Returns an empty
    list rather than inventing something when the evidence is too thin.
    """
    digest, stats = _evidence_digest(store, run_id)
    if not digest:
        return {"proposals": [], "limitation": "No evidence was gathered.", "synthesized": False}

    prompt = (
        f"Research question: {question}\n\n"
        f"Verdict: {json.dumps({k: v for k, v in final_verdict.items() if k != 'rulings'})[:1200]}\n\n"
        f"Evidence graph:\n{json.dumps(digest, indent=1)[:7000]}\n\n"
        "Return the JSON proposals now."
    )
    parsed = _parse_json(llm.complete(prompt, system=SYNTHESIS_SYSTEM))
    proposals = parsed.get("proposals")
    if not isinstance(proposals, list) or not proposals:
        return {
            "proposals": [],
            "limitation": ("Evidence was too thin or too weakly connected to support an "
                           "original proposal; the agent declines to speculate."),
            "synthesized": False,
        }

    clean = []
    for p in proposals[:3]:
        if not isinstance(p, dict) or not p.get("proposal"):
            continue
        clean.append({
            "title": str(p.get("title", "Untitled"))[:120],
            "proposal": str(p["proposal"])[:600],
            "grounded_in": str(p.get("grounded_in", ""))[:300],
            "how_to_test": str(p.get("how_to_test", ""))[:300],
            "novelty": p.get("novelty") if p.get("novelty") in ("incremental", "substantive") else "incremental",
        })
    return {
        "proposals": clean,
        "limitation": str(parsed.get("limitation", ""))[:300],
        "synthesized": bool(clean),
    }


# ── teacher ──────────────────────────────────────────────────────────────

_ALLOWED_DIFF_KEYS = {"confidence_deltas", "retrieval_diversity"}
_ALLOWED_DELTAS = {"supports", "weakens", "refutes", "unknown"}


def _sanitize_diff(diff: dict) -> dict | None:
    """Structural validation before the proposal reaches the policy guard.
    The guard in strategy.py rejects out-of-scope *fields*; this additionally
    rejects malformed values, so a hallucinated diff can't produce a version
    whose numbers are strings or wildly out of range."""
    if not isinstance(diff, dict) or not diff:
        return None
    clean: dict = {}
    for k, v in diff.items():
        if k not in _ALLOWED_DIFF_KEYS:
            return None  # out of scope -- let it be rejected, don't silently drop
        if k == "confidence_deltas":
            if not isinstance(v, dict):
                return None
            deltas = {}
            for dk, dv in v.items():
                if dk not in _ALLOWED_DELTAS or not isinstance(dv, (int, float)):
                    return None
                deltas[dk] = max(-1.0, min(1.0, float(dv)))
            if not deltas:
                return None
            clean[k] = deltas
        else:
            if not isinstance(v, (int, float)):
                return None
            clean[k] = max(0.0, min(1.0, float(v)))
    return clean


def _fallback_ticket(stats: dict) -> dict:
    """Deterministic critique derived from what measurably happened, so even
    the fallback is about this run rather than a fixed sentence."""
    if stats["unusable"] or stats["unknown"]:
        return {
            "failure_description": (
                f"{stats['unknown']} of {stats['total']} evidence items were unusable "
                f"({stats['unusable']} fetches returned nothing readable)."),
            "root_cause": "Retrieval spent effort on sources that could not be read at all.",
            "hypothesis": "Raising retrieval diversity surfaces alternative sources when one fails.",
            "proposed_diff": {"retrieval_diversity": 0.85},
            "expected_gain": "Fewer dead-end fetches per round",
            "risk": "More diverse sources may be less directly on-topic",
        }
    return {
        "failure_description": (
            f"No hypothesis was eliminated across {stats['total']} evidence items; "
            f"{stats['supports']} supported and {stats['refutes']} refuted."),
        "root_cause": "Confidence moves too slowly for weak contradictory evidence to resolve anything.",
        "hypothesis": "A larger 'weakens' penalty separates dying claims from live ones sooner.",
        "proposed_diff": {"confidence_deltas": {"weakens": -0.10}},
        "expected_gain": "Higher hypothesis-elimination rate at equal accuracy",
        "risk": "May over-penalize claims that later recover",
    }


def critique_run(store: Store, llm: LLMClient, run_id: str, question: str) -> dict:
    """The Teacher: diagnose this run's process failure and propose a fix.

    Returns a ticket dict ready for `strategy.raise_ticket`. Falls back to a
    measured, deterministic critique rather than raising -- the meta plane
    must never take the run down with it.
    """
    digest, stats = _evidence_digest(store, run_id)
    fallback = _fallback_ticket(stats)
    if not digest:
        return {**fallback, "authored_by": "fallback"}

    prompt = (
        f"Research question: {question}\n\n"
        f"Evidence tallies: {json.dumps(stats)}\n\n"
        f"What the run did:\n{json.dumps(digest, indent=1)[:7000]}\n\n"
        "Diagnose the strategy failure and return the JSON ticket now."
    )
    parsed = _parse_json(llm.complete(prompt, system=TEACHER_SYSTEM))

    diff = _sanitize_diff(parsed.get("proposed_diff", {}))
    if not parsed.get("failure_description") or diff is None:
        return {**fallback, "authored_by": "fallback"}

    return {
        "failure_description": str(parsed["failure_description"])[:400],
        "root_cause": str(parsed.get("root_cause", ""))[:400] or fallback["root_cause"],
        "hypothesis": str(parsed.get("hypothesis", ""))[:400] or fallback["hypothesis"],
        "proposed_diff": diff,
        "expected_gain": str(parsed.get("expected_gain", ""))[:200] or fallback["expected_gain"],
        "risk": str(parsed.get("risk", ""))[:200] or fallback["risk"],
        "authored_by": "teacher",
    }
