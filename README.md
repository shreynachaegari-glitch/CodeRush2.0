# CodeRush 2.0 | Astra

### Track 1: Agentic Ecosystem

**PS Number:** AE-02
**Problem Statement:** Self-evolving autonomous research agent

## Project Information

- **Team Name:** Astra
- **Project Title:** Shutdown
- **Track/Theme:** Track 1 — Agentic Ecosystem
- **Problem Statement:** AE-02 — Self-evolving autonomous research agent

## Project Description

Locking this now — but with real edits, not a rubber stamp. The good news: this version's core insight (replanning as the hero mechanic, not just attack agents) is genuinely stronger and maps even more literally to AE-02's language than what we had. The bad news: the stack list (Neo4j + Docker + React Flow + Cytoscape.js + ChromaDB + LangGraph + 6 retrieval source types) is scope creep back toward ARES-level ambition. We will not stand all of that up and have it work live. Here's the synthesis — keep the mechanic, cut the infra.

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

List the technologies used in this project:

- Frontend: (e.g., React, Next.js, Tailwind)
- Backend: (e.g., Node.js, FastAPI, Go)
- Database: (e.g., PostgreSQL, MongoDB, Supabase)
- Tools/APIs: (e.g., Clerk, Stripe, Gemini API)

## Setup and Installation

Provide instructions on how to run your project locally:

1. Clone the repository.
2. Install dependencies: `npm install` or `pip install -r requirements.txt`
3. Configure environment variables (provide a .env.example if necessary).
4. Start the development server: `npm run dev` or `python main.py`
