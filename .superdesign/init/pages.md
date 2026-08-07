# Pages — dependency trees

Single-file app: every "page" is a branch of the `WORK` dispatch object inside `App()`, and every component it can call is defined in the same file, `shutdown/static/app.js` (no per-page files to trace imports across). Trees below trace which named component functions / helpers each view actually renders, plus the external assets it touches.

## workspace (Research) — the primary/most complex page
Entry: `App()` → `WORK.workspace()` in `shutdown/static/app.js`
Dependencies:
- `SignalCanvas` (ambient background, only rendered inside the composer)
  - dynamic import `shutdown/static/signalfield.js` → `mountSignalField()` (WebGL2/`ogl`)
- `Pipeline` (5-node connector row)
  - `Icon` (`shutdown/static/icons.js`)
- `AgentCards` (5 agent status cards)
  - `Icon`
  - `Tag`
- `Breach` (injection alert, 0..n instances)
  - `Icon`
- verdict block (inline JSX in `WORK.workspace`, not its own function)
  - `Tag`
  - dynamic import `shutdown/static/motion.js` → `revealVerdict()` (GSAP word-reveal, fired once via `verdictRef` + `revealedVerdict` guard)
- proposals block (inline, "Original proposals" section)
  - `Icon`, `Tag`
- `HypCard` × n (ranked hypotheses)
  - `Ring` → `useCountUp` hook
  - `Tag`
  - `EvRow` × n (expanded evidence)
    - `Icon`
    - `Tag`
- literature block (inline, "Literature retrieved" section)
  - `Icon`
- activity feed block (inline)
  - none (plain text log)

External calls: `POST /api/run` (starts a run) → `EventSource /api/events/{run_id}` (drives nearly all state via ~18 named SSE events, see `routes.md`) → `GET /api/health` (backend status, on mount).

## graph (Evidence Graph)
Entry: `WORK.graph()`
Dependencies:
- `GraphView`
  - `window.EvidenceGraph` class, `shutdown/static/graph.js` (owns its own canvas 2D render loop, force simulation, hover/click handling — not a React-rendered subtree)
  - `Icon` (empty-state icon only)

External calls: polls `GET /api/graph/{run_id}` every 2.2s while `live` (a run is running).

## runs (Runs)
Entry: `WORK.runs()`
Dependencies:
- `Stub` (empty state)
- inline `.runcard` buttons (no separate component function)

External calls: `GET /api/runs` (fetched once per `view`/`running` change via a `useEffect` in `App()`, shared with `reports`).

## reports (Reports)
Entry: `WORK.reports()`
Dependencies:
- `Icon`, `Tag`
- inline `.cmp` comparison `<table>` (no separate component function)
- `Stub` (empty state, if no report yet)

External calls: reuses the same `runs` state fetched by the `runs` page's effect (`GET /api/runs`); does not re-fetch.

## library (Library)
Entry: `WORK.library()`
Dependencies:
- `Stub` (empty state)
- inline `.paper` rows (same visual shape as the workspace's "Literature retrieved" section, not a shared component function — duplicated markup)

External calls: none directly — `papers` state is accumulated client-side from the current session's `papers` SSE events only (not fetched from a papers-specific endpoint).

## strategies (Strategies)
Entry: `WORK.strategies()`
Dependencies:
- `Stub`
- a button that calls `setMetaOpen(true)` to open `MetaPanel` (see below) — this page has no content of its own, it's a signpost.

## memory (Memory)
Entry: `WORK.memory()`
Dependencies:
- `Stub` only. No backing data view implemented.

## settings (fallback, unrouted in NAV)
Entry: the `WORK[view] || fallback` default in `App()`'s render
Dependencies:
- `Stub` only.

---

## MetaPanel (overlay, not a `view` — can appear over any page)
Entry: `<${MetaPanel}>` rendered at the `App()` root when `metaOpen` is true
Dependencies:
- `Icon`, `Tag`
- inline `.commit-c` blocks for: Teacher diagnosis (if present), Evolution tickets (`tickets` state, accumulated from `ticket` SSE events), Rollback history (`rollback` state, from the `rollback` SSE event)
- inline `.commit` git-log-style list for the strategy version timeline

External calls: `GET /api/strategies` (fetched once on `MetaPanel` mount, independent of the current run).

## StatePanel (persistent right rail, on every page)
Entry: `<${StatePanel}>` rendered at the `App()` root, always visible ≥1180px
Dependencies:
- `Icon` — none directly; pure presentational, reads props (`report`, `stages`, `round`, `hyps`, `backend`, `tokens`, `strategyId`, `running`) passed down from `App()` state, no fetches of its own.
