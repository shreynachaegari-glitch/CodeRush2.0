# Routes — Shutdown Research OS

**No URL-based routing.** This is a single-page app served from one HTML entry point with no client-side router (no React Router, no History API pushState) — "navigation" is a plain `useState("workspace")` in `App()` (`shutdown/static/app.js`), and the left rail's nav buttons just call `setView(id)`. There is exactly one server route that returns the page (`GET /`, in `shutdown/web.py`); everything else is data (`/api/*`).

## Server routes (`shutdown/web.py`)
| Path | Method | Returns |
|---|---|---|
| `/` | GET | `shutdown/static/index.html` (the entire app shell) |
| `/static/*` | GET | Static assets (JS/CSS, vendored libs) |
| `/api/health` | GET | `{ backend, model, live, fallback_reason }` |
| `/api/run` | POST | Starts an investigation (multipart: `question`, optional `document`, optional `demo=1`); returns `{ run_id }` |
| `/api/events/{run_id}` | GET (SSE) | Live event stream for a run — see event list below |
| `/api/runs` | GET | List of past runs with verdict summaries (feeds the Runs and Reports views) |
| `/api/graph/{run_id}` | GET | Evidence graph nodes/edges for a run |
| `/api/strategies` | GET | Strategy version timeline + evolution tickets (feeds the Meta Plane) |

## Client "routes" — the `view` state and `WORK` dispatch table
```js
const [view, setView] = useState("workspace");
// ...
const WORK = {
  workspace:  () => html`...`,   // main research flow — composer, pipeline, agents, verdict, hypotheses, papers, activity
  graph:      () => html`<${GraphView} runId=${storeRunId} live=${running} />`,
  runs:       () => html`...`,   // list of past runs, click one to inspect its evidence graph
  reports:    () => html`...`,   // cross-run comparison table + latest evaluation report
  library:    () => html`...`,   // all papers retrieved this session
  strategies: () => html`...`,   // stub pointing at the Meta Plane
  memory:     () => html`...`,   // stub — not implemented
};
// fallback (e.g. "settings") renders a Stub
<main class="work">${(WORK[view] || fallback)()}</main>
```
No route ever has its own URL — refreshing the page always returns to `workspace` with empty state. The Meta Plane is not in `WORK`/`NAV` at all; it's a separately-controlled boolean (`metaOpen`) rendered as an overlay regardless of `view`.

## Page summaries (by `view` id)

### `workspace` (default / home) — Research
The entire investigation lifecycle in one scrolling view: question composer → `Pipeline` + `AgentCards` (live while `running`) → injection `Breach` alerts (if any) → `Verdict` card (once synthesized) → `Original proposals` (evidence-constrained synthesis) → ranked `HypCard` list with a "Best result" banner → `Literature retrieved` papers → `Activity` feed (raw event log). See `pages.md` for the full dependency tree.

### `graph` — Evidence Graph
Just `GraphView` — canvas force-graph of hypotheses/sources/evidence for `storeRunId` (the most recent run started in this session, or a run selected from `runs`).

### `runs` — Runs
List of `.runcard` buttons (question, run id, hypothesis count, tokens, status, timestamp, verdict answer snippet), fetched from `/api/runs`. Clicking one sets `storeRunId` and jumps to `graph`.

### `reports` — Reports
A `.cmp` comparison table across every run that has a verdict (question / verdict answer / confidence / claim count / tokens), with the highest-confidence run's row highlighted (`.best-row`), followed by the latest raw evaluation-report key/value dump.

### `library` — Library
All papers retrieved across the session (OpenAlex/arXiv), same `.paper` row layout as the workspace's "Literature retrieved" section.

### `strategies` — Strategies
A `Stub` pointing the user at the Meta Plane (`setMetaOpen(true)`) — this view intentionally holds no content of its own.

### `memory` — Memory
A `Stub` stating plainly that the memory browser isn't built yet (verdicts/proposals/rollback events are persisted server-side but have no dedicated browsing UI).

### `settings` (fallback, not in `NAV`)
A `Stub` explaining that backend/key configuration is done via `.env` (`GEMINI_API_KEY`, `NVIDIA_API_KEY`, `SHUTDOWN_OFFLINE=1`), reached only via the rail-foot "Settings" button.

## Server-Sent Events (the real "flow" of the app)
`on(eventName, handler)` in `launch()` — one `EventSource` per run, event names: `backend`, `run_started`, `stage`, `hypotheses`, `round`, `fetching`, `papers`, `evidence`, `injection_refused`, `replan`, `verification`, `teacher`, `ticket`, `rollback`, `verdict`, `synthesis`, `approval`, `finished`, `error`, `close`. These drive nearly every piece of client state (`stages`, `activity`, `hyps`, `ev`, `papers`, `breaches`, `tickets`, `teacher`, `rollback`, `verdict`, `synthesis`, `report`, `feed`).
