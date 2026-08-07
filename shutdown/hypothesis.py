"""Hypothesis Framer: turns a question into competing falsifiable claims.

Prompts for strict JSON so a real model's output parses reliably -- loose
"one hypothesis per line" text is fine for a hand-tuned mock, not for a real
LLM whose phrasing varies run to run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .db import Store, new_id, now
from .llm import LLMClient

FRAMER_SYSTEM = (
    "You are the Hypothesis Framer inside Shutdown, a falsification-driven research agent. "
    "Given a research question in a stated domain, produce 2-4 COMPETING hypotheses that could "
    "each independently explain or answer the question -- they must be mutually distinguishable, "
    "not restatements of each other, and each must be falsifiable (state something that, if found, "
    "would kill it, not just support it). Respond with ONLY a JSON array, no prose, no markdown "
    "fences. Each element:\n"
    '{"statement": str, "confidence_prior": float 0-1, '
    '"expected_supporting_evidence": str, "expected_contradicting_evidence": str, '
    '"stop_condition": str}'
)


@dataclass
class Hypothesis:
    hypothesis_id: str
    run_id: str
    statement: str
    confidence_prior: float
    confidence_current: float
    expected_supporting_evidence: str
    expected_contradicting_evidence: str
    stop_condition: str
    status: str = "alive"


def _extract_json_array(text: str) -> list[dict]:
    text = text.strip()
    # strip ```json ... ``` fences a real model may add despite instructions
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    # fallback: find the first [...] block
    m = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return []


def frame_hypotheses(store: Store, llm: LLMClient, run_id: str, question: str, profile: dict) -> list[Hypothesis]:
    prompt = (
        f"Domain profile: {profile.get('name', 'general')}\n"
        f"Domain keywords: {', '.join(profile.get('search_keywords', []))}\n"
        f"Question: {question}\n\n"
        "Return the JSON array now."
    )
    raw = llm.complete(prompt, system=FRAMER_SYSTEM)
    items = _extract_json_array(raw)

    if not items:
        items = [
            {
                "statement": f"Primary claim implied by: {question}",
                "confidence_prior": 0.5,
                "expected_supporting_evidence": "Independent sources/measurements consistent with the claim.",
                "expected_contradicting_evidence": "Sources reporting different outcomes under comparable conditions.",
                "stop_condition": "3 independent pieces of evidence agree, or a code-verified contradiction is found.",
            }
        ]

    hyps: list[Hypothesis] = []
    for item in items[:4]:
        prior = float(item.get("confidence_prior", 0.5))
        prior = max(0.0, min(1.0, prior))
        h = Hypothesis(
            hypothesis_id=new_id(),
            run_id=run_id,
            statement=str(item.get("statement", "")).strip() or "unspecified hypothesis",
            confidence_prior=prior,
            confidence_current=prior,
            expected_supporting_evidence=str(item.get("expected_supporting_evidence", "")).strip(),
            expected_contradicting_evidence=str(item.get("expected_contradicting_evidence", "")).strip(),
            stop_condition=str(item.get("stop_condition", "")).strip()
            or "3 independent pieces of evidence agree, or a code-verified contradiction is found.",
        )
        hyps.append(h)
        store.insert(
            "hypotheses",
            {
                "hypothesis_id": h.hypothesis_id,
                "run_id": h.run_id,
                "statement": h.statement,
                "confidence_prior": h.confidence_prior,
                "confidence_current": h.confidence_current,
                "expected_supporting_evidence": h.expected_supporting_evidence,
                "expected_contradicting_evidence": h.expected_contradicting_evidence,
                "stop_condition": h.stop_condition,
                "status": h.status,
            },
        )
    return hyps
