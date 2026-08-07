# CodeRush 2.0 | Astra

### Track 1: Agentic Ecosystem

**PS Number:** AE-02
**Problem Statement:** Self-evolving autonomous research agent

## Project Information

- **Team Name:** Astra
- **Project Title:** Shutdown
- **Track/Theme:** Track 1 — Agentic Ecosystem
- **Problem Statement:** AE-02 — Self-evolving autonomous research agent

## Status

Core pipeline is **built and verified end-to-end** against a live Gemini key (`shutdown/`), with an offline MockLLM path for reproducible testing without API cost. For the full current build state, known gaps, and operating notes for continuing this work, see [`HANDOFF.md`](HANDOFF.md) — it is the source of truth and is kept more current than this file.

Quick start:
```
pip install -r requirements.txt
# .env with GEMINI_API_KEY=... for a live run, or omit it to use MockLLM
python -m shutdown.main          # full end-to-end demo run
python -m shutdown.evaluate      # held-out benchmark only, no LLM cost
python -m unittest discover -s shutdown/tests -t .   # unit tests
```

### Shutdown — Adaptive Falsification Engine

**Pitch:** An agent that doesn't execute a fixed research plan — it replans every time evidence contradicts itself, and it actively hunts for evidence against its own conclusion before trusting it.

