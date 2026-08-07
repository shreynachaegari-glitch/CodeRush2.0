"""Investigation Planner: orders evidence-gathering across hypotheses and
decides when to replan. Replanning triggers strictly on contradiction, not
on generic step failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .hypothesis import Hypothesis

MAX_ROUNDS = 3

# How many terms lifted from the hypothesis go into the search query. A real
# model states a hypothesis as a full sentence; pasting all ~200 characters
# into a keyword search returns near-random pages (that was the actual root
# cause of the "noisy web evidence" problem, not the search engine).
QUERY_TERM_LIMIT = 8

# Ordinary English that carries no retrieval signal. Deliberately short and
# domain-agnostic -- a real stopword corpus is a dependency we don't need.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those is are was were be been being
of in on at to for from by with within without into over under across
it its their his her they them we our you your as so such not no
does do did doing has have had having will would can could may might must shall should
which who whom whose what when where why how
once also both each any all more most some very much many one two
above below between during before after while until since
""".split())

# Words that describe the *shape* of a hypothesis rather than its subject.
# They're what makes two competing hypotheses read differently while both
# being about the same thing -- useless as retrieval terms.
_HEDGE_WORDS = frozenset("""
because due caused causes causing result results resulting leads lead
remains remain stays stay keeps keep maintains maintain
exceeds exceed fails fail prevents prevent ensures ensure
regardless independently instead rather significantly substantially
""".split())


@dataclass
class PlanStep:
    hypothesis_id: str
    query: str


def build_query(statement: str, profile: dict, term_limit: int = QUERY_TERM_LIMIT) -> str:
    """Distill a hypothesis sentence into a keyword query.

    Keeps domain keywords from the profile (they anchor the search in the
    right field) and the most distinctive content words from the statement,
    in their original order. Numbers and units are kept -- "40%" or "12 GHz"
    are exactly the terms that find a contradicting measurement.
    """
    seen: set[str] = set()
    terms: list[str] = []

    for raw in re.findall(r"[A-Za-z][A-Za-z0-9\-]*|\d+(?:\.\d+)?%?", statement):
        low = raw.lower()
        if low in seen or low in _STOPWORDS or low in _HEDGE_WORDS:
            continue
        if raw[0].isalpha() and len(raw) < 3:
            continue  # drop stray initials/short fragments, keep numerics
        seen.add(low)
        terms.append(raw)
        if len(terms) >= term_limit:
            break

    keywords = [k for k in profile.get("search_keywords", []) if k.lower() not in seen]
    return " ".join(terms + keywords[:3]).strip()


def build_plan(hypotheses: list[Hypothesis], profile: dict) -> list[PlanStep]:
    """One search step per still-alive hypothesis, built from the distinctive
    terms in its statement plus domain keywords from the profile."""
    return [
        PlanStep(hypothesis_id=h.hypothesis_id, query=build_query(h.statement, profile))
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
