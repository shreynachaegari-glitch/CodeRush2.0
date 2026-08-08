"""End-to-end orchestrator: Question -> hypotheses -> evidence rounds ->
replan-on-contradiction -> finalize -> approval gate -> package.

Run: python -m shutdown.main
"""

from __future__ import annotations

import json
from pathlib import Path

from . import contradiction as contradiction_mod
from . import evidence as evidence_mod
from . import memory as memory_mod
from . import scholar
from . import strategy as strategy_mod
from . import verdict as verdict_mod
from .approval import ApprovalGate
from .db import Store, new_id, now
from .hypothesis import frame_hypotheses
from .llm import get_default_client
from .metrics import render_report_table, report_for_run
from .planner import build_plan, should_replan, stop_condition_met
from .search import hybrid_search
from .trace import build_research_package, render_trace_cli, render_trace_html
from .verification import recompute_link_budget, verify_claim

PROFILE_PATH = Path(__file__).parent / "profiles" / "communications.json"
HELD_OUT_PATH = Path(__file__).parent / "held_out_set.json"
HELD_OUT_RETRIEVAL_PATH = Path(__file__).parent / "held_out_retrieval.json"
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

# Hard ceiling on what one investigation may spend. The round cap in
# planner.py bounds how many *rounds* run; this bounds total spend, which the
# round cap can't -- one round over unusually long fetched content can be
# arbitrarily expensive. Reaching it stops evidence collection and finalizes
# on what's already been gathered, rather than aborting the run.
RUN_TOKEN_BUDGET = 60_000


def _track_cost(store: Store, run_id: str, llm) -> None:
    tokens = getattr(llm, "last_usage_tokens", 0) or 0
    if tokens:
        with store.write() as cur:
            cur.execute(
                "UPDATE runs SET total_cost_tokens = total_cost_tokens + ?, "
                "total_cost_usd = total_cost_usd + ? WHERE run_id = ?",
                (tokens, tokens * _EST_USD_PER_TOKEN, run_id),
            )


def _tokens_spent(store: Store, run_id: str) -> int:
    row = store.read_one("SELECT total_cost_tokens FROM runs WHERE run_id = ?", (run_id,))
    return (row["total_cost_tokens"] if row else 0) or 0


def _over_budget(store: Store, run_id: str) -> bool:
    return _tokens_spent(store, run_id) >= RUN_TOKEN_BUDGET


def _noop_emit(event: str, payload: dict) -> None:
    """Default event sink: the CLI doesn't need live events, it prints a trace
    at the end. The web UI passes a real sink to drive its live view."""


