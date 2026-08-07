/* Iconsax-style icon set: 24px grid, 1.5 stroke, round caps/joins, linear
   outline. Hand-authored inline SVG rather than an icon package -- keeps the
   app dependency-free and offline, and every glyph here is one we actually use. */
(function () {
  const h = React.createElement;

  const wrap = (size, children, extra) =>
    h("svg", Object.assign({
      width: size, height: size, viewBox: "0 0 24 24", fill: "none",
      stroke: "currentColor", strokeWidth: 1.5,
      strokeLinecap: "round", strokeLinejoin: "round",
      "aria-hidden": "true", focusable: "false",
    }, extra || {}), children);

  const P = (d) => h("path", { key: d, d: d });
  const C = (cx, cy, r) => h("circle", { key: `${cx}${cy}${r}`, cx, cy, r });

  const paths = {
    // hypothesis framing — branching possibilities
    branch: [P("M6 3v6a3 3 0 0 0 3 3h9"), P("M6 21v-6"), C(6, 4, 0.01), C(18, 12, 3), C(6, 18, 3)],
    // contradiction hunting — a search that's looking for trouble
    hunt: [C(11, 11, 7), P("M20 20l-3.5-3.5"), P("M8.5 11h5"), P("M11 8.5v5")],
    // verification — sandboxed recompute
    beaker: [P("M9 3v6.5L4.5 17A2.5 2.5 0 0 0 6.7 21h10.6a2.5 2.5 0 0 0 2.2-4L15 9.5V3"), P("M8 3h8"), P("M7.5 15h9")],
    // evolution — the meta plane
    dna: [P("M7 3c0 5 10 5 10 10S7 18 7 21"), P("M17 3c0 5-10 5-10 10s10 5 10 8"), P("M8.5 7.5h7"), P("M8.5 16.5h7")],
    // verdict — the gavel/seal
    seal: [C(12, 9, 6), P("M9 14.5 8 21l4-2 4 2-1-6.5")],
    // shield — injection blocked
    shield: [P("M12 22s8-4 8-10V5.5L12 2 4 5.5V12c0 6 8 10 8 10z"), P("M9.5 12l1.8 1.8 3.5-3.6")],
    shieldAlert: [P("M12 22s8-4 8-10V5.5L12 2 4 5.5V12c0 6 8 10 8 10z"), P("M12 8v4.5"), P("M12 16h.01")],
    // document
    doc: [P("M14 2v5a1 1 0 0 0 1 1h5"), P("M19 9v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 6z"), P("M9 13h6"), P("M9 17h4")],
    upload: [P("M12 15V3"), P("M8.5 6.5 12 3l3.5 3.5"), P("M21 15v3a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3v-3")],
    // globe — web source
    globe: [C(12, 12, 9), P("M3.5 9h17"), P("M3.5 15h17"), P("M12 3a14 14 0 0 1 0 18"), P("M12 3a14 14 0 0 0 0 18")],
    // database — structured dataset
    database: [h("ellipse", { key: "e", cx: 12, cy: 6, rx: 7.5, ry: 3 }), P("M4.5 6v12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6"), P("M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3")],
    // terminal — code output
    terminal: [h("rect", { key: "r", x: 3, y: 4, width: 18, height: 16, rx: 2.5 }), P("M7.5 9.5 10 12l-2.5 2.5"), P("M13 15h4")],
    check: [P("M4.5 12.5 9 17l10.5-10.5")],
    x: [P("M6 6l12 12"), P("M18 6 6 18")],
    // replan — loop back
    loop: [P("M4 9a6 6 0 0 1 6-6h5"), P("M12.5 0.5 15.5 3l-3 2.5"), P("M20 15a6 6 0 0 1-6 6H9"), P("M11.5 18.5 8.5 21l3 2.5")],
    // rollback
    rewind: [P("M20 12a8 8 0 1 1-2.5-5.8"), P("M20 3v4h-4")],
    bolt: [P("M13 2 4.5 13.5H11L10 22l8.5-11.5H12L13 2z")],
    clock: [C(12, 12, 9), P("M12 7.5V12l3 1.8")],
    coin: [C(12, 12, 9), P("M12 7v10"), P("M14.5 9.5c-.5-1-3.5-1.4-4.3-.2-.9 1.3.6 2 1.8 2.3 1.2.3 2.9.8 2.4 2.3-.5 1.4-3.6 1.4-4.4.1")],
    user: [C(12, 8, 3.5), P("M4.5 20.5c1-3.5 4-5 7.5-5s6.5 1.5 7.5 5")],
    spark: [P("M12 3v3"), P("M12 18v3"), P("M3 12h3"), P("M18 12h3"), P("M5.6 5.6l2.1 2.1"), P("M16.3 16.3l2.1 2.1"), P("M18.4 5.6l-2.1 2.1"), P("M7.7 16.3l-2.1 2.1"), C(12, 12, 3)],
    link: [P("M10 13.5a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7L11.5 6.3"), P("M14 10.5a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.5-1.5")],
    satellite: [P("M7 12 3.5 8.5 8 4l3.5 3.5"), P("M12.5 16.5 16 20l4.5-4.5L17 12"), P("M9 14l-2.5 2.5"), P("M15 10 17.5 7.5"), C(12, 12, 2.5), P("M18 6.5a4 4 0 0 1 0 5.5")],
    // nav
    runs: [P("M4 6h16"), P("M4 12h16"), P("M4 18h10"), C(19.5, 18, 1.8)],
    library: [P("M5 4v16"), P("M9 4v16"), P("M13.5 4.6 12.8 20"), P("M17.6 5.2 20 19.6"), P("M3.5 20h17")],
    graph: [C(6, 17, 2.5), C(12, 7, 2.5), C(18.5, 15, 2.5), P("M7.6 15.2 10.6 9.2"), P("M14.2 8.4l3 4.6")],
    strategies: [C(6.5, 6, 2.5), C(6.5, 18, 2.5), C(17.5, 12, 2.5), P("M6.5 8.5v7"), P("M9 6.6c5 .6 6 2.4 6.2 4.2"), P("M9 17.4c5-.6 6-2.4 6.2-4.2")],
    memory: [P("M9 3v2"), P("M15 3v2"), P("M9 19v2"), P("M15 19v2"), P("M3 9h2"), P("M3 15h2"), P("M19 9h2"), P("M19 15h2"), h("rect", { key: "r", x: 5, y: 5, width: 14, height: 14, rx: 3 }), h("rect", { key: "r2", x: 9, y: 9, width: 6, height: 6, rx: 1.4 })],
    reports: [P("M14 2v5a1 1 0 0 0 1 1h5"), P("M19 9v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 6z"), P("M9 17v-3"), P("M12 17v-5"), P("M15 17v-2")],
    settings: [C(12, 12, 3), P("M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.5 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H1.6a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 3.3 7.5a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H8a1.6 1.6 0 0 0 1-1.5V1.6a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V8a1.6 1.6 0 0 0 1.5 1H22a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z")],
    teacher: [P("M12 3 2 8l10 5 10-5-10-5z"), P("M5.5 10v5c0 1.7 3 3 6.5 3s6.5-1.3 6.5-3v-5"), P("M22 8v6")],
    idea: [P("M9.5 18h5"), P("M10 21h4"), P("M12 3a6 6 0 0 0-3.5 10.9c.4.3.6.8.6 1.3v.3h5.8v-.3c0-.5.2-1 .6-1.3A6 6 0 0 0 12 3z")],
    paper: [P("M14 2v5a1 1 0 0 0 1 1h5"), P("M19 9v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 6z"), P("M8.5 12h7"), P("M8.5 15.5h5")],
    quote: [P("M9 11H5.5a1 1 0 0 1-1-1V7.5a1 1 0 0 1 1-1H8a1 1 0 0 1 1 1V13c0 2.2-1.2 3.6-3 4.2"), P("M19.5 11H16a1 1 0 0 1-1-1V7.5a1 1 0 0 1 1-1h2.5a1 1 0 0 1 1 1V13c0 2.2-1.2 3.6-3 4.2")],
    close: [P("M6 6l12 12"), P("M18 6 6 18")],
    chevron: [P("M9 6l6 6-6 6")],
  };

  window.Icon = function Icon({ name, size = 18, ...rest }) {
    const d = paths[name];
    if (!d) return null;
    return wrap(size, d, rest);
  };
})();
