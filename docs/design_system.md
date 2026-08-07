# Shutdown — Research OS design system

The interface for an autonomous research agent has one job: make it legible that
*reasoning is happening*, and make the reasoning auditable. Everything below
serves that. Where a requested feature had no real data behind it, it is an
honest empty state rather than a mock — a fake number in a research tool is
worse than a blank.

---

## 1. Information architecture

```
Shutdown
├── Research          ← workspace: question → pipeline → hypotheses → verdict
├── Runs              ← every recorded investigation, its verdict and cost
├── Evidence Graph    ← claims / sources / verification as a live topology
├── Library           ← literature retrieved (OpenAlex + arXiv), with citations
├── Strategies        ← entry point to the Meta Plane
├── Memory            ← verdicts, proposals, rollback events  (browser: not built)
├── Reports           ← evaluation report + research package
└── Settings          ← backend/key configuration (via .env)

Meta Plane  ← deliberately NOT in the nav tree. A floating panel, reachable
              from anywhere, never interleaved with research content.
```

**Why the Meta Plane floats.** The control plane answers a question; the meta
plane changes the agent's own parameters. Mixing them in one scroll would imply
they carry the same authority. It overlays instead — you deliberately open the
thing that governs the system.

## 2. UX flow

```
ask ─→ attach (optional) ─→ run
                             │
        ┌────────────────────┴──────────────────┐
        │  framing → hunting ⇄ replan → verify  │   live, streamed over SSE
        └────────────────────┬──────────────────┘
                             ▼
              verdict ─→ proposals ─→ report
                             │
                    (meta plane, in parallel)
              teacher critique → ticket → benchmark
                             → approve | rollback
```

The pipeline is never a spinner. Each stage is a named module that lights,
pulses while working, and locks green — because "which module is running" is
information the user wants, and a spinner throws it away.

## 3. Wireframe (desktop, ≥1180px)

```
┌──────────┬──────────────────────────────────────────┬──────────────┐
│ 216px    │  Research workspace                      │  272px       │
│          │  ┌────────────────────────────────────┐  │              │
│ Shutdown │  │ composer: question + PDF + run     │  │ CURRENT      │
│          │  └────────────────────────────────────┘  │  MODULE      │
│ Research │  ○──○──○──○──○   pipeline               │  ● hunting   │
│ Runs     │                                          │              │
│ Graph    │  ⚠ injection refused @ page 1, §4.3      │ LIVE STATE   │
│ Library  │                                          │  round 2/3   │
│ Strategy │  ┌────────────────────────────────────┐  │  tokens      │
│ Memory   │  │ ◉ 62%  hypothesis ............... │  │  strategy    │
│ Reports  │  │        evidence rows (expandable) │  │              │
│          │  └────────────────────────────────────┘  │ HEALTH  94   │
│          │                                          │              │
│ Settings │  VERDICT · rulings · caveats             │ gauges…      │
└──────────┴──────────────────────────────────────────┴──────────────┘
                                       ( ● Meta Plane )  ← floating
```

**Responsive.** ≥1500px: full three-pane, ultrawide keeps the workspace centred
at max-width rather than stretching lines past comfortable measure. ≤1180px:
right panel drops, rail collapses to 64px icons. ≤780px: rail hides entirely.

## 4. Color — revision 2

**Signature element:** every hypothesis states what would prove it wrong. That
mechanic — not "an AI is reasoning" generically — is what a viewer should
remember, so the falsification target is stamped onto its card like a
case-file annotation: rotated -1.1°, `--serif` at 600 weight, oxide-red ink,
a faded double-rule border. It's the loudest thing on the card, louder than
the confidence ring next to it. See `.stamp` in `styles.css`.

Revision 1 of this system was near-black + a single amber accent — exactly
the AI-generated default the design brief warns against. Revised: surfaces
carry a faint green bias (instrument, not void), text is report-stock
parchment rather than pure white, and there are three accents each bound to
one plane/state rather than one arbitrary neon pop.

| Token | Value | Use |
|---|---|---|
| `--s-0` | `#0a0f0d` | app ground |
| `--s-1` | `#0d1310` | rail, panel |
| `--s-2` | `#131a16` | raised card |
| `--s-3` | `#19211c` | hover, input |
| `--line` / `--line-2` | `#212a24` / `#2c382f` | hairlines |
| `--fg` / `--fg-2` / `--fg-3` | `#e8e4d8` / `#a3ab9f` / `#647065` | text ramp (parchment, not white) |

| Token | Value | Meaning |
|---|---|---|
| `--control` | `#c98a3f` amber | control plane — the hunt, live/active |
| `--meta` | `#4a8a82` teal | meta plane — governance |
| `--kill` | `#b0402f` oxide red | the falsification stamp |
| `--ok` | `#6fae6f` | supports · survived · promoted |
| `--bad` | `#b0402f` | refutes · eliminated · blocked (same ink as the stamp — one failure vocabulary) |
| `--violet` | `#8c7aa8` | rollback · original proposals |

Semantic colors are separate from the accents and never used decoratively. No
neon, no gradients as identity — the one gradient is a 4% white sheen on glass.

## 5. Typography

Three roles, not two. **Inter** (vendored, 48KB variable woff2) carries UI
chrome, labels and body text — it's a neutral instrument face, deliberately
not asked to carry any personality. **Source Serif** (vendored, 21KB, weight
600) appears in exactly two places: the falsification stamp and the verdict
headline — the two moments the agent is asserting something rather than
logging a step. That contrast (clinical sans everywhere, one authoritative
serif at the moments that matter) is the typographic half of the signature.
Monospace (`ui-monospace`) for every number, id, path and diff.

