# Design System — Shutdown Onboarding Flow (landing + upload)

## Product context
Shutdown is a falsification-driven research agent (CodeRush 2.0, AE-02): it frames competing hypotheses, actively hunts for evidence that would prove each one *wrong*, and only self-improves through a governed, human-approved, rollback-able loop. The main product is a three-pane "Research OS" (`shutdown/static/`) with its own light, restrained design system (white ground, indigo/violet accents, documented in `.superdesign/init/theme.md`).

**This design system is deliberately separate from that one.** It covers exactly two new pages that sit *in front of* the Research OS as an entry flow:

1. **Landing** — project name, a one-to-two-line description, one CTA. Nothing else.
2. **Upload** — a file-drop page where the user hands over the document(s) they want investigated, which then carries into the existing Research OS workspace (the composer's existing PDF-attach flow, `shutdown/static/app.js`).

The user explicitly chose a distinct dark/neon identity for these two pages rather than reusing the main app's light system — these are the "hook" before the instrument-panel product, closer to a mission-briefing / signal-intercept moment than a SaaS dashboard.

## Visual direction
Dark, atmospheric, cinematic — a moment of arrival, not a form. Full-bleed animated backgrounds carry the emotional weight; UI chrome stays minimal (one headline, one line of copy, one button on the landing page; a drop zone and minimal instructions on the upload page).

## Color
| Token | Value | Role |
|---|---|---|
| `bg` | `#08060d` | page ground — near-black, faint violet bias |
| `panel` | `#120f1c` | any raised surface (drop zone, cards) |
| `line` | `#2a2438` | hairline borders on dark |
| `fg` | `#f4f0fb` | primary text — soft white, not pure |
| `fg-dim` | `#9d94b8` | secondary text |
| `violet` | `#5227FF` | primary accent — tunnel core, primary button |
| `magenta` | `#A855F7` | secondary accent — cable/pulse glow, hover states |
| `pink` | `#fc42ff` | MagicRings ring color one (upload page) |
| `cyan` | `#42fcff` | MagicRings ring color two (upload page) |

These are the LightTunnel/MagicRings components' own default palette, kept rather than reworked — the brief calls for their look specifically, not a Shutdown-brand recolor.

## Typography
- Display/headline (project name): a bold, wide-tracked sans or a masked/reveal heading treatment — animated in on load (mask-reveal or fade+rise), not static. This is the one moment on the page allowed a flourish.
- Body/description: clean sans, generous line-height, kept short (1-2 lines max — the brief is explicit that nothing else belongs on the landing page).
- UI/buttons: same sans, medium weight, wide letter-spacing on the CTA label.

## Motion
- **Landing**: `LightTunnel` full-bleed background (converging fiber-optic cables with traveling light pulses, violet/magenta) — see `.superdesign/init/components.md` "SignalCanvas" for how the analogous effect is already wired into the main app (WebGL2, `ogl`, pause off-screen/hidden-tab, `prefers-reduced-motion` respected — same engineering discipline applies here). Headline reveals on load; CTA has a subtle hover lift/glow.
- **Upload**: `MagicRings` background (concentric pulsing rings, pink→cyan) behind or around the drop zone. Drop zone gives clear visual feedback on drag-over (per the existing `.chip-btn.over` pattern in the main app) and on a file being attached.
- Both effects must degrade gracefully (no WebGL2 → static gradient fallback, reduced-motion → static frame) — same standard as the rest of the app.

## Layout
- Landing: single centered column, vertically centered in the viewport. Name → description → CTA, stacked, generous vertical rhythm. No nav, no footer, no secondary content.
- Upload: centered drop zone (large target area, dashed/glowing border), a one-line instruction above it, minimal supporting copy below (what happens next). No nav chrome — this is still pre-app.

## What NOT to do
- Do not pull in the main Research OS's light-mode chrome (rail nav, state panel, etc.) — these two pages precede that shell entirely.
- Do not add extra sections, testimonials, feature lists, or navigation to the landing page — brief is explicit: name + 1-2 line description + CTA, nothing else.
- Do not invent survey/form fields on the upload page — it is a file drop only, no questions.
