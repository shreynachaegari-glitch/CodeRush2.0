# Components — Shutdown Research OS

**Stack:** vanilla JS, React + `htm` tagged templates (no JSX, no build step — `shutdown/static/app.js` is the exact file that runs in the browser). No component library, no CSS framework — hand-authored CSS in `shutdown/static/styles.css` against a custom token system. All components live in one file, `shutdown/static/app.js`, as plain functions (not separate files/modules).

Icons are hand-authored inline SVG (`shutdown/static/icons.js`), Iconsax-style: 24px grid, 1.5 stroke, round caps/joins — not an icon package.

---

## Icon
Source: `shutdown/static/icons.js`

```js
window.Icon = function Icon({ name, size = 18, ...rest }) {
  const d = paths[name];
  if (!d) return null;
  return wrap(size, d, rest);
};
// wrap() renders an <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
// stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"> containing
// the named path/circle primitives. ~40 named icons: branch, hunt, beaker, dna,
// seal, shield, shieldAlert, doc, upload, globe, database, terminal, check, x,
// loop, rewind, bolt, clock, coin, user, spark, link, satellite, runs, library,
// graph, strategies, memory, reports, settings, teacher, idea, paper, quote,
// close, chevron.
```
Usage: `<${Icon} name="hunt" size=15 style=${{ color: WARN }} />`

---

## Tag
Source: `shutdown/static/app.js`, `styles.css` `.tag` / `.tag-*`

```js
const Tag = ({ k, children }) => html`<span class="tag tag-${k}">${children}</span>`;
```
`k` selects a semantic variant: `supports`/`supported` (green), `refutes`/`falsified`/`eliminated` (red), `weakens`/`alive`/`undetermined` (amber), `unknown` (gray), `survived` (green), `meta` (violet), `substantive` (violet). Small uppercase mono pill, used everywhere a status/relation needs a compact label.

---

## Ring (confidence gauge)
Source: `shutdown/static/app.js`

```js
function Ring({ value, status, size = 46 }) {
  const v = useCountUp(value);
  const r = size / 2 - 3.5, C = 2 * Math.PI * r, col = hue(status);
  return html`
    <div class="ring" style=${{ width: size, height: size }}>
      <svg width=${size} height=${size}>
        <circle cx=${size / 2} cy=${size / 2} r=${r} fill="none" stroke="#e6e8eb" stroke-width="3" />
        <circle cx=${size / 2} cy=${size / 2} r=${r} fill="none" stroke=${col} stroke-width="3"
                stroke-linecap="round" stroke-dasharray=${C} stroke-dashoffset=${C * (1 - v)} />
      </svg>
      <span class="rv" style=${{ color: col }}>${Math.round(v * 100)}</span>
    </div>`;
}
```
An SVG circular progress ring showing a hypothesis's confidence (0–1), colored by status via the `hue()` helper (`OK` green if survived/supported, `BAD` red if eliminated/falsified, `WARN` amber otherwise). `useCountUp` animates the displayed number toward its target over 800ms (cubic ease-out) rather than snapping — "a confidence figure should read as something that moved."

```js
function useCountUp(target, ms = 800) {
  const [v, setV] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const a = from.current, b = target;
    if (a === b) return;
    const t0 = performance.now();
    let raf;
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / ms);
      setV(a + (b - a) * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(tick); else from.current = b;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}
```

---

## HypCard (hypothesis card) — the primary content unit
Source: `shutdown/static/app.js`, `styles.css` `.hcard*`, `.stamp*`, `.kills`

```js
function HypCard({ h, evidence, rank, lead, open, onToggle }) {
  const refutes = evidence.filter((e) => e.relation === "refutes").length;
  return html`
    <div class="hcard ${lead ? "lead" : ""} ${h.status === "eliminated" ? "dead" : ""}"
         style=${{ animationDelay: `${rank * 60}ms` }}>
      <div class="hcard-b" onClick=${onToggle} role="button" tabIndex=${0}
           onKeyDown=${(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onToggle())}>
        <${Ring} value=${h.confidence ?? 0} status=${h.status} />
        <div>
          <div class="hcard-txt">${h.statement}</div>
          <div class="hcard-meta">
            <${Tag} k=${h.status}>${h.status}<//>
            <span class="dot"></span><span>${evidence.length} evidence</span>
            ${refutes > 0 && html`<span class="dot"></span><span style=${{ color: BAD }}>${refutes} contradiction${refutes > 1 ? "s" : ""}</span>`}
            ${h.ruling && html`<${Tag} k=${h.ruling}>${h.ruling}<//>`}
          </div>
          ${open && h.kills_it && html`
            <div class="stamp">
              <span class="stamp-mark">✕ falsified by</span>
              <span class="stamp-body">${h.kills_it}</span>
            </div>`}
          ${h.why && html`<div class="kills" style=${{ borderLeftColor: hue(h.ruling) }}>${h.why}</div>`}
        </div>
        <${Icon} name="chevron" size=15 style=${{ color: "var(--fg-3)", transform: open ? "rotate(90deg)" : "", transition: "transform .25s" }} />
      </div>
      ${open && evidence.length > 0 && html`
        <div class="ev-list">${evidence.map((e, i) => html`<${EvRow} e=${e} key=${i} />`)}</div>`}
    </div>`;
}
```