| Role | Face | Size / weight | Notes |
|---|---|---|---|
| Page title | Inter | 19px / 650 | `-0.025em` tracking |
| **Stamp mark** | **Source Serif** | 12.5px / 600 | uppercase, `.08em`, oxide red |
| **Stamp body / verdict answer** | **Source Serif** | 14.5–19px / 400–600 | the only prose set in serif |
| Body | Inter | 14px / 400–450 | |
| Card text | Inter | 13–14px / 450 | |
| Meta, captions | Inter | 11.5–12.5px / 400 | `--fg-2` / `--fg-3` |
| Section label | Inter | 11px / 650 | uppercase, `.12em` |
| Numeric | mono | `tabular-nums` | columns must align |

Body tracking is `-0.006em` — Inter reads slightly loose at small sizes on dark.

## 6. Spacing

4px base scale: `4 · 8 · 12 · 16 · 24 · 32 · 48`. Radii: `8 / 12 / 16 / 22`.
Layout is flex/grid + `gap` throughout — never per-element margins that collapse
or double.

## 7. Component hierarchy

```
App
├── Rail            brand · nav · settings
├── Work (routed)
│   ├── Composer        textarea · DropZone · run
│   ├── Pipeline        Stage × 5 (idle|active|done)
│   ├── Breach          injection refusal
│   ├── Verdict         answer · Ruling × n · caveats
│   ├── Proposals       Proposal × n
│   ├── HypCard × n     Ring · meta · EvRow × n
│   ├── GraphView       canvas + legend
│   ├── Papers          Paper × n (citation counts)
│   └── Feed            activity log
├── StatePanel      module · live state · health · gauges
└── MetaPanel       teacher · tickets · rollback · timeline   (overlay)
```

## 8. Animation specification

Motion is only used where it carries meaning. Springs
(`cubic-bezier(.34,1.4,.5,1)`) for anything that enters; ease-out
(`cubic-bezier(.2,.8,.2,1)`) for anything that changes value.

| Element | Motion | What it means |
|---|---|---|
| Pipeline connector | `scaleX` 0→1, 450ms | reasoning flowed to the next module |
| Active orb | halo ripple, 1.9s loop | this module is working *now* |
| Stage complete | border → green, spring | locked in, not revisitable this round |
| Hypothesis card | rise + fade, 60ms stagger | claims arrive in order |
| Confidence ring | `stroke-dashoffset` 900ms + counting number | confidence *moved*, it wasn't always this |
| Evidence row | slide-in from left, 350ms | appended to a record |
| Graph edge | quadratic grown 0→1, 620ms cubic-out | this link was just discovered |
| Graph node | scale-in 500ms | entity entered the investigation |
| Injection breach | 500ms jolt + 3s scanning sweep | an attack was caught — it should feel like one |
| Benchmark bar | width 800ms ease | before → after comparison |
| Meta panel | slide + scale from right, 340ms spring | a separate system, overlaid |

No spinners anywhere. Loading is a shimmer skeleton or a named module pulsing.
All of it collapses under `prefers-reduced-motion: reduce`.

## 9. Evidence graph

Canvas 2D, hand-written force layout (~120 lines; d3 would have been a
dependency for three forces).

- **Nodes** — hypothesis (ring gauge showing confidence, colored by status),
  source (small circle), verification (cyan diamond)
- **Edges** — supports / weakens / refutes / unknown / verified-by, colored,
  refutes drawn heavier, unknown dashed
- **Forces** — centring pull, pairwise repulsion, spring along edges, 0.86 damping
- **Interaction** — hover dims everything unconnected and raises a tooltip;
  double-click a source opens it
- **Merge, never replace** — nodes keep positions across polls so the layout
  doesn't jump each time evidence lands

## 10. Interaction design

Hypothesis cards expand/collapse (click or Enter/Space, `role="button"`,
`tabIndex`). Cards lift 2px on hover with a shadow. Sources are real anchors
with `rel="noopener"`. Focus is always visible (2px amber, 2px offset). The
Meta Plane closes on scrim click.

## 11–14. States

**Empty** — every view has one, and views without backing data say so plainly:
Memory reads *"Verdicts, proposals and rollback events are already persisted
each run — this browser view is not implemented yet."* That is the truth, and it
is more useful than a fake table.

**Loading** — shimmer skeletons + the pulsing module name. Never a spinner.

**Error** — rate limiting is detected specifically and rendered as an
actionable message with the two real fixes (`NVIDIA_API_KEY`,
`SHUTDOWN_OFFLINE=1`), not a provider stack trace.

**Honest-degradation states** — the verdict is labelled *"derived (no model
synthesis)"* when it fell back to arithmetic, and the teacher critique is
labelled *"derived"* vs *"model-authored"*. The user always knows whether a
model reasoned or a fallback fired.

## 15. What this deliberately does not do

- No fabricated metrics. "Reasoning health" is a composite of five metrics we
  actually measure, and the panel names its inputs so it can't be read as a
  model-produced judgement.
- No hallucination-risk score — we have no calibrated way to measure it, so
  claiming one would be dishonest.
- Memory browser, Settings editor and Approval Queue interactivity are not
  built; they are labelled as such.
