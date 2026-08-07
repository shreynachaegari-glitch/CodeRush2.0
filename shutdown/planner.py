"""Investigation Planner: orders evidence-gathering across hypotheses and
decides when to replan. Replanning triggers strictly on contradiction, not
on generic step failure.
"""

from __future__ import annotations

from dataclasses import dataclass

from .hypothesis import Hypothesis

MAX_ROUNDS = 3


@dataclass
class PlanStep:
    hypothesis_id: str
    query: str


def build_plan(hypotheses: list[Hypothesis], profile: dict) -> list[PlanStep]:
    """One search step per still-alive hypothesis, seeded from its statement
    plus any domain keywords in the profile (e.g. comms/satellite terms)."""
    keywords = " ".join(profile.get("search_keywords", []))
    return [
        PlanStep(hypothesis_id=h.hypothesis_id, query=f"{h.statement} {keywords}".strip())
        for h in hypotheses
        if h.status == "alive"
    ]


def should_replan(contradiction_found: bool, round_number: int) -> bool:
    if contradiction_found and round_number < MAX_ROUNDS:
        return True
    return False


def stop_condition_met(hypotheses: list[Hypothesis], round_number: int) -> bool:
    alive = [h for h in hypotheses if h.status == "alive"]
    if not alive:
        return True
    if round_number >= MAX_ROUNDS:
        return True
    return any(h.confidence_current >= 0.85 for h in alive)
