# Shutdown — Project Handoff / History

Paste this file's path (or its contents) into a new Claude Code chat to resume with full context:
`code rush/HANDOFF.md` in this repo.

## What this is

**CodeRush 2.0** hackathon submission.
- **Team:** Astra
- **Project title:** Shutdown (originally called Janus in early drafts — renamed, keep it Shutdown)
- **Track:** Track 1 — Agentic Ecosystem
- **Problem statement:** AE-02 — Self-Evolving Autonomous Research Agent
- **GitHub repo:** https://github.com/shreynachaegari-glitch/CodeRush2.0 (public)
- **Local path:** `c:\Users\shrey\Documents\Codex\2026-04-23-files-mentioned-by-the-user-resnet50\building_seg_v2_fixed_final\NRSC\code rush\`
- **Git identity used:** N SREYESH KUMAR / shreynachaegari@gmail.com (local repo config only)
- **GitHub CLI:** installed via winget, authenticated as `shreynachaegari-glitch`

The source-of-truth problem statement doc is `Participants Handbook and Problem Statements.docx` in the user's Downloads folder — read directly, not from memory, when any AE-02 requirement question comes up again.

## The pitch, one paragraph

Shutdown takes a research question, generates competing falsifiable hypotheses, actively hunts for evidence that would kill each one (not just evidence that supports the leading candidate), replans its investigation the moment evidence contradicts itself, and — separately — logs its own strategy failures as structured tickets, proposes versioned fixes, tests them on a held-out labeled set, and only promotes a fix after a human approves it. Every claim, source, and strategy change is traceable and reversible. Demo domain: satellite/comms (LEO swarm bus arbitration), chosen as a single vertical slice — the core engine itself is domain-agnostic.

## Key architecture decision: two planes

- **Control plane** (task agent): Hypothesis Framer → Investigation Planner → Contradiction Hunter → Verification Agent → Confidence Update → Replan-or-Finalize. Answers one question.
- **Meta plane** (meta agent): Strategy Evaluator. The *only* component allowed to change the parameters the control plane uses (confidence-update deltas, retrieval weighting). Reads failures, proposes a versioned diff, tests it on held-out data, requires human approval before promotion.

Full architecture diagram, SQLite schema, and reasoning for every scope cut are in the locked plan file:
`C:\Users\shrey\.claude\plans\check-the-docs-of-reflective-hamming.md`

## Judging rubric (memorize this, it's the actual scoring)

Technical depth 25% · Verified usefulness 20% · Reliability/evaluation 20% · Safety/governance 15% · UX 10% · Originality/leverage 10%.

## What NOT to build (deliberate, already argued through — don't re-litigate)

- No Neo4j, Docker, ChromaDB, e2b, Langfuse, GAIA (gated dataset), or a real vector DB.
- No forking `open_deep_research`, `open-coscientist-agents`, `Open-Prompt-Injection`, or `reflexion` wholesale — read them for pattern ideas only, write the logic ourselves. `browser-use` was the one sanctioned exception (see Known Gaps — never actually integrated).
- No model fine-tuning / RL self-improvement — self-evolution is scoped to prompts/policies/retrieval-weights only, never model weights or the trusted control layer.
- No multi-domain "research profile" auto-routing — demo is locked to one domain (communications/satellite), loaded directly.
- No hierarchical/multi-timescale evolution, no tournament/ELO strategy promotion, no skill-library subsystem, no novelty-search bonus, no confidence-tiered evolution ladder — all considered and cut for hackathon scope; full reasoning in the plan file section "What's explicitly NOT in the architecture."

Prior art to cite honestly, not to pretend doesn't exist: **EvoFSM** (arXiv 2601.09465) is the closest academic analog to the replan-on-contradiction mechanic — the differentiator is the *combination* (falsification-as-goal + governed rollback-able self-improvement measured on held-out data + auditable evidence graph), not replanning alone.

## What's built and verified (all of it, against a live Gemini key)

Located in `code rush/shutdown/`:

| File | Does |
|---|---|
| `db.py` | SQLite schema, WAL mode, single-writer lock |
| `llm.py` | Pluggable client (`MockLLM` for offline, `_RealLLM` for Gemini/OpenAI/Anthropic — currently Gemini is the one actually used/tested) |
| `search.py` | DuckDuckGo (`ddgs` package) keyword search + local hash-embedding rerank ("hybrid retrieval") |
| `approval.py` | Checkpoint/resume approval gate — only two action types: `publish_verdict`, `promote_strategy` |
| `verification.py` | Sandboxed subprocess recompute (link-budget/FSPL calc), timeout + resource limits |
| `hypothesis.py` | Hypothesis Framer — JSON-contract prompt, 2-4 competing falsifiable hypotheses |
| `planner.py` | Investigation Planner — replans strictly on contradiction, not generic failure |
| `contradiction.py` | Contradiction Hunter — injection detection (regex heuristics), unit normalization (GHz↔MHz, °C↔K), contradiction-class tagging, real PDF (PyMuPDF)/CSV/web fetch |
| `evidence.py` | Typed evidence graph (supports/weakens/refutes), explicit confidence-update rule |
| `strategy.py` | Evolution tickets, deterministic (non-LLM-graded) held-out scoring, scope-violation auto-reject, explicit `rollback()` |
| `metrics.py` | Evaluation report using the handbook's *exact* metric names (citation precision/recall, unsupported-claim rate, source quality, browser success, code-execution success, prompt-injection resistance, cost, human interventions) plus hypothesis-elimination-rate, strategy-improvement-rate, rollback-frequency |
| `trace.py` | Styled HTML trace viewer (confidence bars, color-coded evidence/approvals/tickets) + CLI viewer + `research_package.zip` bundler |
| `main.py` | End-to-end orchestrator wiring everything + the comms/satellite demo scenario |
| `profiles/communications.json` | The one domain profile (no multi-profile routing) |
| `held_out_set.json` | 15 labeled cases: 8 self-authored + 7 adapted from public benchmark-style descriptions |
| `demo_assets/generate_assets.py` | Generates the real demo PDF (with planted prompt-injection) and CSV dataset |
| `evaluate.py` | Standalone held-out benchmark runner (`python -m shutdown.evaluate`) — no LLM call, no cost, reproducible |
| `writeup.py` | Regenerates `docs/evaluation_report.md` (narrative prose) from the latest finalized run — `python -m shutdown.writeup` |
| `tests/` | `unittest` suite covering injection detection, unit normalization, strategy scoring/policy-guard, confidence-update boundaries — `python -m unittest discover -s shutdown/tests -t .` |

**Confirmed working end-to-end with a real Gemini key** (`gemini-flash-latest`, via the current `google-genai` SDK — the old `google.generativeai` package and `gemini-1.5-flash` model are both dead, don't reintroduce them):
- 3 distinct, falsifiable, domain-appropriate hypotheses generated per run
- Real PDF parsed, planted injection detected and refused (never trusted as evidence)
- Real CSV dataset ingested as the structured-dataset leg
- Sandboxed link-budget recompute succeeds and feeds evidence in
- Evolution ticket → deterministic held-out scoring → approval gate → **explicit rollback demo** (deliberately regressive strategy promoted, caught, rolled back) all fire correctly
- Full metrics table populated including real token-cost tracking
- `research_package.zip` + styled `trace_<run_id>.html` produced in `shutdown_output/` (gitignored, regenerated per run)

Run it: `cd "code rush" && python -m shutdown.main` (needs `.env` with `GEMINI_API_KEY=...`, gitignored, not committed).

## Real bugs found and fixed by actually running it (not from review — from execution)

1. Strategy version diff-chain wasn't being replayed — before/after held-out eval was silently comparing a strategy to itself. Fixed: `_resolve_strategy()` now walks the parent chain root-to-leaf.
2. Float-drift at the 0.15 classification boundary (`0.5 - 0.35 = 0.15000000000000002`) caused a misclassification. Fixed: round before threshold checks in both `strategy.py` and `evidence.py`.
3. `google-generativeai` deprecated, `gemini-1.5-flash` returns 404 — migrated to `google-genai` + `gemini-flash-latest` alias.
4. `duckduckgo_search` renamed to `ddgs` — added fallback import chain.
5. Empty/blocked fetches (403s, anti-bot pages) were silently counted as "supports" evidence — now logged as `unknown` and skipped if content is under ~40 chars, or matches an anti-bot/blocked-access marker regardless of length (see gap #2 fix below).

## Resolved since the list below was first written (2026-08-07)

- **#2 (noisy web evidence)** — `search.py` now filters low-quality/anti-bot search snippets before ranking; `contradiction.py:is_low_quality_content()` catches full fetched pages that survive HTML-stripping with real-looking length (e.g. "ResearchGate — Temporarily Unavailable", "Just a moment... Checking your browser") and logs them as `unknown` instead of `supports`; web evidence confidence is now scaled by the reranked relevance score instead of a flat 0.6.
- **#6 (stale README)** — rewritten to reflect the actual build, links to `HANDOFF.md` and `docs/`.
- **#7 (no test suite)** — `shutdown/tests/` (`unittest`, stdlib only) + `shutdown/evaluate.py` (standalone held-out runner, no LLM cost) added.
- **#8 (no LLM retry handling)** — `llm.py:_with_retry()` wraps every real-provider call with exponential backoff on transient errors (429/5xx/timeout/connection); non-transient errors still raise immediately.
- **#9 (stale requirements.txt)** — cleaned up to `ddgs`, `python-dotenv`, `google-genai` as real (not commented-out) deps.
- **#5 (partial)** — `docs/architecture.md` (mermaid diagram + data model), `docs/threat_model.md` (trust boundaries / threats / mitigations table), and `docs/evaluation_report.md` (narrative writeup, regenerate via `python -m shutdown.writeup`) added. Demo recording itself is still outstanding.

## Known gaps — real next steps, ranked

1. **`browser-use` was never actually integrated.** The plan named it as the one sanctioned external library for browser control; the current implementation uses a plain `requests.get()` fallback instead. If the demo needs live interactive-page browsing (not just static PDF/CSV/search-result fetches), this needs to be wired in. Deliberately not done yet — heavier install (Playwright browsers), weigh against remaining hackathon time before starting.
2. ~~Web-search evidence is noisy~~ — resolved, see above. Residual: no hard ceiling on total token/cost spend per run independent of the round cap (see `docs/threat_model.md` T6).
3. **Rotate the Gemini API keys.** Two keys were pasted directly into an earlier chat (both now in that transcript) — go to `aistudio.google.com/apikey` and regenerate/delete once done testing. `.env` locally is fine and gitignored; chat history is not a safe place for a live key. **Still outstanding — this requires the user, not code.**
4. **No dry-run/rehearsal of the actual 7-8 minute demo script yet** — approval-gate click timing, narration, the "unscripted second hypothesis" beat from the plan's demo script are not yet tested as a live presentation.
5. **Demo recording itself** is the one deliverable from the original #5 not yet produced (diagram/threat-model/eval-writeup are done, see above).
6. ~~README stale~~ — resolved, see above.
7. ~~No automated test suite~~ — resolved, see above.
8. ~~No retry/error handling around LLM calls~~ — resolved, see above.
9. ~~requirements.txt stale~~ — resolved, see above.

## Operating notes for continuing this in a new chat

- Plan mode was used for the design phase; the locked plan is at `C:\Users\shrey\.claude\plans\check-the-docs-of-reflective-hamming.md` — read it for the full architecture reasoning before making design changes.
- The user (Sreyesh, he/him) prefers terse, high-signal responses; strongly reacts against scope creep — every added idea should be weighed against hackathon time cost and either adopted cheaply (schema field) or explicitly rejected with a one-line reason, mirroring the style already used throughout this build.
- Git commits use `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` per this session's convention.
- Don't recreate `.env` from memory — if a fresh key is needed, ask the user for it again (same caution as before: treat anything pasted in chat as exposed, recommend rotation after use).