Two ideas fused, not competing:
- **Falsification framing** (memorable, demoable, gives you the injection-defense test for free)
- **Adaptive replanning** (the mechanic that elevates this design — "plan once, execute" is what every competitor does; "replan on contradiction" is what AE-02's planner language literally rewards)

---

### Architecture (buildable version)

```
Question
    │
    ▼
Hypothesis Framer          → falsifiable claim(s), confidence target, stop condition
    │
    ▼
Investigation Planner       → decides which evidence types are needed, in what order
    │
    ▼
┌─────────────── Evidence Collection Round ───────────────┐
│  Contradiction Hunter (live search, untrusted-page       │
│  handling — injection defense lives here)                │
│  Statistical Weakness Agent (sandboxed recompute,         │
│  only for closed-form claims)                             │
│  Assumption Auditor (rule-based, no live dependency)      │
└──────────────────────┬─────────────────────────────────┘
                        ▼
              Confidence Update
                        │
         ┌──────────────┴───────────────┐
         │ still uncertain / new         │ confidence stable /
         │ contradiction found           │ stop condition met
         ▼                               ▼
   Replan (new evidence targets)    Finalize
         │                               │
         └──────────► loop back ◄────────┘
                        │
                        ▼
              Attack/Evidence Graph
           (claim → evidence → source → survived/killed)
                        │
                        ▼
              Human Approval Gate
                        │
                        ▼
              Verdict Report

══════════ background, cross-mission ══════════
     Strategy Evaluator: tracks which evidence-collection
     order/weighting actually raised accuracy on a held-out
     labeled set → proposes v2 → benchmark → approve → version → rollback
```

**Design decisions:**
- Kept 3 evidence agents, not 4-6 — Contradiction Hunter, Statistical Weakness Agent, Assumption Auditor. Case-Study Failure Finder is cut (redundant with Contradiction Hunter in practice, and thinnest source availability).
- Added the **replan loop** as the literal hero mechanic — "plan → evidence → replan → evidence → stop" maps closely to AE-02's own wording, rather than a static attack pipeline.
- Cut Neo4j → plain SQLite/Postgres tables + NetworkX or a JSON tree rendered client-side. A judge cannot tell the difference between Neo4j and a well-rendered JSON tree in a 7-minute demo; they can tell the difference between a working demo and a half-configured graph database.
- Cut Docker → subprocess + resource limits + timeout. Same reasoning.
- Cut ChromaDB unless vector memory is already working from prior work — otherwise it's new infra for marginal benefit at this stage.
- Cut "6 retrieval source types" (academic/government/PDF/dataset/terminal/browser) → 1 solid search API + PDF reading + sandboxed code. Depth over breadth.
- React Flow *or* Cytoscape, not both.

---

### Why this fits the rubric

- **Technical depth (25%)**: replanning loop + falsification agents together show real orchestration logic, not a linear pipeline.
- **Reliability/evaluation (20%)**: a held-out benchmark (v1 vs v2 evidence-weighting, measured on 10-15 pre-labeled hypotheses) is honest and reproducible.
- **Safety/governance (15%)**: injection defense + approval gate + rollback, all demoable in under a minute each.
- **Originality (10%)**: "replans when its own evidence contradicts itself" is a sharper, more specific claim than "AI that researches" — none of the existing research-agent tools visibly replan mid-investigation on contradiction; they retrieve-then-summarize once.

---

### Demo script (7 min, single hypothesis, unscripted second one)

1. State hypothesis: "This paper's claimed 15% gain from RIS-assisted beamforming holds under realistic channel conditions."
2. Planner builds initial evidence plan.
3. Contradiction Hunter finds a disputing paper → confidence drops → **planner visibly replans**, adds a new evidence target (checking the CSI assumption).
4. Statistical Weakness Agent recomputes gain under stated vs. realistic CSI in sandbox → shows the drop numerically.
5. One fetched page contains a hidden injected instruction → shown detected, ignored, logged.
6. Verdict: confidence score, evidence graph, what survived and what didn't.
7. Human approval click before verdict is finalized.
8. Unscripted second hypothesis, live.
9. Strategy Evaluator: v1 vs v2 evidence-weighting, held-out accuracy table, approval, rollback shown live.

---

### Build priority (cut from bottom if time runs out)

1. Hypothesis Framer + Planner + replan loop — must-have, this is the differentiator
2. Assumption Auditor — cheapest, no live dependency
3. Contradiction Hunter + injection defense test — must-have, explicitly required by handbook
4. Evidence graph (JSON tree render is enough) — must-have
5. Strategy Evaluator + held-out benchmark — must-have, 20% of score lives here
6. Approval gate — cheap, do it
7. Statistical Weakness Agent (sandboxed recompute) — build only if time remains, scope to closed-form claims only
8. UI polish — last

## Technical Stack

- **Language/runtime:** Python 3.11+, stdlib `sqlite3` (WAL mode, single-writer lock) — no external database
- **LLM:** Google Gemini (`gemini-flash-latest` via `google-genai`), with pluggable OpenAI/Anthropic dispatch and an offline `MockLLM` for cost-free testing (`shutdown/llm.py`)
- **Retrieval:** DuckDuckGo keyword search (`ddgs`) + a local hash-embedding cosine rerank for hybrid retrieval, with a noisy/boilerplate-result filter (`shutdown/search.py`)
- **Document ingestion:** PyMuPDF for PDF, stdlib for CSV, `requests` for web fetches
- **Verification:** sandboxed subprocess recompute with timeout/resource limits (`shutdown/verification.py`)
- **Persistence/tracing:** SQLite schema in `shutdown/db.py`; self-contained HTML trace viewer in `shutdown/trace.py`

## Setup and Installation

1. Clone the repository.
2. `pip install -r requirements.txt`
3. Create `.env` (gitignored) with `GEMINI_API_KEY=...` for a live LLM run — omit it to run entirely offline against `MockLLM`.
4. `cd "code rush" && python -m shutdown.main`

Output lands in `shutdown_output/` (gitignored): `research_package.zip`, a styled `trace_<run_id>.html`, and `evaluation_report.json`.

## Submission docs

- [`docs/architecture.md`](docs/architecture.md) — diagram + data model
- [`docs/threat_model.md`](docs/threat_model.md) — trust boundaries, threats, mitigations
- [`docs/evaluation_report.md`](docs/evaluation_report.md) — narrative write-up of the metrics table, regenerate with `python -m shutdown.writeup`
