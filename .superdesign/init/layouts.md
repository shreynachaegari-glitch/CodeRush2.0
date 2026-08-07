# Layouts — Shutdown Research OS

Single-page app. There is exactly one HTML entry point (`shutdown/static/index.html`) and one root component (`App`, in `shutdown/static/app.js`) that renders the entire shell every time — there is no separate "layout wrapper" file per route; the three-pane shell and its children are all defined inline inside `App()`'s return.

---

## Root shell — `.os` (3-column grid)
Source: `shutdown/static/app.js` (bottom of `App()`), `styles.css` `.os`, `.rail`, `.work`, `.state-panel`

```js
return html`
  <div class="os">
    <nav class="rail"> ... left nav, see "Rail" below ... </nav>
    <main class="work"> ${(WORK[view] || fallback)()} </main>
    <${StatePanel} report=${report} stages=${stages} round=${round} hyps=${hyps}
                   backend=${backend} tokens=${report?.cost_tokens} strategyId=${strategyId} running=${running} />
    <button class="meta-fab" onClick=${() => setMetaOpen(true)}>
      <span class="d"></span> Meta Plane
      ${tickets.length > 0 && html`<span style=${{ color: "var(--fg-3)" }}>· ${tickets.length}</span>`}
    </button>
    ${metaOpen && html`<${MetaPanel} onClose=${() => setMetaOpen(false)}
                                     tickets=${tickets} rollback=${rollback} teacher=${teacher} />`}
  </div>`;
```

```css
.os { display: grid; grid-template-columns: var(--rail) 1fr var(--state); height: 100vh; overflow: hidden; }
/* --rail: 216px, --state: 272px (250px under 1500px) */
@media (max-width: 1180px) { .os { grid-template-columns: 64px 1fr; } .state-panel { display: none; } .rail-label { display: none; } }
@media (max-width: 780px)  { .os { grid-template-columns: 1fr; } .rail { display: none; } }
```

Three fixed columns: left nav rail → center scrollable workspace (`.work`, routed by `view` state) → right "live system state" rail. A floating pill button (`.meta-fab`, bottom-right, offset to sit left of the state panel) opens the Meta Plane as a slide-in overlay panel + scrim — it is deliberately NOT a nav item; the meta plane governs the agent's own parameters and shouldn't read as peer content to research.

---

## Rail (left nav)
Source: `shutdown/static/app.js`, `styles.css` `.rail`, `.brand*`, `.nav-*`

```js
<nav class="rail">
  <div class="brand">
    <div class="brand-m"><${Icon} name="satellite" size=17 /></div>
    <div><div class="brand-n">Shutdown</div><div class="brand-s">Research OS</div></div>
  </div>
  <div class="nav-g">
    <div class="nav-t rail-label">Workspace</div>
    ${NAV.map((n) => html`
      <button class=${"nav-i " + (view === n.id ? "on" : "")} onClick=${() => setView(n.id)}>
        <span class="ic"><${Icon} name=${n.icon} size=16 /></span>
        <span class="rail-label">${n.label}</span>
        ${n.id === "runs" && runs.length > 0 && html`<span class="badge rail-label">${runs.length}</span>`}
        ${n.id === "library" && papers.length > 0 && html`<span class="badge rail-label">${papers.length}</span>`}
      </button>`)}
  </div>
  <div class="rail-foot">
    <button class="nav-i" onClick=${() => setView("settings")}>
      <span class="ic"><${Icon} name="settings" size=16 /></span>
      <span class="rail-label">Settings</span>
    </button>
  </div>
</nav>
```

```js
const NAV = [
  { id: "workspace",  label: "Research",        icon: "hunt" },
  { id: "runs",       label: "Runs",            icon: "runs" },
  { id: "graph",      label: "Evidence Graph",  icon: "graph" },
  { id: "library",    label: "Library",         icon: "library" },
  { id: "strategies", label: "Strategies",      icon: "strategies" },
  { id: "memory",     label: "Memory",          icon: "memory" },
  { id: "reports",    label: "Reports",         icon: "reports" },
];
```
216px fixed width, collapses to 64px icon-only at ≤1180px (labels hidden via `.rail-label { display: none }`), hidden entirely at ≤780px. Active item gets `.on` (background `--s-3`, icon tinted `--control`). Badge counts show live counts (runs recorded, papers in library).

