# Threat Model — Shutdown

Scope: the AE-02 self-evolving research agent (`shutdown/`), demo domain: LEO satellite bus arbitration. This covers the agent's trust boundaries, not the hackathon infra (no auth/multi-tenant/network deployment surface exists yet — single local process).

## Trust boundaries

```
Untrusted                    Trusted (control layer)              Governed-but-bounded (meta layer)
──────────                   ────────────────────────              ──────────────────────────────────
Web pages                                                          Strategy Evaluator
PDFs / CSVs        ──fetch──▶  Contradiction Hunter  ──evidence──▶  (proposes confidence-delta /
Search results                Hypothesis Framer                     retrieval-weight diffs only)
LLM outputs (as data)         Investigation Planner                        │
                               Verification sandbox                  held-out score, gated by
                               Approval Gate  ◀──human click──        Approval Gate + auto-reject
                                                                       on scope-violating diffs
```

## Assets

1. **Verdict integrity** — the final confidence/status assigned to each hypothesis must reflect real evidence, not attacker-controlled content.
2. **Control-flow integrity** — approval gates, the scope-violation policy check, and the sandbox limits must never be modifiable by anything the self-evolution loop touches.
3. **Cost/availability** — the agent must not be driven into unbounded LLM spend or infinite replanning by adversarial input.
4. **Audit trail** — every evidence item, approval, and strategy change must remain traceable and reversible (evidence graph + strategy version chain + rollback log).

## Threats and mitigations

| # | Threat | Vector | Mitigation | Status |
|---|---|---|---|---|
| T1 | Prompt injection via fetched content | A PDF/web page contains an instruction ("ignore previous instructions...") aimed at the LLM reading it as evidence | `contradiction.py:check_injection` — regex heuristics run on every fetch *before* the content is passed to any LLM call; flagged content is logged (`sources.injection_flagged`) and never contributes evidence (`relation="unknown"`), never trusted even if the LLM itself would have ignored it | Implemented, demoed (planted injection in `demo_assets/bus_arbitration_spec.pdf`), covered by `metrics.py:prompt_injection_resistance` and unit tests |
| T2 | Silent evidence poisoning from low-quality/blocked fetches | A 403, anti-bot page, or empty fetch gets HTML-stripped down to near-nothing and is scored as "supports" by default | Fetches under ~40 chars, and search results matching known boilerplate/anti-bot markers, are excluded before reaching the contradiction hunter; logged as `unknown`, not silently counted | Implemented (`main.py`, `search.py:_is_low_quality`) |
| T3 | Self-evolution loop escalates its own privileges | A strategy-evolution ticket proposes a diff that touches approval policy, sandbox limits, or network allowlist instead of confidence deltas | `strategy.py:DISALLOWED_DIFF_FIELDS` + `is_policy_violation()` — checked *before* any held-out evaluation or approval request; violating tickets are auto-rejected and logged, never even shown to the approval gate | Implemented, covered by unit tests (`test_strategy.py:TestPolicyGuard`) |
| T4 | A promoted strategy regresses accuracy | A strategy change scores well on the exact case it was designed for but hurts overall held-out accuracy | Every ticket is scored deterministically (no LLM self-grading) against the full held-out set before/after; promotion requires explicit human approval; `strategy.rollback()` restores the prior active version and is logged to `memory` (`rollback_frequency` metric) | Implemented and explicitly demoed (deliberately regressive ticket promoted then rolled back in `main.py`) |
| T5 | Sandbox escape / resource exhaustion during verification | The verification agent recomputes closed-form claims in a subprocess; malicious or buggy input could attempt to consume unbounded CPU/memory or escape the subprocess | `verification.py` runs the recompute as a subprocess with a timeout and resource limits, not `eval()`/inline execution in the main process | Implemented for the one closed-form calculation currently wired in (link-budget/FSPL); scope is narrow (fixed formula, no arbitrary code from evidence text is ever executed) |
| T6 | Unbounded replanning / cost blowup | A hypothesis never stabilizes and the planner keeps replanning indefinitely, burning LLM tokens | `planner.py:MAX_ROUNDS` (=3) hard-caps replanning rounds regardless of contradiction state; per-call token usage is tracked and surfaced in the cost metric so spend is visible, not silent | Implemented — round cap exists; **gap** — no separate hard ceiling on total token spend independent of round count, see below |
| T7 | Exposed API keys | Live keys pasted into a chat transcript or committed to the repo | `.env` is gitignored, never committed; `main.py` only loads keys from `.env`/environment, never hardcodes them | Process is sound, but **two real keys were pasted into an earlier chat transcript and need rotation** — this is a live action item, not a code fix (see `HANDOFF.md`) |

## Known gaps in this threat model (not yet mitigated)

- No hard ceiling on total token/cost spend per run independent of the round cap (T6) — round count is bounded, but a pathological single round (e.g. very long fetched content) is not separately metered.
- Injection detection is regex/heuristic-based, not exhaustive — a sufficiently novel injection phrasing could evade the pattern list. Defense-in-depth (never trusting flagged-or-unflagged fetched content as instructions, only as data) is the real backstop, not pattern completeness.
- Single-process/local-only deployment: no network exposure, no multi-user auth model exists or is claimed to exist.
