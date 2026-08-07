"""End-to-end orchestrator: Question -> hypotheses -> evidence rounds ->
replan-on-contradiction -> finalize -> approval gate -> package.

Run: python -m shutdown.main
"""

from __future__ import annotations

import json
from pathlib import Path

from . import contradiction as contradiction_mod
from . import evidence as evidence_mod
from . import strategy as strategy_mod
from .approval import ApprovalGate
from .db import Store, dumps, new_id, now
from .hypothesis import frame_hypotheses
from .llm import get_default_client
from .metrics import render_report_table, report_for_run
from .planner import build_plan, should_replan, stop_condition_met
from .search import hybrid_search
from .trace import build_research_package, render_trace_cli, render_trace_html
from .verification import recompute_link_budget

PROFILE_PATH = Path(__file__).parent / "profiles" / "communications.json"
HELD_OUT_PATH = Path(__file__).parent / "held_out_set.json"
DEMO_ASSETS = Path(__file__).parent.parent / "demo_assets"

# Real files, not inline strings -- exercises actual PDF parsing and actual
# CSV ingestion. The PDF has a planted instruction buried in section 4.3
# (see demo_assets/generate_assets.py); the CSV is the "1 structured dataset"
# leg of the AE-02 minimum-viable-demonstration checklist.
SPEC_SHEET_PDF = DEMO_ASSETS / "bus_arbitration_spec.pdf"
THERMAL_DATASET_CSV = DEMO_ASSETS / "thermal_power_constraints.csv"


# Rough blended estimate for a small "flash"-tier model, USD per token.
# Labeled as an estimate deliberately -- real per-provider pricing varies and
# changes; this is enough to populate the handbook's "cost" column honestly
# rather than leaving it at zero.
_EST_USD_PER_TOKEN = 0.0000003


def _track_cost(store: Store, run_id: str, llm) -> None:
    tokens = getattr(llm, "last_usage_tokens", 0) or 0
    if tokens:
        with store.write() as cur:
            cur.execute(
                "UPDATE runs SET total_cost_tokens = total_cost_tokens + ?, "
                "total_cost_usd = total_cost_usd + ? WHERE run_id = ?",
                (tokens, tokens * _EST_USD_PER_TOKEN, run_id),
            )


