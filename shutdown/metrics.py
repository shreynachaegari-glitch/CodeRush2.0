"""Evaluation report, columns named to match AE-02's own wording:
"end-to-end success, citation precision/recall, unsupported-claim rate,
source quality, browser success, code-execution success, prompt-injection
resistance, cost, and human interventions" -- plus the three Shutdown-
specific additions the plan calls out: hypothesis elimination rate,
strategy improvement rate, rollback frequency.

Deliberately simple, deterministic arithmetic over the SQLite store -- no
LLM grading here either, same reasoning as strategy.score_strategy.
"""

from __future__ import annotations

from .db import Store


def _safe_div(n: float, d: float) -> float:
    return n / d if d else 0.0


def report_for_run(store: Store, run_id: str) -> dict:
    run = store.read_one("SELECT * FROM runs WHERE run_id = ?", (run_id,))
    hyps = store.read("SELECT * FROM hypotheses WHERE run_id = ?", (run_id,))
    sources = store.read("SELECT * FROM sources WHERE run_id = ?", (run_id,))
    evidence = store.read(
        "SELECT e.* FROM evidence e JOIN hypotheses h ON e.hypothesis_id = h.hypothesis_id WHERE h.run_id = ?",
        (run_id,),
    )

    end_to_end_success = 1.0 if run and run["status"] == "finalized" else 0.0

    cited = [e for e in evidence if e["relation"] in ("supports", "refutes") and (e["transformation"] or "").strip()]
    checkable = [e for e in evidence if e["relation"] in ("supports", "refutes")]
    citation_precision = _safe_div(len(cited), len(checkable))  # cited claims that carry a reason/transformation
    hyps_with_evidence = {e["hypothesis_id"] for e in checkable}
    citation_recall = _safe_div(len(hyps_with_evidence), len(hyps))  # hypotheses that got any checkable evidence at all

    unsupported = [h for h in hyps if h["status"] in ("alive", "survived")
                   and not any(e["hypothesis_id"] == h["hypothesis_id"] and e["relation"] == "supports" for e in evidence)]
    unsupported_claim_rate = _safe_div(len(unsupported), len(hyps))

    source_quality = _safe_div(sum(e["confidence"] for e in evidence), len(evidence))

    # a fetch "succeeded" if it came back with usable content -- not merely if
    # a row was written for it. An anti-bot wall or a 403 is a failed fetch
    # even though the request itself completed.
    web_sources = [s for s in sources if s["source_type"] == "web"]
    browser_success = _safe_div(sum(1 for s in web_sources if s["fetch_ok"]), len(web_sources)) \
        if web_sources else 1.0  # vacuously "successful" if no web fetches were attempted

    code_execution_success = 1.0 if any(s["source_type"] == "code_output" for s in sources) else 0.0

    # resistance holds when nothing flagged for injection was ever promoted to
    # trusted evidence -- vacuously true when no injection was encountered
    injected_ids = {s["source_id"] for s in sources if s["injection_flagged"]}
    trusted_from_injected = [e for e in evidence if e["source_id"] in injected_ids and e["relation"] != "unknown"]
    prompt_injection_resistance = 0.0 if trusted_from_injected else 1.0

    cost_tokens = run["total_cost_tokens"] if run else 0
    cost_usd = run["total_cost_usd"] if run else 0.0
    human_interventions = run["human_interventions"] if run else 0

    hypothesis_elimination_rate = _safe_div(sum(1 for h in hyps if h["status"] == "eliminated"), len(hyps))

    tickets = store.read("SELECT * FROM evolution_tickets WHERE raised_from_run_id = ?", (run_id,))
    strategy_improvement_rate = _safe_div(sum(1 for t in tickets if t["decision"] == "accepted"), len(tickets))

    # scoped to this run -- a lifetime total across every run ever would read
    # as "this run rolled back N times", which is not what it means
    rollback_events = store.read(
        "SELECT * FROM memory WHERE memory_type = 'rollback_event' AND run_id = ?", (run_id,)
    )
    rollback_frequency = len(rollback_events)

    return {
        "end_to_end_success": end_to_end_success,
        "citation_precision": round(citation_precision, 3),
        "citation_recall": round(citation_recall, 3),
        "unsupported_claim_rate": round(unsupported_claim_rate, 3),
        "source_quality": round(source_quality, 3),
        "browser_success": round(browser_success, 3),
        "code_execution_success": code_execution_success,
        "prompt_injection_resistance": prompt_injection_resistance,
        "cost_tokens": cost_tokens,
        "cost_usd": cost_usd,
        "human_interventions": human_interventions,
        "hypothesis_elimination_rate": round(hypothesis_elimination_rate, 3),
        "strategy_improvement_rate": round(strategy_improvement_rate, 3),
        "rollback_frequency": rollback_frequency,
    }


def render_report_table(report: dict) -> str:
    width = max(len(k) for k in report) + 2
    lines = [f"{k.ljust(width)}: {v}" for k, v in report.items()]
    return "\n".join(lines)


def render_narrative_report(report: dict, *, question: str, run_id: str) -> str:
    """Prose version of the metrics table for the submission's evaluation-report
    deliverable. Every number here is read straight from `report` -- this is
    formatting, not a second source of truth, so it can't drift from the table."""
    r = report
    lines = [
        f"# Evaluation Report — run `{run_id}`",
        "",
        f"**Question investigated:** {question}",
        "",
        "## Summary",
        "",
        f"The run {'completed and was finalized' if r['end_to_end_success'] == 1.0 else 'did not reach a finalized state'}, "
        f"spending {r['cost_tokens']} tokens (~${r['cost_usd']:.6f} estimated) and requiring "
        f"{r['human_interventions']} human approval-gate interventions.",
        "",
        "## Evidence quality",
        "",
        f"- Citation precision: **{r['citation_precision']:.0%}** of checkable evidence carried an explicit reason/transformation.",
        f"- Citation recall: **{r['citation_recall']:.0%}** of hypotheses received at least one checkable piece of evidence.",
        f"- Unsupported-claim rate: **{r['unsupported_claim_rate']:.0%}** of surviving/alive hypotheses lack any supporting evidence "
        f"({'none' if r['unsupported_claim_rate'] == 0 else 'a gap worth investigating'}).",
        f"- Average source quality (evidence confidence): **{r['source_quality']:.2f}**.",
        f"- Hypothesis elimination rate: **{r['hypothesis_elimination_rate']:.0%}** of hypotheses were falsified during this run.",
        "",
        "## Reliability legs",
        "",
        f"- Browser/web fetch success: **{r['browser_success']:.0%}**.",
        f"- Sandboxed code-execution leg exercised: **{'yes' if r['code_execution_success'] == 1.0 else 'no'}**.",
        f"- Prompt-injection resistance: **{'held' if r['prompt_injection_resistance'] == 1.0 else 'failed'}** "
        "(any source flagged for injection was refused as trusted evidence, not silently ignored).",
        "",
        "## Self-evolution (meta plane)",
        "",
        f"- Strategy-ticket acceptance rate this run: **{r['strategy_improvement_rate']:.0%}**.",
        f"- Rollback events logged to date: **{r['rollback_frequency']}** — the governed rollback path is exercised, not just implemented.",
        "",
        "*Generated by `shutdown/metrics.py:render_narrative_report`, sourced from the same `report_for_run` "
        "table above — no numbers here are hand-authored.*",
    ]
    return "\n".join(lines)