**The signature element is `.stamp`** — the falsification target ("what would prove this claim wrong") rendered as a case-file rubber-stamp: rotated -1.1°, serif type (`--serif`, the only place besides the verdict headline that this face is used), red ink (`--kill`), a faded double-rule border via `::before`, animated in with a `stamp-hit` keyframe (scale 1.5→0.96→1, opacity 0→1). It is deliberately louder than the confidence ring next to it — it's the one thing this tool does that a generic AI dashboard doesn't.

Expand/collapse toggles the evidence list beneath the card. Cards animate in with a staggered `lift-in` (60ms × rank).

---

## EvRow (evidence row)
Source: `shutdown/static/app.js`, `styles.css` `.ev-row`, `.ev-t`, `.ev-c`, `.locpill`

```js
const EvRow = ({ e }) => {
  const isUrl = /^https?:/.test(e.source || "");
  return html`
    <div class="ev-row">
      <span class="eic"><${Icon} name=${SRC_ICON[e.source_type] || "doc"} size=14 /></span>
      <div style=${{ minWidth: 0 }}>
        <div class="ev-t">${e.reason}</div>
        <div class="ev-c">${isUrl ? html`<a href=${e.source} target="_blank" rel="noopener noreferrer">${shortSrc(e.source)}</a>` : shortSrc(e.source)}</div>
        ${e.locator && html`<span class="locpill"><${Icon} name="doc" size=10 /> ${e.locator}</span>`}
      </div>
      <${Tag} k=${e.relation}>${e.relation}<//>
    </div>`;
};
```
`SRC_ICON` maps source type → icon: `{ pdf: "doc", paper: "paper", dataset: "database", web: "globe", code_output: "terminal", inline: "doc" }`. One row per piece of evidence inside an expanded `HypCard`.

---

## Stub (empty state)
Source: `shutdown/static/app.js`, `styles.css` `.empty`

```js
const Stub = ({ icon, title, body }) => html`
  <div class="empty">
    <div class="ei"><${Icon} name=${icon} size=28 /></div>
    <div class="et">${title}</div>
    <div class="ed">${body}</div>
  </div>`;
```
Used for every "nothing here yet" view (Runs, Reports, Library, Strategies, Memory, Settings). Honest, not decorative — copy states plainly when something isn't built yet rather than showing mock content.

---

## AgentCards + Pipeline (per-agent progress)
Full source and rationale in `layouts.md` (they're structural, driving the main workspace flow, not a leaf primitive) — cross-referenced here because they are the primary "component" a redesign is likely to touch. Five fixed agent identities: Hypothesis Framer, Contradiction Hunter, Verification Agent, Strategy Evaluator, Verdict Synthesizer.

## SignalCanvas (ambient background)
```js
function SignalCanvas() {
  const ref = useRef(null);
  useEffect(() => {
    let handle = null, cancelled = false;
    import("/static/signalfield.js").then(({ mountSignalField }) => {
      if (cancelled || !ref.current) return;
      handle = mountSignalField(ref.current, { density: 18, speed: 0.45, opacity: 0.85 });
    }).catch(() => {});
    return () => { cancelled = true; handle && handle.stop(); };
  }, []);
  return html`<canvas class="signal-canvas" ref=${ref} aria-hidden="true"></canvas>`;
}
```
Mounted behind the question composer only. A WebGL2 (`ogl`, vendored, ~5KB) fragment shader rendering converging signal lines that pulse toward a focal point — "evidence flowing toward a verdict." Colored indigo/violet to match `--control`/`--meta`. Fails silently (renders nothing) if WebGL2 is unavailable. Full shader in `shutdown/static/signalfield.js`.