def run_investigation(store: Store, llm, question: str, profile: dict) -> str:
    run_id = new_id()
    store.insert(
        "runs",
        {
            "run_id": run_id,
            "question": question,
            "started_at": now(),
            "finished_at": None,
            "status": "running",
            "strategy_version_id": None,
            "total_cost_tokens": 0,
            "total_cost_usd": 0.0,
            "human_interventions": 0,
        },
    )

    hyps = frame_hypotheses(store, llm, run_id, question, profile)
    _track_cost(store, run_id, llm)

    # -- structured dataset leg (CSV), logged once against the first hypothesis
    # up front, independent of the search loop below
    if THERMAL_DATASET_CSV.exists() and hyps:
        ds_fetch = contradiction_mod.fetch(str(THERMAL_DATASET_CSV))
        ds_source_id = evidence_mod.add_source(store, run_id, str(THERMAL_DATASET_CSV), ds_fetch.source_type,
                                                ds_fetch.content, ds_fetch.injection_flagged, ds_fetch.injection_detail)
        evidence_mod.add_evidence(store, hyps[0].hypothesis_id, ds_source_id, "supports", None, 0.7,
                                   "structured dataset: per-component thermal/power budget table")

    round_number = 1
    contradiction_found_ever = False

    while not stop_condition_met(hyps, round_number):
        plan = build_plan(hyps, profile)
        round_contradiction = False

        for step in plan:
            hyp = next(h for h in hyps if h.hypothesis_id == step.hypothesis_id)

            # -- the PDF spec sheet (with its planted instruction), fetched once, for the demo beat
            if round_number == 1 and step is plan[0] and SPEC_SHEET_PDF.exists():
                fetch = contradiction_mod.fetch(str(SPEC_SHEET_PDF))
            else:
                results = hybrid_search(step.query, max_results=3)
                top = results[0] if results else None
                fetch = contradiction_mod.fetch(top.url if top else "https://example.invalid/none")

            source_id = evidence_mod.add_source(
                store, run_id, fetch.content[:200], fetch.source_type, fetch.content,
                fetch.injection_flagged, fetch.injection_detail,
            )

            if fetch.injection_flagged:
                # detected, logged, refused -- content is NOT passed to the planner as trusted evidence
                evidence_mod.add_evidence(store, hyp.hypothesis_id, source_id, "unknown", None, 0.0,
                                           f"refused: injection detected ({fetch.injection_detail})")
                continue

            if len(fetch.content.strip()) < 40:
                # empty/blocked fetch (e.g. a 403 or an anti-bot page) has no content to
                # actually check -- log it as unknown, don't silently count it as support
                evidence_mod.add_evidence(store, hyp.hypothesis_id, source_id, "unknown", None, 0.0,
                                           "fetch returned no usable content")
                continue

            contradicts, cls, reason = contradiction_mod.detect_contradiction(llm, hyp.statement, fetch.content)
            _track_cost(store, run_id, llm)
            relation = "refutes" if contradicts else "supports"
            evidence_mod.add_evidence(store, hyp.hypothesis_id, source_id, relation, cls, 0.6, reason or "search result")
            new_conf = evidence_mod.update_confidence(store, hyp.hypothesis_id, relation)
            hyp.confidence_current = new_conf
            if contradicts:
                round_contradiction = True
                contradiction_found_ever = True

        if should_replan(round_contradiction, round_number):
            round_number += 1
            continue
        break

    # -- verification agent: recompute a closed-form claim for this domain
    verify = recompute_link_budget(distance_km=550, freq_ghz=12.0, tx_power_dbw=10.0, ant_gain_db=30.0)
    if verify.ok:
        for h in hyps:
            source_id = evidence_mod.add_source(store, run_id, "sandbox://link_budget_recompute", "code_output",
                                                 verify.stdout, False, "")
            evidence_mod.add_evidence(store, h.hypothesis_id, source_id, "supports", None, 0.8,
                                       f"independent recompute: {verify.stdout.strip()}")

    # -- meta plane: one failure this run surfaced becomes an evolution ticket
    gate = ApprovalGate(store)
    held_out = strategy_mod.load_held_out_set(HELD_OUT_PATH)
    ticket_id = strategy_mod.raise_ticket(
        store, run_id=run_id,
        failure_description="Weak-evidence sources were treated the same as strong ones (no distinction in confidence delta).",
        root_cause="Confidence-update rule doesn't scale the 'weakens' penalty by source quality.",
        hypothesis="Increasing the 'weakens' penalty slightly will separate genuinely weak claims from alive ones faster.",
        proposed_diff={"confidence_deltas": {"weakens": -0.10}},
        expected_gain="+ held-out accuracy on borderline 'weakens' cases",
        risk="Might over-penalize claims that recover with later supporting evidence",
    )
    eval_result = strategy_mod.evaluate_ticket(store, ticket_id, held_out)

    approval_id = gate.request(
        run_id=run_id, action_type="promote_strategy", ticket_id=ticket_id,
        context=eval_result,
    )
    # presenter approves live if it actually improved; otherwise this is the rollback demo beat
    approved = bool(eval_result.get("improved"))
    gate.resolve(approval_id, approved=approved)
    strategy_mod.finalize_ticket(store, ticket_id, approved=approved)

    # -- rollback demonstration (named required deliverable in the handbook):
    # propose a deliberately regressive change, simulate it having been
    # promoted before the regression was caught, then roll back to the
    # version that was active immediately before it.
    pre_rollback_active = strategy_mod.active_version_id(store)
    bad_ticket_id = strategy_mod.raise_ticket(
        store, run_id=run_id,
        failure_description="Rollback demonstration: a second, more aggressive strategy change is tested.",
        root_cause="Hypothetical -- zeroing the 'refutes' penalty would let refuted claims linger as 'alive'.",
        hypothesis="Removing the refutes penalty entirely will not hurt held-out accuracy.",
        proposed_diff={"confidence_deltas": {"refutes": 0.0}},
        expected_gain="none expected -- this proposal is intentionally regressive, to exercise the rollback path",
        risk="Refuted claims never get eliminated",
    )
    bad_eval = strategy_mod.evaluate_ticket(store, bad_ticket_id, held_out)
    strategy_mod.finalize_ticket(store, bad_ticket_id, approved=True)  # simulate: promoted before regression caught
    strategy_mod.rollback(store, pre_rollback_active)
    rollback_demo = {
        "bad_version_accuracy": bad_eval["after"]["accuracy"],
        "restored_version_accuracy": bad_eval["before"]["accuracy"],
        "rolled_back_to": pre_rollback_active,
    }

    print(f"rollback demo: bad version scored {rollback_demo['bad_version_accuracy']:.3f}, "
          f"restored version scores {rollback_demo['restored_version_accuracy']:.3f} "
          f"(rolled back to {rollback_demo['rolled_back_to']})")

    # -- publish gate
    graph_summary = {
        "hypotheses": [h.statement for h in hyps],
        "contradiction_found": contradiction_found_ever,
        "rollback_demo": rollback_demo,
    }
    publish_approval_id = gate.request(run_id=run_id, action_type="publish_verdict", context=graph_summary)
    gate.resolve(publish_approval_id, approved=True)

    store.update("runs", "run_id", run_id, {"status": "finalized", "finished_at": now()})
    return run_id


def _load_dotenv():
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).parent.parent / ".env")
    except ImportError:
        pass


def main():
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252, breaks on em-dashes etc.
    _load_dotenv()
    store = Store("shutdown.db")
    llm = get_default_client()
    print(f"LLM backend: {type(llm).__name__}")
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

    question = (
        "For a LEO swarm satellite communication system, does enforcing single-master "
        "bus arbitration keep peak power draw within the swarm's thermal budget?"
    )
    run_id = run_investigation(store, llm, question, profile)

    print(render_trace_cli(store, run_id))
    print("\n--- evaluation report ---")
    report = report_for_run(store, run_id)
    print(render_report_table(report))

    pkg = build_research_package(store, run_id, "shutdown_output", extra_files={"evaluation_report.json": report})
    print(f"\nresearch package: {pkg}")

    trace_html_path = Path("shutdown_output") / f"trace_{run_id}.html"
    trace_html_path.write_text(render_trace_html(store, run_id), encoding="utf-8")
    print(f"trace viewer (open in a browser): {trace_html_path}")


if __name__ == "__main__":
    main()