---

## Pipeline (thin connector row)
Source: `shutdown/static/app.js`, `styles.css` `.pipe`, `.pstage`, `.porb`

```js
const STAGES = [
  { id: "framing",   label: "Framing",      icon: "branch" },
  { id: "hunting",   label: "Hunting",      icon: "hunt" },
  { id: "verifying", label: "Verification", icon: "beaker" },
  { id: "evolving",  label: "Evolution",    icon: "dna" },
  { id: "verdict",   label: "Verdict",      icon: "seal" },
];
const Pipeline = ({ stages }) => html`
  <div class="pipe">
    ${STAGES.map((s, i) => {
      const st = stages[s.id] || "idle";
      const flowed = i > 0 && stages[STAGES[i - 1].id] === "done";
      return html`
        <div class="pstage ${st} ${flowed ? "flowed" : ""}">
          <div class="porb"><${Icon} name=${st === "done" ? "check" : s.icon} size=15 /></div>
          <div class="pl">${s.label}</div>
        </div>`;
    })}
  </div>`;
```
Five nodes in a row, connected by a horizontal line that draws itself green (`draw` keyframe, `scaleX` 0→1) as each stage completes. The active node pulses with a halo ring (`halo` keyframe). States: `idle` (default, gray) → `active` (indigo, scaled 1.1×, pulsing halo) → `done` (green, checkmark icon). Sits directly above `AgentCards` — same state, denser summary view.

---

## AgentCards (per-agent progress — the primary "what is the agent doing right now" surface)
Source: `shutdown/static/app.js`, `styles.css` `.agents`, `.agent*`

```js
const AGENTS = [
  { id: "framing",   name: "Hypothesis Framer",   role: "Generates competing falsifiable claims" },
  { id: "hunting",   name: "Contradiction Hunter", role: "Hunts for evidence that would kill each claim" },
  { id: "verifying", name: "Verification Agent",  role: "Recomputes a claim in a sandbox" },
  { id: "evolving",  name: "Strategy Evaluator",  role: "Diagnoses this run, proposes a governed fix" },
  { id: "verdict",   name: "Verdict Synthesizer", role: "States the answer, rules each claim" },
];
const AgentCards = ({ stages, activity }) => html`
  <div class="agents">
    ${AGENTS.map((a) => {
      const st = stages[a.id] || "idle";
      return html`
        <div class="agent ${st}">
          <div class="agent-hd">
            <div class="agent-ic"><${Icon} name=${st === "done" ? "check" : a.icon} size=15 /></div>
            <div>
              <div class="agent-n">${a.name}</div>
              <div class="agent-r">${a.role}</div>
            </div>
            <div class="agent-status"><${Tag} k=${st === "done" ? "supports" : st === "active" ? "alive" : "unknown"}>${st}<//></div>
          </div>
          <div class="agent-live">
            ${st === "active" ? html`<span class="dots">${activity[a.id] || "working"}</span>`
              : st === "done" ? (activity[a.id] || "complete") : "waiting"}
          </div>
        </div>`;
    })}
  </div>`;
```
```css
.agents { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--sp-2); margin-bottom: var(--sp-5); }
```
Responsive card grid, one card per agent. `activity[stage_id]` is populated live from SSE events (e.g. `"supports · doi.org/10.1109/access.2018.2"`, `"sandbox ok · FSPL_dB=168.841"`) — real status text sourced from the event stream, never a generic spinner/skeleton for an active agent.

---

## StatePanel (right rail — live system state)
Source: `shutdown/static/app.js`, `styles.css` `.state-panel`, `.kv`, `.gauge-*`, `.health*`, `.mod-now`

