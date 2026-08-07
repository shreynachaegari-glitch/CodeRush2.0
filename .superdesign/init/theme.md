# Theme — Shutdown Research OS

No Tailwind, no CSS-in-JS, no CSS modules. One hand-authored stylesheet, `shutdown/static/styles.css`, against a custom `:root` custom-property token system. Two web fonts vendored locally as woff2 (no CDN — `shutdown/static/vendor/inter.woff2`, `shutdown/static/vendor/sourceserif.woff2`), loaded via `@font-face`.

## Part 1 — Compact token summary

**Design direction (current, light mode):** clean white ground, near-black text (not pure black), exactly one restrained primary accent (indigo) for the control plane / primary actions, a second accent (violet) for the meta plane, and standard semantic red/amber/green held strictly to status meaning — never used decoratively. Radii are soft (8–22px), spacing is a strict 4px scale, and almost every "colored" surface (backgrounds, borders, shadows) is built from `color-mix(in srgb, var(--token) N%, transparent)` rather than a second hardcoded hex — so retinting is a one-line token edit, not a find/replace across the file.

The one signature visual (`.stamp`, see `components.md`) breaks this palette deliberately: rotated, serif, red ink — it is meant to look hand-applied, not themed.

### Color
| Token | Value | Role |
|---|---|---|
| `--s-0` | `#ffffff` | app ground / cards |
| `--s-1` | `#fafafa` | rail / panel ground |
| `--s-2` | `#ffffff` | raised card (same as s-0 currently) |
| `--s-3` | `#f1f2f5` | hover / input background |
| `--line` | `#e6e8eb` | default hairline border |
| `--line-2` | `#d6dade` | stronger border (hover, active) |
| `--fg` | `#171a1f` | primary text |
| `--fg-2` | `#5b626e` | secondary text |
| `--fg-3` | `#98a0ab` | tertiary / muted text |
| `--control` | `#3454d1` | **primary accent** — control plane, primary actions, links, focus ring |
| `--meta` | `#7c5cbf` | meta-plane accent (same value as `--violet`) |
| `--kill` | `#c23b2e` | the falsification stamp |
| `--ok` | `#1f8a55` | success / supports / promoted |
| `--warn` | `#b3790f` | caution / weakens / alive |
| `--bad` | `#c23b2e` | failure / refutes / eliminated (same value as `--kill`) |
| `--violet` | `#7c5cbf` | rollback / proposals |

### Type
- **Body/UI face:** Inter (variable, weights 100–900), vendored woff2. `font-size: 14px; line-height: 1.55; letter-spacing: -.006em` at the body level.
- **Signature/authority face:** "Source Serif" (weight 600 only), vendored woff2. Used in exactly two places: the falsification stamp (`.stamp-mark` 12.5px uppercase, `.stamp-body` 14.5px) and the verdict headline (`.verdict-a`, 19px/600). Fallback stack: `Georgia, "Times New Roman", serif`.
- **Data/mono face:** system stack `ui-monospace, "SF Mono", "Cascadia Mono", Consolas, monospace` — every number, id, timestamp, path, and JSON diff.
- Scale in practice: 10px section labels (uppercase, `.11–.13em` tracking) → 11–13px meta/captions → 14–15px body/card text → 19px verdict headline → 30px the one big number (`.health-n`, reasoning-health score).

### Layout
- Spacing scale: `--sp-1..7` = 4, 8, 12, 16, 24, 32, 48px.
- Radii: `--r-1..4` = 8, 12, 16, 22px.
- Shell: 3-column CSS grid, `216px 1fr 272px` (rail / work / state-panel), collapsing at 1180px and 780px breakpoints (see `layouts.md`).
- Motion: `--spring: cubic-bezier(.34, 1.4, .5, 1)` for anything entering/springing in; `--ease: cubic-bezier(.2, .8, .2, 1)` for value/property transitions. `prefers-reduced-motion: reduce` collapses all animation/transition durations to `.01ms` globally.

---

## Part 2 — Raw source

