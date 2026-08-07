# Extractable components — Shutdown Research OS

Components worth extracting as reusable Superdesign `DraftComponent` entities — appear on multiple views or define a shared UI pattern. Full source for each is in `components.md` / `layouts.md`.

## Layout Components (appear on most/all pages)

## Rail
- Source: `shutdown/static/app.js` (inline in `App()`, not its own function — extract as `<nav class="rail">...</nav>`)
- Category: layout
- Description: Left navigation — brand mark, 7-item nav list, Settings footer button. Present on every view.
- Extractable props: `activeView` (string, one of `workspace|runs|graph|library|strategies|memory|reports`, default `"workspace"`), `runsCount` (number, default 0 — drives the Runs badge), `papersCount` (number, default 0 — drives the Library badge)
- Hardcoded: brand name "Shutdown" / "Research OS" subtitle, the 7 nav items' labels+icons+order, satellite icon as the brand mark

## StatePanel
- Source: `shutdown/static/app.js` `StatePanel()`
- Category: layout
- Description: Right-hand persistent rail showing current agent, live run stats, a composite "reasoning health" score, and five metric gauges. Present on every view (≥1180px).
- Extractable props: `running` (boolean), `currentModuleLabel` (string | null), `round`/`hyps.length`/`tokens`/`strategyId`/`backendLabel` (the live-state values), `report` (object | null — gates whether health/metrics sections render at all)
- Hardcoded: section labels, the health-score weighting formula text, the five metric labels/order

## MetaPanel
- Source: `shutdown/static/app.js` `MetaPanel()`
- Category: layout (overlay)
- Description: Right-anchored slide-in panel + scrim showing the governed self-improvement history — teacher critique, evolution tickets with held-out benchmark bars, rollback events, and a git-commit-style strategy version timeline.
- Extractable props: `open` (boolean), `tickets` (array), `rollback` (object | null), `teacher` (object | null)
- Hardcoded: "Meta Plane" title/subtitle, section order, the commit-timeline visual metaphor

## Meta plane FAB
- Source: `shutdown/static/app.js` `.meta-fab` (inline button in `App()`)
- Category: layout
- Description: Floating pill button, bottom-right, opens `MetaPanel`. Deliberately outside the main nav — signals "this governs the agent, it isn't a content page."
- Extractable props: `ticketCount` (number, default 0)
- Hardcoded: "Meta Plane" label, teal status dot

## Basic / content components (used across pages or repeated within one)

## HypCard
- Source: `shutdown/static/app.js` `HypCard()`
- Category: basic
- Description: The primary content card — a falsifiable hypothesis with a confidence ring, status/ruling tags, an evidence count, an expandable evidence list, and (the signature element) a rotated red-ink "falsified by" stamp.
- Extractable props: `statement` (string), `confidence` (number 0–1), `status` (`alive|survived|eliminated`), `ruling` (`supported|falsified|undetermined` | null), `killsIt` (string | null — the falsification target text), `why` (string | null), `evidenceCount` (number), `contradictionCount` (number), `lead` (boolean — highlights as the current front-runner), `open` (boolean, expand state)
- Hardcoded: "✕ falsified by" label text, chevron rotation on expand, stagger animation delay formula

## Ring
- Source: `shutdown/static/app.js` `Ring()`
- Category: basic
- Description: Small SVG circular confidence gauge with an animated count-up number in the center.
- Extractable props: `value` (number 0–1), `status` (drives ring color via the shared `hue()` mapping), `size` (number, default 46)
- Hardcoded: track color `#e6e8eb`, stroke width 3, count-up duration 800ms

## AgentCards (5-card grid)
- Source: `shutdown/static/app.js` `AgentCards()`
- Category: basic
- Description: One card per pipeline agent (Hypothesis Framer, Contradiction Hunter, Verification Agent, Strategy Evaluator, Verdict Synthesizer) showing name, role, a status tag, and a live one-line status pulled from the event stream.
- Extractable props: `agents` (array of `{ id, name, role, icon }` — currently a fixed constant, but extractable if agent roster ever varies), `stageStatus` (map of agent id → `idle|active|done`), `activity` (map of agent id → current status string)
- Hardcoded: the 5 agent identities/roles/order, "waiting"/"working"/"complete" fallback copy

## Pipeline (connector row)
- Source: `shutdown/static/app.js` `Pipeline()`
- Category: basic
- Description: Compact 5-node horizontal progress indicator, sits above `AgentCards` as a denser summary of the same state.
- Extractable props: same `stageStatus` map as `AgentCards`
- Hardcoded: the 5 stage labels/icons/order (kept in sync with `AGENTS` manually — two separate constants, `STAGES` and `AGENTS`)

## Tag
- Source: `shutdown/static/app.js` `Tag()`
- Category: basic
- Description: Small uppercase mono status pill, ~12 semantic variants (supports/refutes/weakens/alive/survived/eliminated/undetermined/unknown/meta/substantive/supported/falsified).
- Extractable props: `variant` (string, the `k` prop — selects the CSS modifier class), `children` (label text)
- Hardcoded: none — fully generic, color comes entirely from the variant→CSS mapping

## EvRow
- Source: `shutdown/static/app.js` `EvRow()`
- Category: basic
- Description: One evidence citation row inside an expanded `HypCard` — source-type icon, reason text, source link/locator, relation tag.
- Extractable props: `sourceType` (drives icon), `reason` (string), `source` (URL or path string), `locator` (string | null, e.g. "page 4, §2.1"), `relation` (drives the trailing `Tag`)
- Hardcoded: URL-detection regex for whether `source` renders as a link

## Composer
- Source: `shutdown/static/app.js` (inline, top of `WORK.workspace()`)
- Category: basic
- Description: The question textarea + drag-and-drop PDF attach chip + "Try the demo" ghost button + primary "Run investigation" button, with the ambient `SignalCanvas` behind it.
- Extractable props: `value` (string), `disabled` (boolean, while running), `fileName` (string | null), `dragOver` (boolean), `isDemoMode` (boolean)
- Hardcoded: placeholder copy, demo-mode explanatory caption, PDF-only file accept filter

## Breach (injection alert)
- Source: `shutdown/static/app.js` `Breach()`
- Category: basic
- Description: Full-width alert card shown when a prompt-injection attempt is caught in a fetched document/source — shows the source+locator, a highlighted excerpt (the matched phrase wrapped in `<mark>`), and a "logged, never executed" confirmation line.
- Extractable props: `source` (string), `locator` (string | null), `detail` (string — contains the matched pattern, parsed via regex), `excerpt` (string | null)
- Hardcoded: the three-line copy structure (headline / source-locator / confirmation), the `jolt` entrance + `sweep` ambient animation

## Stub (empty state)
- Source: `shutdown/static/app.js` `Stub()`
- Category: basic
- Description: Generic centered empty-state block — icon, title, one-line description. Used for every "not built yet" or "nothing recorded yet" page.
- Extractable props: `icon` (icon name), `title` (string), `body` (string)
- Hardcoded: none — fully generic