Sections top to bottom: **Current module** (pulsing dot + active stage name) → **Live state** (research round, hypothesis count, lead confidence, tokens, strategy version id, profile, model/backend) → **Research health** (a single 0–100 composite score, `.health-n`, with its formula spelled out in `.health-sub` so it can't be mistaken for a model-produced judgement) → **Metrics** (five labeled gauge bars: citation precision, source quality, fetch success, injection resistance, unsupported claims) → cost/approvals key-values.

```js
const health = report ? Math.round(100 * (
  0.3 * (report.citation_precision ?? 0) +
  0.2 * (1 - (report.unsupported_claim_rate ?? 0)) +
  0.2 * (report.prompt_injection_resistance ?? 0) +
  0.15 * (report.source_quality ?? 0) +
  0.15 * (report.browser_success ?? 0))) : null;
```
272px fixed width (250px ≤1500px), hidden entirely ≤1180px. Background `--s-1`, left border `--line`.

---

## MetaPanel (floating overlay — the meta plane)
Source: `shutdown/static/app.js`, `styles.css` `.scrim`, `.meta-panel`, `.meta-hd`, `.meta-body`, `.commit*`, `.bench*`, `.diffbox`

```js
function MetaPanel({ onClose, tickets, rollback, teacher }) {
  const [remote, setRemote] = useState(null);
  useEffect(() => { fetch("/api/strategies").then((r) => r.json()).then(setRemote).catch(() => {}); }, []);
  const versions = (remote?.versions || []).slice(0, 12);
  return html`
    <${React.Fragment}>
      <div class="scrim" onClick=${onClose}></div>
      <aside class="meta-panel" role="dialog" aria-label="Meta plane">
        <div class="meta-hd"> ... title + close button ... </div>
        <div class="meta-body">
          <!-- Teacher diagnosis (if present) -->
          <!-- Evolution tickets · held-out benchmark, one .commit-c per ticket -->
          <!-- Rollback history (if a rollback happened) -->
          <!-- Strategy timeline: git-commit-style vertical list, .commit + connecting line -->
        </div>
      </aside>
    <//>`;
}
```
Right-anchored slide-in panel (`slide-l` keyframe: translateX 28px→0 + scale .98→1), 560px max width, full-height minus 18px inset, over a dimming scrim (`#14161ab8`, blurred). Closes on scrim click or the header's close button. Fetches `/api/strategies` on mount for the version timeline. The "git-commit" visual language (small circular node + connecting vertical line + a code-styled card) is deliberate — strategy versions are literally a governed diff history, so it borrows the vocabulary of commit history.

---

## GraphView (Evidence Graph route)
Source: `shutdown/static/app.js`, `styles.css` `.graph-shell`, `.graph-legend`, `.graph-hint`

Canvas-based force-directed graph (`shutdown/static/graph.js`, `window.EvidenceGraph` class — hand-written physics, no d3/vis library). `GraphView` owns the canvas ref, instantiates `EvidenceGraph` once, and polls `/api/graph/{runId}` every 2.2s while a run is live to feed `setData()`. 480px fixed height, full-width panel with an overlaid legend (relation → color) and a hint string, bottom-left/top-right respectively.

---

## Composer (question input, top of Research workspace)
Source: `shutdown/static/app.js`, `styles.css` `.composer`, `.chip-btn`, `.run-btn`

```js
<div class="composer">
  <${SignalCanvas} />
  <textarea rows="3" value=${q} disabled=${running} placeholder="What claim should be tested? ..." onChange=${...} />
  <div class="composer-b">
    <div class="chip-btn ${file ? "set" : ""} ${over ? "over" : ""}" onClick=... onDragOver=... onDragLeave=... onDrop=...>
      <input type="file" accept="application/pdf" style="display:none" onChange=... />
      <${Icon} name=${file ? "doc" : "upload"} size=14 />
      ${file ? html`<span class="nm">${file.name}</span>` : html`<span>Attach PDF</span>`}
    </div>
    ${file && !running && html`<button class="ghost-btn" onClick=${() => setFile(null)}>remove</button>`}
    ${!running && !isDemo && html`<button class="ghost-btn" onClick=${...}><${Icon} name="satellite" size=13 /> Try the demo</button>`}
    <button class="run-btn" onClick=${launch} disabled=${running || !q.trim()}>
      <${Icon} name=${running ? "clock" : "hunt"} size=14 />
      ${running ? html`<span class="dots">Investigating</span>` : "Run investigation"}
    </button>
  </div>
</div>
```
A card containing: the ambient `SignalCanvas` (z-index 0, behind text), a plain `<textarea>` (no border, transparent), then a button row: drag-and-drop PDF attach chip (visual states: default dashed / `.over` while dragging / `.set` solid-green once a file is attached), a conditional "Try the demo" ghost button (only shown when the composer is empty/not already in demo mode), and the primary indigo "Run investigation" button (disabled while running or empty).