### `shutdown/static/styles.css` — `:root` token block
```css
:root {
  /* ── surface: paper white through light gray ── */
  --s-0: #ffffff;   /* app ground */
  --s-1: #fafafa;   /* rail / panel ground */
  --s-2: #ffffff;   /* raised card */
  --s-3: #f1f2f5;   /* hover / input */
  --line: #e6e8eb;
  --line-2: #d6dade;

  /* ── content: near-black, not pure black ── */
  --fg: #171a1f;
  --fg-2: #5b626e;
  --fg-3: #98a0ab;

  /* ── semantic. One accent per plane/state. ── */
  --control: #3454d1;   /* control plane — the hunt, primary actions */
  --meta: #7c5cbf;       /* meta plane — governance */
  --kill: #c23b2e;       /* the falsification stamp */
  --ok: #1f8a55;
  --warn: #b3790f;
  --bad: #c23b2e;
  --violet: #7c5cbf;

  --r-1: 8px; --r-2: 12px; --r-3: 16px; --r-4: 22px;

  /* 4px base spacing scale */
  --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px;
  --sp-5: 24px; --sp-6: 32px; --sp-7: 48px;

  --mono: ui-monospace, "SF Mono", "Cascadia Mono", Consolas, monospace;
  --serif: "Source Serif", Georgia, "Times New Roman", serif;
  --spring: cubic-bezier(.34, 1.4, .5, 1);
  --ease: cubic-bezier(.2, .8, .2, 1);

  --rail: 216px;
  --state: 272px;
}
```

### `@font-face` declarations
```css
@font-face {
  font-family: "Inter";
  src: url("/static/vendor/inter.woff2") format("woff2");
  font-weight: 100 900;
  font-display: swap;
}
@font-face {
  font-family: "Source Serif";
  src: url("/static/vendor/sourceserif.woff2") format("woff2");
  font-weight: 600;
  font-display: swap;
}
```

### Global element defaults
```css
* { box-sizing: border-box; }
html, body, #root { height: 100%; }
body {
  margin: 0; background: var(--s-0); color: var(--fg);
  font-family: Inter, -apple-system, "Segoe UI", sans-serif;
  font-size: 14px; line-height: 1.55; font-weight: 400;
  -webkit-font-smoothing: antialiased; letter-spacing: -.006em;
}
button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; }
a { color: var(--control); }
:focus-visible { outline: 2px solid var(--control); outline-offset: 2px; border-radius: 6px; }
```

### Full stylesheet
The complete current `shutdown/static/styles.css` (~540 lines) — read it directly from the repo path rather than duplicating it here; it is the single source of truth and changes frequently. Key selector groups, in file order: shell (`.os`, `.rail`, `.work`), composer (`.composer`, `.chip-btn`, `.run-btn`), pipeline (`.pipe`, `.pstage`, `.porb`), hypothesis card (`.hcard*`, `.stamp*`, `.kills`), tags (`.tag*`), graph (`.graph-*`), verdict (`.verdict*`), proposals (`.prop*`), agent cards (`.agents`, `.agent*`), meta plane (`.meta-*`, `.scrim`, `.commit*`, `.bench*`, `.diffbox`), state panel (`.state-panel`, `.kv`, `.gauge-*`, `.health*`, `.mod-now`), injection breach (`.breach*`), papers (`.paper`, `.cites`), comparison table (`.cmp*`), generic states (`.empty`, `.skel`, `.err-box`, `.feed`, `.runcard`).

### JS-side color constants (must stay in sync with the CSS tokens above)
`shutdown/static/app.js`:
```js
const OK = "#1f8a55", WARN = "#b3790f", BAD = "#c23b2e", META = "#7c5cbf", KILL = "#c23b2e", CONTROL = "#3454d1";
```
`shutdown/static/graph.js` (canvas force-graph, can't use CSS vars — plain 2D context fill/stroke):
```js
const REL = {
  supports:    { color: "#1f8a55", label: "supports" },
  weakens:     { color: "#b3790f", label: "weakens" },
  refutes:     { color: "#c23b2e", label: "refutes" },
  unknown:     { color: "#98a0ab", label: "unknown" },
  verified_by: { color: "#7c5cbf", label: "verified by" },
};
const STATUS = { survived: "#1f8a55", eliminated: "#c23b2e", alive: "#b3790f" };
```
`shutdown/static/signalfield.js` (WebGL uniform colors, RGB 0–1 float, matching `--control`/`--meta`):
```js
uAmber: { value: opts.amber || [0.204, 0.329, 0.820] },  /* --control indigo */
uCyan:  { value: opts.cyan  || [0.486, 0.361, 0.749] },  /* --meta violet */
```