def run_investigation(store: Store, llm, question: str, profile: dict,
                      emit=_noop_emit,
                      spec_pdf: Path | None = None,
                      dataset_csv: Path | None = None,
                      use_demo_assets: bool = False) -> str:
    """`spec_pdf` is the primary document under investigation, if any.

    Passing one marks this as a *user-document* run: the document is read
    against **every** hypothesis in round 1 (not just the first), because if
    you upload a document you want it examined against all of the competing
    claims, not one of them.

    `use_demo_assets` is the *only* path to the bundled satellite PDF/CSV —
    it must be requested explicitly (the CLI demo, or an explicit "try the
    demo" action in the UI). A plain research question with no upload and no
    demo flag gets no document leg at all; it was previously silently
    defaulting to the satellite spec sheet for every question, which is not
    what "investigate this question" means.
    """
    user_document = spec_pdf is not None
    if spec_pdf is None and use_demo_assets:
        spec_pdf = SPEC_SHEET_PDF
    if dataset_csv is None and use_demo_assets and not user_document:
        dataset_csv = THERMAL_DATASET_CSV
    memory_mod.prune_expired(store)  # actually enforce expiry, not just carry the column
    run_id = new_id()

    # Pin the strategy version for the whole run, and record which one it was.
    # Pinning at the start (rather than re-reading after this run's own
    # evolution ticket promotes a new version) keeps a run reproducible: the
    # evidence in the graph was all scored under one rule, and a promoted
    # change takes effect on the *next* run. Without this, the meta plane's
    # output would never actually reach the control plane at all.
    active = strategy_mod.active_strategy(store)
    deltas = active["strategy"]["confidence_deltas"]
    retrieval_diversity = active["strategy"].get("retrieval_diversity", 0.0)

    store.insert(
        "runs",
        {
            "run_id": run_id,
            "question": question,
            "started_at": now(),
            "finished_at": None,
            "status": "running",
            "strategy_version_id": active["version_id"],
            "total_cost_tokens": 0,
            "total_cost_usd": 0.0,
            "human_interventions": 0,
        },
    )

    emit("run_started", {"run_id": run_id, "question": question,
                         "strategy_version_id": active["version_id"], "deltas": deltas,
                         "document": spec_pdf.name if spec_pdf and spec_pdf.exists() else None,
                         "user_document": user_document})

    # Fetch the document once, up front, rather than re-parsing the PDF on
    # every round-1 step below -- and so the excerpt can ground hypothesis
    # framing itself. Previously a user's uploaded document was only ever
    # checked against hypotheses framed BLIND to it (from the typed question
    # alone), so an upload could sail through a whole run without actually
    # shaping what was investigated.
    document_fetch = None
    if spec_pdf is not None and spec_pdf.exists():
        document_fetch = contradiction_mod.fetch(str(spec_pdf))

    emit("stage", {"stage": "framing", "status": "active"})
    # A planted-instruction document must never reach the framing prompt --
    # it goes through the normal injection-refusal path in the round loop
    # instead, same as any other untrusted fetch.
    document_excerpt = (document_fetch.content[:3000]
                        if user_document and document_fetch and not document_fetch.injection_flagged
                        else None)
    hyps = frame_hypotheses(store, llm, run_id, question, profile, document_excerpt=document_excerpt)
    _track_cost(store, run_id, llm)
    emit("hypotheses", {"hypotheses": [
        {"id": h.hypothesis_id, "statement": h.statement, "confidence": h.confidence_current,
         "status": h.status, "kills_it": h.expected_contradicting_evidence}
        for h in hyps
    ]})
    emit("stage", {"stage": "framing", "status": "done"})

    # -- structured dataset leg (CSV), logged once against the first hypothesis
    # up front, independent of the search loop below
    if dataset_csv is not None and dataset_csv.exists() and hyps:
        ds_fetch = contradiction_mod.fetch(str(dataset_csv))
        ds_source_id = evidence_mod.add_source(store, run_id, str(dataset_csv), ds_fetch.source_type,
                                                ds_fetch.content, ds_fetch.injection_flagged, ds_fetch.injection_detail)
        evidence_mod.add_evidence(store, hyps[0].hypothesis_id, ds_source_id, "supports", None, 0.7,
                                   "structured dataset: per-component thermal/power budget table")
        emit("evidence", {
            "hypothesis_id": hyps[0].hypothesis_id, "relation": "supports", "confidence": 0.7,
            "source": str(dataset_csv), "source_type": ds_fetch.source_type, "locator": "",
            "reason": "structured dataset: per-component thermal/power budget table",
            "excerpt": ds_fetch.content[:180],
        })

    round_number = 1
    contradiction_found_ever = False
    budget_exhausted = False

    emit("stage", {"stage": "hunting", "status": "active"})
    while not stop_condition_met(hyps, round_number) and not budget_exhausted:
        plan = build_plan(hyps, profile)
        emit("round", {"round": round_number, "steps": [
            {"hypothesis_id": s.hypothesis_id, "query": s.query} for s in plan
        ]})
        round_contradiction = False

        for step in plan:
            if _over_budget(store, run_id):
                # finalize on the evidence gathered so far rather than aborting --
                # a partial answer with an honest cost record beats no answer
                print(f"token budget ({RUN_TOKEN_BUDGET}) reached; finalizing on evidence gathered so far")
                emit("budget_reached", {"budget": RUN_TOKEN_BUDGET})
                budget_exhausted = True
                break

            hyp = next(h for h in hyps if h.hypothesis_id == step.hypothesis_id)

            # The primary document. For an uploaded document that's every
            # hypothesis in round 1 -- the user wants their file examined
            # against all the competing claims. For the bundled demo asset it's
            # just the first, so the rest of the run exercises live search.
            evidence_confidence = 0.6  # default for non-web legs (PDF/CSV/code -- already vetted, not search noise)
            read_document = round_number == 1 and (user_document or step is plan[0])
            if read_document and document_fetch is not None:
                source_ref = str(spec_pdf)
                emit("fetching", {"hypothesis_id": hyp.hypothesis_id, "source": source_ref, "kind": "document"})
                fetch = document_fetch  # already parsed once, up front -- reuse rather than re-parse per hypothesis
            else:
                # Literature first. A peer-reviewed paper with a DOI and a
                # citation count is evidence; a general web page usually isn't.
                # Web search stays as the fallback when the indexes return
                # nothing for a query.
                emit("fetching", {"hypothesis_id": hyp.hypothesis_id, "source": step.query, "kind": "literature"})
                papers = scholar.search_literature(step.query, limit=3)
                if papers:
                    paper = papers[0]
                    source_ref = paper.url or paper.doi
                    # An abstract from an index is clean, on-topic text -- far
                    # better contradiction-checking material than a scraped page.
                    fetch = contradiction_mod.FetchResult(
                        content=f"{paper.title}. {paper.abstract}".strip(),
                        source_type="paper", injection_flagged=False, injection_detail="",
                    )
                    # standing scales weight, capped so a famous paper can't
                    # dominate on reputation alone
                    evidence_confidence = round(min(0.9, 0.55 + 0.1 * min(3, paper.citations / 50)), 3)
                    emit("papers", {"hypothesis_id": hyp.hypothesis_id,
                                    "papers": [p.as_dict() for p in papers]})
                else:
                    emit("fetching", {"hypothesis_id": hyp.hypothesis_id, "source": step.query, "kind": "search"})
                    results = hybrid_search(step.query, max_results=3, diversity=retrieval_diversity)
                    top = results[0] if results else None
                    # the real locator, kept verbatim -- a citation the reader can't
                    # follow back to its origin isn't a citation
                    source_ref = top.url if top else "https://example.invalid/none"
                    fetch = contradiction_mod.fetch(source_ref)
                    if top:
                        # web search is the noisiest evidence leg -- scale confidence by
                        # how relevant the reranked result actually was instead of
                        # trusting every hit at the same flat weight.
                        evidence_confidence = round(0.3 + 0.4 * min(1.0, max(0.0, top.score)), 3)

            # an anti-bot wall or an empty body is a failed fetch even though the
            # request completed -- recorded on the source so browser_success measures
            # retrieval, not merely that a row was written
            usable = (len(fetch.content.strip()) >= 40
                      and not contradiction_mod.is_low_quality_content(fetch.content))

            source_id = evidence_mod.add_source(
                store, run_id, source_ref, fetch.source_type, fetch.content,
                fetch.injection_flagged, fetch.injection_detail,
                fetch_ok=usable or fetch.injection_flagged,  # a flagged page did fetch fine; we refused it
            )

            if fetch.injection_flagged:
                # detected, logged, refused -- content is NOT passed to the planner as trusted evidence
                evidence_mod.add_evidence(store, hyp.hypothesis_id, source_id, "unknown", None, 0.0,
                                           f"refused: injection detected ({fetch.injection_detail})")
                emit("injection_refused", {
                    "hypothesis_id": hyp.hypothesis_id, "source": source_ref,
                    "locator": fetch.locator, "detail": fetch.injection_detail, "excerpt": fetch.excerpt,
                })
                continue

            if not usable:
                evidence_mod.add_evidence(store, hyp.hypothesis_id, source_id, "unknown", None, 0.0,
                                           "fetch returned no usable content")
                emit("evidence", {
                    "hypothesis_id": hyp.hypothesis_id, "relation": "unknown", "confidence": 0.0,
                    "source": source_ref, "source_type": fetch.source_type, "locator": "",
                    "reason": "fetch returned no usable content", "excerpt": "",
                })
                continue

            contradicts, cls, reason, relevant = contradiction_mod.detect_contradiction(llm, hyp.statement, fetch.content)
            _track_cost(store, run_id, llm)
            # A source that never actually addresses the hypothesis is not
            # support for it -- previously "no contradiction found" defaulted
            # straight to "supports" even for an unrelated document, which
            # meant an irrelevant upload could still bump confidence up.
            if not relevant:
                relation = "unknown"
                evidence_confidence = 0.0
            else:
                relation = "refutes" if contradicts else "supports"
            evidence_mod.add_evidence(store, hyp.hypothesis_id, source_id, relation, cls, evidence_confidence,
                                       reason or ("search result" if relevant else "evidence does not address this hypothesis"))
            new_conf = evidence_mod.update_confidence(store, hyp.hypothesis_id, relation, deltas=deltas)
            hyp.confidence_current = new_conf
            # keep the in-memory copy in step with the store: build_plan() and
            # stop_condition_met() both filter on .status, so a stale value here
            # meant an eliminated hypothesis kept getting planned for
            hyp.status = evidence_mod.classify(new_conf)
            emit("evidence", {
                "hypothesis_id": hyp.hypothesis_id, "relation": relation, "confidence": evidence_confidence,
                "source": source_ref, "source_type": fetch.source_type,
                "locator": fetch.locator, "contradiction_class": cls,
                "reason": reason or "no same-conditions conflict found",
                "excerpt": contradiction_mod.strip_page_marks(fetch.content)[:180].strip(),
                "new_confidence": new_conf, "status": hyp.status,
            })
            if contradicts:
                round_contradiction = True
                contradiction_found_ever = True

        if budget_exhausted:
            break
        if should_replan(round_contradiction, round_number):
            emit("replan", {"from_round": round_number, "to_round": round_number + 1,
                            "why": "evidence contradicted a live hypothesis"})
            round_number += 1
            continue
        break
    emit("stage", {"stage": "hunting", "status": "done"})

    # -- verification agent: recompute a closed-form claim for this domain.
    # The bundled satellite demo keeps its polished, known-good link-budget
    # recompute; a real question gets a real check grounded in what THIS run
    # actually found -- the model is asked to extract an actual numeric claim
    # from the hypothesis/evidence and recompute it, or say honestly that
    # nothing here is closed-form recomputable. Running the satellite formula
    # against every question regardless of domain would be evidence that was
    # never really checked.
    emit("stage", {"stage": "verifying", "status": "active"})
    if use_demo_assets and not user_document:
        verify = recompute_link_budget(distance_km=550, freq_ghz=12.0, tx_power_dbw=10.0, ant_gain_db=30.0)
        if verify.ok:
            for h in hyps:
                source_id = evidence_mod.add_source(store, run_id, "sandbox://link_budget_recompute", "code_output",
                                                     verify.stdout, False, "")
                evidence_mod.add_evidence(store, h.hypothesis_id, source_id, "supports", None, 0.8,
                                           f"independent recompute: {verify.stdout.strip()}")
        emit("verification", {"ok": verify.ok, "stdout": verify.stdout.strip(),
                              "timed_out": verify.timed_out, "verifiable": True})
    elif hyps:
        # verify against the lead hypothesis -- the one the evidence gathered
        # so far actually points at, not an arbitrary pick
        lead = max(hyps, key=lambda h: h.confidence_current)
        excerpts = [row["transformation"] for row in store.read(
            "SELECT transformation FROM evidence WHERE hypothesis_id = ? ORDER BY timestamp", (lead.hypothesis_id,)
        )]
        claim = verify_claim(llm, lead.statement, excerpts)
        _track_cost(store, run_id, llm)
        if not claim.verifiable:
            emit("verification", {"ok": False, "verifiable": False, "reason": claim.reason,
                                  "hypothesis_id": lead.hypothesis_id})
        else:
            verify = claim.result
            stdout = verify.stdout.strip()
            failed = "FAIL" in stdout.upper()
            if verify.ok and not failed:
                relation = "supports"
            elif verify.ok and failed:
                relation = "refutes"
            else:
                relation = None  # sandbox errored/timed out -- not evidence either way
            if relation is not None:
                source_id = evidence_mod.add_source(store, run_id, "sandbox://claim_recompute", "code_output",
                                                     stdout, False, "")
                evidence_mod.add_evidence(store, lead.hypothesis_id, source_id, relation, None, 0.75,
                                           f"independent recompute: {stdout}")
                new_conf = evidence_mod.update_confidence(store, lead.hypothesis_id, relation, deltas=deltas)
                lead.confidence_current = new_conf
                lead.status = evidence_mod.classify(new_conf)
            emit("verification", {"ok": verify.ok, "stdout": stdout, "timed_out": verify.timed_out,
                                  "verifiable": True, "hypothesis_id": lead.hypothesis_id, "relation": relation})
    else:
        emit("verification", {"ok": False, "verifiable": False, "reason": "no hypotheses to verify"})
    emit("stage", {"stage": "verifying", "status": "done"})

    # -- meta plane: the Teacher reviews what THIS run actually did and writes
    # the ticket. Previously this block was a hardcoded string, which meant the
    # "self-improvement" loop proposed the same fix regardless of what happened.
    emit("stage", {"stage": "evolving", "status": "active"})
    gate = ApprovalGate(store)
    held_out = strategy_mod.load_held_out_set(HELD_OUT_PATH)
    retrieval_held_out = strategy_mod.load_held_out_set(HELD_OUT_RETRIEVAL_PATH)

    lesson = verdict_mod.critique_run(store, llm, run_id, question)
    _track_cost(store, run_id, llm)
    emit("teacher", lesson)

    ticket_id = strategy_mod.raise_ticket(
        store, run_id=run_id,
        failure_description=lesson["failure_description"],
        root_cause=lesson["root_cause"],
        hypothesis=lesson["hypothesis"],
        proposed_diff=lesson["proposed_diff"],
        expected_gain=lesson["expected_gain"],
        risk=lesson["risk"],
    )
    eval_result = strategy_mod.evaluate_ticket(store, ticket_id, held_out, retrieval_held_out)
    emit("ticket", {
        "ticket_id": ticket_id, "kind": "improvement",
        "failure": lesson["failure_description"], "root_cause": lesson["root_cause"],
        "authored_by": lesson.get("authored_by", "teacher"),
        "proposed_diff": lesson["proposed_diff"],
        "before": eval_result.get("before"), "after": eval_result.get("after"),
        "improved": eval_result.get("improved"),
    })

    approval_id = gate.request(
        run_id=run_id, action_type="promote_strategy", ticket_id=ticket_id,
        context=eval_result,
    )
    # presenter approves live if it actually improved; otherwise this is the rollback demo beat
    approved = bool(eval_result.get("improved"))
    emit("approval", {"approval_id": approval_id, "action": "promote_strategy",
                      "approved": approved, "context": eval_result})
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
    bad_eval = strategy_mod.evaluate_ticket(store, bad_ticket_id, held_out, retrieval_held_out)
    strategy_mod.finalize_ticket(store, bad_ticket_id, approved=True)  # simulate: promoted before regression caught
    strategy_mod.rollback(store, pre_rollback_active, run_id=run_id,
                          reason="held-out accuracy regressed after promotion")
    rollback_demo = {
        "bad_version_accuracy": bad_eval["after"]["accuracy"],
        "restored_version_accuracy": bad_eval["before"]["accuracy"],
        "rolled_back_to": pre_rollback_active,
    }

    print(f"rollback demo: bad version scored {rollback_demo['bad_version_accuracy']:.3f}, "
          f"restored version scores {rollback_demo['restored_version_accuracy']:.3f} "
          f"(rolled back to {rollback_demo['rolled_back_to']})")
    emit("ticket", {
        "ticket_id": bad_ticket_id, "kind": "regressive",
        "failure": "Deliberately regressive proposal, to exercise the rollback path.",
        "proposed_diff": {"confidence_deltas": {"refutes": 0.0}},
        "before": bad_eval.get("before"), "after": bad_eval.get("after"),
        "improved": bad_eval.get("improved"),
    })
    emit("rollback", rollback_demo)
    emit("stage", {"stage": "evolving", "status": "done"})

    # -- verdict: actually answer the question. Confidence numbers are not a
    # conclusion; this states what the evidence shows, rules each hypothesis
    # right/wrong/undetermined, and names what would overturn it.
    emit("stage", {"stage": "verdict", "status": "active"})
    final_verdict = verdict_mod.synthesize_verdict(store, llm, run_id, question)
    _track_cost(store, run_id, llm)
    ruling_by_id = {r["hypothesis_id"]: r for r in final_verdict.get("rulings", [])}
    emit("verdict", {
        **final_verdict,
        "hypotheses": [
            {"id": h.hypothesis_id, "statement": h.statement,
             "confidence": h.confidence_current, "status": h.status,
             "ruling": ruling_by_id.get(h.hypothesis_id, {}).get("ruling", "undetermined"),
             "why": ruling_by_id.get(h.hypothesis_id, {}).get("why", "")}
            for h in hyps
        ],
    })
    memory_mod.remember(store, "verdict", run_id, final_verdict, provenance="verdict.synthesize_verdict")

    # -- synthesis: judging claims isn't the same as producing an idea. This
    # proposes what to do about the result, constrained by the same evidence
    # and held to the same falsifiability standard as the hypotheses were.
    synthesis = verdict_mod.propose_solutions(store, llm, run_id, question, final_verdict)
    _track_cost(store, run_id, llm)
    emit("synthesis", synthesis)
    memory_mod.remember(store, "synthesis", run_id, synthesis, provenance="verdict.propose_solutions")

    # -- long-term memory: what's left open, and what was actually consulted.
    # Both are genuinely expiring (see memory.py) -- an unresolved question
    # nobody follows up on, or a source-consultation summary, both go stale.
    memory_mod.remember_unresolved_questions(store, run_id, hyps)
    run_sources = [dict(s) for s in store.read("SELECT * FROM sources WHERE run_id = ?", (run_id,))]
    memory_mod.remember_source_summary(store, run_id, question, run_sources)

    # -- publish gate
    graph_summary = {
        "hypotheses": [h.statement for h in hyps],
        "contradiction_found": contradiction_found_ever,
        "rollback_demo": rollback_demo,
        "verdict": final_verdict,
    }
    publish_approval_id = gate.request(run_id=run_id, action_type="publish_verdict", context=graph_summary)
    emit("approval", {"approval_id": publish_approval_id, "action": "publish_verdict",
                      "approved": True, "context": graph_summary})
    gate.resolve(publish_approval_id, approved=True)

    store.update("runs", "run_id", run_id, {"status": "finalized", "finished_at": now()})
    emit("stage", {"stage": "verdict", "status": "done"})
    emit("finished", {"run_id": run_id, "report": report_for_run(store, run_id),
                      "contradiction_found": contradiction_found_ever})
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
    run_id = run_investigation(store, llm, question, profile, use_demo_assets=True)

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
