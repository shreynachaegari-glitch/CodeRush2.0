/* Shutdown — Research OS.
   React via htm tagged templates: no JSX build step, so the file you read is
   the file that runs. */
(function () {
  const { useState, useEffect, useRef, useCallback, useMemo } = React;
  const html = htm.bind(React.createElement);
  const Icon = window.Icon;
  let _motion = null;
  const motion = () => (_motion ||= import("/static/motion.js"));

  /* Ambient WebGL background for the composer, adapted from the
     shader-background technique (ogl + a fragment shader driven by a few
     uniforms) into Shutdown's own visual language -- see signalfield.js for
     the full rationale. Mounts a canvas behind the composer and tears it
     down on unmount; any failure (no WebGL2) degrades to a plain panel. */
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

  const STAGES = [
    { id: "framing",   label: "Framing",      icon: "branch" },
    { id: "hunting",   label: "Hunting",      icon: "hunt" },
    { id: "verifying", label: "Verification", icon: "beaker" },
    { id: "evolving",  label: "Evolution",    icon: "dna" },
    { id: "verdict",   label: "Verdict",      icon: "seal" },
  ];
  const NAV = [
    { id: "workspace",  label: "Research",        icon: "hunt" },
    { id: "runs",       label: "Runs",            icon: "runs" },
    { id: "graph",      label: "Evidence Graph",  icon: "graph" },
    { id: "library",    label: "Library",         icon: "library" },
    { id: "strategies", label: "Strategies",      icon: "strategies" },
    { id: "memory",     label: "Memory",          icon: "memory" },
    { id: "reports",    label: "Reports",         icon: "reports" },
  ];
  const SRC_ICON = { pdf: "doc", paper: "paper", dataset: "database", web: "globe", code_output: "terminal", inline: "doc" };
  const OK = "#5ec98a", WARN = "#e0a942", BAD = "#ef6a80", META = "#4cc4dd";

  const hue = (s) => (s === "survived" || s === "supported" ? OK
                    : s === "eliminated" || s === "falsified" ? BAD : WARN);

  function shortSrc(s) {
    if (!s) return "";
    if (s.startsWith("sandbox://")) return s;
    if (/^https?:/.test(s)) {
      try { const u = new URL(s); return u.hostname.replace(/^www\./, "") + (u.pathname.length > 1 ? u.pathname.slice(0, 22) : ""); }
      catch { return s; }
    }
    return s.split(/[\\/]/).pop();
  }

  /* Numbers count rather than snap: a confidence figure should read as
     something that moved. */
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

  const Tag = ({ k, children }) => html`<span class="tag tag-${k}">${children}</span>`;

  function Ring({ value, status, size = 46 }) {
    const v = useCountUp(value);
    const r = size / 2 - 3.5, C = 2 * Math.PI * r, col = hue(status);
    return html`
      <div class="ring" style=${{ width: size, height: size }}>
        <svg width=${size} height=${size}>
          <circle cx=${size / 2} cy=${size / 2} r=${r} fill="none" stroke="#1c2330" stroke-width="3" />
          <circle cx=${size / 2} cy=${size / 2} r=${r} fill="none" stroke=${col} stroke-width="3"
                  stroke-linecap="round" stroke-dasharray=${C} stroke-dashoffset=${C * (1 - v)} />
        </svg>
        <span class="rv" style=${{ color: col }}>${Math.round(v * 100)}</span>
      </div>`;
  }

  /* ── pipeline ─────────────────────────────────────────── */
  const Pipeline = ({ stages }) => html`
    <div class="pipe">
      ${STAGES.map((s, i) => {
        const st = stages[s.id] || "idle";
        const flowed = i > 0 && stages[STAGES[i - 1].id] === "done";
        return html`
          <div class="pstage ${st} ${flowed ? "flowed" : ""}" key=${s.id}>
            <div class="porb"><${Icon} name=${st === "done" ? "check" : s.icon} size=15 /></div>
            <div class="pl">${s.label}</div>
          </div>`;
      })}
    </div>`;

  /* ── evidence + hypothesis ────────────────────────────── */
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
            ${open && h.kills_it && html`<div class="kills"><b>Falsified by:</b> ${h.kills_it}</div>`}
            ${h.why && html`<div class="kills" style=${{ borderLeftColor: hue(h.ruling) }}>${h.why}</div>`}
          </div>
          <${Icon} name="chevron" size=15 style=${{ color: "var(--fg-3)", transform: open ? "rotate(90deg)" : "", transition: "transform .25s" }} />
        </div>
        ${open && evidence.length > 0 && html`
          <div class="ev-list">${evidence.map((e, i) => html`<${EvRow} e=${e} key=${i} />`)}</div>`}
      </div>`;
  }

  const Breach = ({ a }) => {
    const phrase = (a.detail.match(/'(.+)'/) || [])[1];
    let body = a.excerpt;
    if (phrase && a.excerpt) {
      const i = a.excerpt.toLowerCase().indexOf(phrase.toLowerCase());
      if (i >= 0) body = html`${a.excerpt.slice(0, i)}<mark>${a.excerpt.substr(i, phrase.length)}</mark>${a.excerpt.slice(i + phrase.length)}`;
    }
    return html`
      <div class="breach">
        <div class="breach-h"><${Icon} name="shieldAlert" size=17 /> Prompt injection found and refused</div>
        <div class="breach-s">${shortSrc(a.source)}${a.locator ? html` — <b>${a.locator}</b>` : null}</div>
        ${a.excerpt && html`<div class="breach-q">${body}</div>`}
        <div class="breach-v"><${Icon} name="shield" size=14 /> Logged as evidence. Never executed, never trusted as instructions.</div>
      </div>`;
  };

  /* ── graph view ───────────────────────────────────────── */
  function GraphView({ runId, live }) {
    const ref = useRef(null), inst = useRef(null);
    const [empty, setEmpty] = useState(false);

    useEffect(() => {
      if (!ref.current) return;
      inst.current = new window.EvidenceGraph(ref.current);
      return () => inst.current && inst.current.stop();
    }, []);

    useEffect(() => {
      if (!runId) { setEmpty(true); return; }
      let alive = true;
      const pull = () => fetch(`/api/graph/${runId}`).then((r) => r.json()).then((d) => {
        if (!alive || !inst.current) return;
        setEmpty(!d.nodes || d.nodes.length === 0);
        inst.current.setData(d);
      }).catch(() => {});
      pull();
      const iv = live ? setInterval(pull, 2200) : null;
      return () => { alive = false; iv && clearInterval(iv); };
    }, [runId, live]);

    return html`
      <div class="graph-shell">
        <canvas ref=${ref}></canvas>
        ${empty && html`
          <div style=${{ position: "absolute", inset: 0, display: "grid", placeItems: "center", pointerEvents: "none" }}>
            <div style=${{ textAlign: "center", color: "var(--fg-3)" }}>
              <${Icon} name="graph" size=26 />
              <div style=${{ fontSize: 13, marginTop: 8 }}>The graph builds as evidence arrives</div>
            </div>
          </div>`}
        <div class="graph-hint">hover a node · double-click a source to open it</div>
        <div class="graph-legend">
          ${Object.entries(window.GRAPH_REL).map(([k, v]) => html`
            <span key=${k}><i style=${{ background: v.color }}></i>${v.label}</span>`)}
        </div>
      </div>`;
  }

  /* ── meta plane ───────────────────────────────────────── */
  function MetaPanel({ onClose, tickets, rollback, teacher }) {
    const [remote, setRemote] = useState(null);
    useEffect(() => { fetch("/api/strategies").then((r) => r.json()).then(setRemote).catch(() => {}); }, []);
    const versions = (remote?.versions || []).slice(0, 12);

    return html`
      <${React.Fragment}>
        <div class="scrim" onClick=${onClose}></div>
        <aside class="meta-panel" role="dialog" aria-label="Meta plane">
          <div class="meta-hd">
            <${Icon} name="dna" size=17 style=${{ color: META }} />
            <div style=${{ flex: 1 }}>
              <h2>Meta Plane</h2>
              <div class="s">Governed self-improvement — separate from research</div>
            </div>
            <button class="ghost-btn" onClick=${onClose} aria-label="Close"><${Icon} name="close" size=16 /></button>
          </div>

          <div class="meta-body">
            ${teacher && html`
              <div>
                <div class="sp-t">Teacher — diagnosis of this run</div>
                <div class="commit-c">
                  <div class="commit-h">
                    <${Icon} name="teacher" size=14 style=${{ color: META }} />
                    ${teacher.authored_by === "teacher" ? "Model-authored critique" : "Derived critique (fallback)"}
                  </div>
                  <div class="commit-m">${teacher.failure_description}</div>
                  <div class="commit-m" style=${{ marginTop: 6, color: "var(--fg-3)" }}>
                    <b style=${{ color: "var(--fg-2)" }}>Root cause:</b> ${teacher.root_cause}
                  </div>
                  <div class="diffbox">${JSON.stringify(teacher.proposed_diff)}</div>
                </div>
              </div>`}

            <div>
              <div class="sp-t">Evolution tickets · held-out benchmark</div>
              ${tickets.length === 0
                ? html`<div class="empty" style=${{ padding: 24 }}><div class="ed">No tickets yet. One is raised at the end of each run.</div></div>`
                : tickets.map((t, i) => {
                    const b = t.before?.accuracy ?? 0, a = t.after?.accuracy ?? 0;
                    const dir = a > b ? "up" : a < b ? "dn" : "eq";
                    return html`
                      <div class="commit-c" style=${{ marginBottom: 8 }} key=${i}>
                        <div class="commit-h">
                          <${Icon} name=${t.kind === "regressive" ? "shieldAlert" : "idea"} size=14
                                   style=${{ color: t.kind === "regressive" ? BAD : META }} />
                          ${t.kind === "regressive" ? "Regressive proposal (drill)" : "Improvement proposal"}
                          <span class="commit-sha">${String(t.ticket_id || "").slice(0, 7)}</span>
                        </div>
                        <div class="commit-m">${t.failure}</div>
                        <div class="diffbox">${JSON.stringify(t.proposed_diff)}</div>
                        <div class="bench">
                          <span class="from">${b.toFixed(3)}</span>
                          <span class="benchbar"><i style=${{ width: `${a * 100}%`, background: dir === "up" ? OK : dir === "dn" ? BAD : "var(--fg-3)" }} /></span>
                          <span class=${"to " + dir}>${a.toFixed(3)}</span>
                          <${Tag} k=${dir === "up" ? "supports" : dir === "dn" ? "refutes" : "unknown"}>
                            ${dir === "up" ? "promote" : dir === "dn" ? "reject" : "no change"}<//>
                        </div>
                      </div>`;
                  })}
            </div>

            ${rollback && html`
              <div>
                <div class="sp-t">Rollback history</div>
                <div class="commit-c" style=${{ borderLeft: `2px solid ${"#a78bfa"}` }}>
                  <div class="commit-h"><${Icon} name="rewind" size=14 style=${{ color: "#a78bfa" }} /> Regression caught after promotion</div>
                  <div class="bench">
                    <span class="to dn">${rollback.bad_version_accuracy.toFixed(3)}</span>
                    <span class="from">→</span>
                    <span class="to up">${rollback.restored_version_accuracy.toFixed(3)}</span>
                    <span class="commit-sha">restored ${String(rollback.rolled_back_to).slice(0, 7)}</span>
                  </div>
                </div>
              </div>`}

            <div>
              <div class="sp-t">Strategy timeline</div>
              ${versions.length === 0
                ? html`<div class="empty" style=${{ padding: 24 }}><div class="ed">No strategy versions recorded yet.</div></div>`
                : versions.map((v, i) => html`
                    <div class="commit" key=${v.version_id}>
                      <div class=${"commit-n " + (v.status === "active" ? "active" : v.status === "rejected" ? "rejected" : v.status === "superseded" ? "rolled" : "")}>
                        <${Icon} name=${v.status === "active" ? "check" : v.status === "rejected" ? "close" : "dna"} size=12 />
                      </div>
                      <div class="commit-c" style=${{ marginBottom: 14 }}>
                        <div class="commit-h">
                          <span class="commit-sha">${v.version_id.slice(0, 7)}</span>
                          <${Tag} k=${v.status === "active" ? "supports" : v.status === "rejected" ? "refutes" : "unknown"}>${v.status}<//>
                        </div>
                        <div class="diffbox">${v.diff_json === "{}" ? "baseline (no diff)" : v.diff_json}</div>
                      </div>
                    </div>`)}
            </div>
          </div>
        </aside>
      <//>`;
  }

  /* ── right rail: live system state ────────────────────── */
  function StatePanel({ report, stages, round, hyps, backend, tokens, strategyId, running }) {
    const current = STAGES.find((s) => stages[s.id] === "active");
    const lead = hyps.length ? Math.max(...hyps.map((h) => h.confidence ?? 0)) : 0;

    // Reasoning health: a composite of metrics we actually measure. Shown with
    // its inputs so it can't be mistaken for a model-produced score.
    const health = report ? Math.round(100 * (
      0.3 * (report.citation_precision ?? 0) +
      0.2 * (1 - (report.unsupported_claim_rate ?? 0)) +
      0.2 * (report.prompt_injection_resistance ?? 0) +
      0.15 * (report.source_quality ?? 0) +
      0.15 * (report.browser_success ?? 0))) : null;

    const gauges = report ? [
      ["Citation precision", report.citation_precision, OK],
      ["Source quality", report.source_quality, META],
      ["Fetch success", report.browser_success, WARN],
      ["Injection resistance", report.prompt_injection_resistance, OK],
      ["Unsupported claims", report.unsupported_claim_rate, BAD],
    ] : [];

    return html`
      <aside class="state-panel">
        <div>
          <div class="sp-t">Current module</div>
          <div class="mod-now ${running ? "" : "idle"}">
            <span class="pulse"></span>
            <span>${current ? current.label : running ? "starting" : "idle"}</span>
          </div>
        </div>

        <div>
          <div class="sp-t">Live state</div>
          <div class="kv"><span class="k">Research round</span><span class="v">${round}<span style=${{ color: "var(--fg-3)" }}>/3</span></span></div>
          <div class="kv"><span class="k">Hypotheses</span><span class="v">${hyps.length}</span></div>
          <div class="kv"><span class="k">Lead confidence</span><span class="v warn">${Math.round(lead * 100)}%</span></div>
          <div class="kv"><span class="k">Tokens</span><span class="v">${(tokens || 0).toLocaleString()}</span></div>
          <div class="kv"><span class="k">Strategy</span><span class="v meta">${strategyId ? strategyId.slice(0, 7) : "—"}</span></div>
          <div class="kv"><span class="k">Profile</span><span class="v">communications</span></div>
          <div class="kv"><span class="k">Model</span><span class=${"v " + (backend?.live ? "ok" : "warn")}>${backend ? (backend.live ? backend.model : "offline mock") : "—"}</span></div>
        </div>

        ${report && html`
          <div>
            <div class="sp-t">Research health</div>
            <div class="health">
              <div class="health-n" style=${{ color: health >= 80 ? OK : health >= 55 ? WARN : BAD }}>${health}</div>
              <div class="health-l">Reasoning health</div>
              <div class="health-sub">Composite of citation precision, unsupported-claim rate, injection resistance, source quality and fetch success.</div>
            </div>
          </div>

          <div>
            <div class="sp-t">Metrics</div>
            ${gauges.map(([label, v, col]) => html`
              <div class="gauge-row" key=${label}>
                <span class="gauge-l">${label}</span>
                <span class="gauge-t"><i class="gauge-f" style=${{ display: "block", width: `${(v ?? 0) * 100}%`, background: col }} /></span>
                <span class="gauge-v" style=${{ color: col }}>${(v ?? 0).toFixed(2)}</span>
              </div>`)}
            <div class="kv" style=${{ marginTop: 8 }}><span class="k">Estimated cost</span><span class="v meta">$${(report.cost_usd ?? 0).toFixed(5)}</span></div>
            <div class="kv"><span class="k">Human approvals</span><span class="v">${report.human_interventions}</span></div>
          </div>`}
      </aside>`;
  }

  /* ── stub pages that have no backing data yet ─────────── */
  const Stub = ({ icon, title, body }) => html`
    <div class="empty">
      <div class="ei"><${Icon} name=${icon} size=28 /></div>
      <div class="et">${title}</div>
      <div class="ed">${body}</div>
    </div>`;

  /* ── app ──────────────────────────────────────────────── */
  // The one built-in scenario -- reachable only via the explicit "Try the
  // demo" action, never as a pre-filled default. A blank composer makes it
  // obvious the agent is waiting on *your* question; a pre-filled satellite
  // question invited running the demo by accident and mistaking every result
  // for a bug, because typing a different question and re-running without
  // clearing the text silently re-ran the same demo scenario.
  const DEMO_Q = "For a LEO swarm satellite communication system, does enforcing single-master bus arbitration keep peak power draw within the swarm's thermal budget?";

  function App() {
    const [view, setView] = useState("workspace");
    const [q, setQ] = useState("");
    const [isDemo, setIsDemo] = useState(false);
    const [file, setFile] = useState(null);
    const [over, setOver] = useState(false);
    const [running, setRunning] = useState(false);
    const [backend, setBackend] = useState(null);
    const [metaOpen, setMetaOpen] = useState(false);

    const [stages, setStages] = useState({});
    const [round, setRound] = useState(1);
    const [hyps, setHyps] = useState([]);
    const [ev, setEv] = useState({});
    const [papers, setPapers] = useState([]);
    const [breaches, setBreaches] = useState([]);
    const [tickets, setTickets] = useState([]);
    const [teacher, setTeacher] = useState(null);
    const [rollback, setRollback] = useState(null);
    const [verdict, setVerdict] = useState(null);
    const [synthesis, setSynthesis] = useState(null);
    const [report, setReport] = useState(null);
    const [feed, setFeed] = useState([]);
    const [err, setErr] = useState(null);
    const [openIds, setOpenIds] = useState({});
    const [docName, setDocName] = useState(null);
    const [storeRunId, setStoreRunId] = useState(null);
    const [strategyId, setStrategyId] = useState(null);
    const [runs, setRuns] = useState([]);
    const fileRef = useRef(null);
    const verdictRef = useRef(null);

    // fires once per verdict, not on every re-render -- otherwise the word
    // reveal would replay on unrelated state changes elsewhere in the app
    const revealedVerdict = useRef(null);
    useEffect(() => {
      if (!verdict || !verdictRef.current || revealedVerdict.current === verdict) return;
      revealedVerdict.current = verdict;
      requestAnimationFrame(() => motion().then((m) => m.revealVerdict(verdictRef.current)));
    }, [verdict]);

    useEffect(() => { fetch("/api/health").then((r) => r.json()).then(setBackend).catch(() => {}); }, []);
    useEffect(() => {
      if (view === "runs" || view === "reports")
        fetch("/api/runs").then((r) => r.json()).then(setRuns).catch(() => {});
    }, [view, running]);

    const log = useCallback((m, hi) =>
      setFeed((F) => [...F.slice(-80), { t: new Date().toLocaleTimeString([], { hour12: false }), m, hi }]), []);

    async function launch() {
      setStages({}); setRound(1); setHyps([]); setEv({}); setPapers([]); setBreaches([]);
      setTickets([]); setTeacher(null); setRollback(null); setVerdict(null); setSynthesis(null);
      setReport(null); setFeed([]); setErr(null); setOpenIds({}); setDocName(null);
      setStoreRunId(null); setRunning(true); setView("workspace");

      const fd = new FormData();
      fd.append("question", q);
      if (file) fd.append("document", file);
      if (isDemo && !file) fd.append("demo", "1");

      let id;
      try {
        const r = await fetch("/api/run", { method: "POST", body: fd });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || "could not start");
        id = j.run_id;
      } catch (e) { setErr(String(e.message || e)); setRunning(false); return; }

      const es = new EventSource(`/api/events/${id}`);
      const on = (n, f) => es.addEventListener(n, (m) => f(JSON.parse(m.data)));

      on("backend", (d) => {
        log(`backend ${d.llm} · ${d.model}`, !!d.fallback_reason);
        setBackend((b) => ({ ...(b || {}), backend: d.llm, model: d.model,
                            live: d.llm !== "MockLLM", fallback_reason: d.fallback_reason }));
      });
      on("run_started", (d) => {
        setDocName(d.document); setStoreRunId(d.run_id); setStrategyId(d.strategy_version_id);
        log(`run ${d.run_id} · strategy ${String(d.strategy_version_id).slice(0, 7)}`);
        if (d.document) log(`${d.user_document ? "your document" : "bundled demo doc"}: ${d.document}`, !!d.user_document);
      });
      on("stage", (d) => setStages((s) => ({ ...s, [d.stage]: d.status })));
      on("hypotheses", (d) => {
        setHyps(d.hypotheses);
        setOpenIds(Object.fromEntries(d.hypotheses.map((h) => [h.id, true])));
        log(`framed ${d.hypotheses.length} competing hypotheses`, true);
      });
      on("round", (d) => { setRound(d.round); log(`round ${d.round} · ${d.steps.length} step(s)`); });
      on("fetching", (d) => log(`${d.kind} · ${String(d.source).slice(0, 56)}`));
      on("papers", (d) => { setPapers((P) => [...P, ...d.papers]); log(`${d.papers.length} papers retrieved`, true); });
      on("evidence", (d) => {
        setEv((E) => ({ ...E, [d.hypothesis_id]: [...(E[d.hypothesis_id] || []), d] }));
        if (d.new_confidence != null)
          setHyps((H) => H.map((h) => h.id === d.hypothesis_id ? { ...h, confidence: d.new_confidence, status: d.status } : h));
        log(`${d.relation} · ${shortSrc(d.source)}`, d.relation === "refutes");
      });
      on("injection_refused", (d) => { setBreaches((B) => [...B, d]); log(`INJECTION REFUSED · ${d.locator}`, true); });
      on("replan", (d) => { setRound(d.to_round); log(`replanning → round ${d.to_round}`, true); });
      on("verification", (d) => log(`sandbox ${d.ok ? "ok" : "failed"} · ${String(d.stdout).replace(/\n/g, " · ")}`));
      on("teacher", (d) => { setTeacher(d); log(`teacher: ${d.authored_by === "teacher" ? "model-authored" : "derived"} critique`, true); });
      on("ticket", (d) => setTickets((T) => [...T, d]));
      on("rollback", (d) => { setRollback(d); log(`rolled back to ${String(d.rolled_back_to).slice(0, 7)}`, true); });
      on("verdict", (d) => { setVerdict(d); setHyps(d.hypotheses || []); log("verdict synthesized", true); });
      on("synthesis", (d) => { setSynthesis(d); if (d.proposals?.length) log(`${d.proposals.length} original proposals`, true); });
      on("approval", (d) => log(`gate ${d.action} · ${d.approved ? "approved" : "rejected"}`));
      on("finished", (d) => { setReport(d.report); log("finalized", true); });
      on("error", (d) => setErr(d.message));
      on("close", () => { es.close(); setRunning(false); });
      es.onerror = () => { es.close(); setRunning(false); };
    }

    const ranked = useMemo(() => [...hyps].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0)), [hyps]);
    const evCount = Object.values(ev).reduce((n, a) => n + a.length, 0);
    const quota = err && /429|RESOURCE_EXHAUSTED|quota/i.test(err);
    const started = running || hyps.length > 0;

    const WORK = {
      workspace: () => html`
        <${React.Fragment}>
          <div class="work-hd">
            <h1>Research workspace</h1>
            <span class="sub">${docName ? docName : "falsification-driven investigation"}</span>
          </div>

          ${backend?.fallback_reason && html`
            <div class="err-box" style=${{ marginBottom: 16 }}>
              <${Icon} name="shieldAlert" size=16 />
              <div>
                Your configured API key failed to initialize a real model — every run right now uses the
                offline mock, which returns fixed demo hypotheses regardless of your question or document.
                <span class="hint">${backend.fallback_reason}</span>
              </div>
            </div>`}

          <div class="composer">
            <${SignalCanvas} />
            <textarea rows="3" value=${q} disabled=${running} placeholder="What claim should be tested? e.g. Does X hold under Y conditions..."
                      onChange=${(e) => { setQ(e.target.value); setIsDemo(false); }} />
            <div class="composer-b">
              <div class="chip-btn ${file ? "set" : ""} ${over ? "over" : ""}"
                   onClick=${() => fileRef.current.click()}
                   onDragOver=${(e) => { e.preventDefault(); setOver(true); }}
                   onDragLeave=${() => setOver(false)}
                   onDrop=${(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) { setFile(f); setIsDemo(false); } }}>
                <input ref=${fileRef} type="file" accept="application/pdf" style=${{ display: "none" }}
                       onChange=${(e) => { if (e.target.files[0]) { setFile(e.target.files[0]); setIsDemo(false); } }} />
                <${Icon} name=${file ? "doc" : "upload"} size=14 />
                ${file ? html`<span class="nm">${file.name}</span>` : html`<span>Attach PDF</span>`}
              </div>
              ${file && !running && html`<button class="ghost-btn" onClick=${() => setFile(null)}>remove</button>`}
              ${!running && !isDemo && html`
                <button class="ghost-btn" onClick=${() => { setQ(DEMO_Q); setFile(null); setIsDemo(true); }}>
                  <${Icon} name="satellite" size=13 /> Try the demo
                </button>`}
              <button class="run-btn" onClick=${launch} disabled=${running || !q.trim()}>
                <${Icon} name=${running ? "clock" : "hunt"} size=14 />
                ${running ? html`<span class="dots">Investigating</span>` : "Run investigation"}
              </button>
            </div>
          </div>

          ${isDemo && !running && html`
            <div style=${{ marginTop: 12, fontSize: 12.5, color: "var(--fg-3)", display: "flex", gap: 8 }}>
              <${Icon} name="satellite" size=15 />
              <span>Demo scenario loaded — uses the bundled satellite spec sheet (with a planted prompt injection) and thermal dataset. Edit the question or attach your own PDF to leave demo mode.</span>
            </div>`}

          ${err && html`
            <div class="err-box" style=${{ marginTop: 16 }}>
              <${Icon} name="shieldAlert" size=16 />
              <div>
                ${quota ? "Model quota exhausted (Gemini free tier is 20 requests/day)." : err}
                ${quota && html`<span class="hint">Set NVIDIA_API_KEY in .env for a backend without that cap, or SHUTDOWN_OFFLINE=1 to run the full pipeline offline on the mock.</span>`}
              </div>
            </div>`}

          ${started && html`<div style=${{ marginTop: 28 }}><${Pipeline} stages=${stages} /></div>`}
          ${breaches.map((b, i) => html`<${Breach} a=${b} key=${i} />`)}

          ${verdict && html`
            <section class="sec">
              <div class="verdict" ref=${verdictRef}>
                <div class="verdict-l">Verdict ${verdict.synthesized === false ? "· derived (no model synthesis)" : ""}</div>
                <div class="verdict-a">${verdict.answer}</div>
                <div style=${{ display: "flex", gap: 8, marginBottom: 4 }}>
                  <${Tag} k=${verdict.confidence === "high" ? "supports" : verdict.confidence === "low" ? "refutes" : "weakens"}>
                    ${verdict.confidence} confidence<//>
                </div>
                ${(verdict.rulings || []).map((r, i) => {
                  const h = (verdict.hypotheses || []).find((x) => x.id === r.hypothesis_id);
                  return html`
                    <div class="verdict-row" key=${i}>
                      <${Tag} k=${r.ruling}>${r.ruling}<//>
                      <div class="w">${h ? h.statement : r.hypothesis_id}<div style=${{ color: "var(--fg-3)", marginTop: 3 }}>${r.why}</div></div>
                    </div>`;
                })}
                <div class="verdict-foot">
                  <div><b>What would change this</b>${verdict.what_would_change_it}</div>
                  <div><b>Caveat</b>${verdict.caveats}</div>
                </div>
              </div>
            </section>`}

          ${synthesis && html`
            <section class="sec">
              <div class="sec-hd"><${Icon} name="idea" size=15 style=${{ color: "#a78bfa" }} />
                <h2>Original proposals</h2><span class="n">evidence-constrained</span></div>
              ${synthesis.proposals?.length
                ? synthesis.proposals.map((p, i) => html`
                    <div class="prop" key=${i} style=${{ animationDelay: `${i * 70}ms` }}>
                      <div class="prop-t">${p.title} <${Tag} k=${p.novelty === "substantive" ? "substantive" : "unknown"}>${p.novelty}<//></div>
                      <div class="prop-p">${p.proposal}</div>
                      <div class="prop-m">
                        <span><b>Grounded in:</b> ${p.grounded_in}</span>
                        <span><b>How to test:</b> ${p.how_to_test}</span>
                      </div>
                    </div>`)
                : html`<div class="empty"><div class="ed">${synthesis.limitation}</div></div>`}
            </section>`}

          ${started && html`
            <section class="sec">
              <div class="sec-hd"><${Icon} name="branch" size=15 style=${{ color: WARN }} />
                <h2>Hypotheses</h2><span class="n">${hyps.length} claims · ${evCount} evidence</span></div>
              ${hyps.length === 0
                ? html`<div class="empty"><div class="et"><span class="dots">Framing competing hypotheses</span></div>
                        <div class="ed">Each claim must state what would disprove it.</div>
                        <div class="skel" style=${{ width: "55%", margin: "14px auto 0" }} /></div>`
                : ranked.map((h, i) => html`
                    <${HypCard} h=${h} evidence=${ev[h.id] || []} rank=${i}
                                lead=${i === 0 && h.status !== "eliminated"} open=${openIds[h.id] !== false}
                                key=${h.id} onToggle=${() => setOpenIds((O) => ({ ...O, [h.id]: O[h.id] === false }))} />`)}
            </section>`}

          ${papers.length > 0 && html`
            <section class="sec">
              <div class="sec-hd"><${Icon} name="paper" size=15 style=${{ color: META }} />
                <h2>Literature retrieved</h2><span class="n">${papers.length} papers</span></div>
              <div style=${{ border: "1px solid var(--line)", borderRadius: 12, padding: "4px 16px", background: "var(--s-1)" }}>
                ${papers.slice(0, 8).map((p, i) => html`
                  <div class="paper" key=${i} style=${{ animationDelay: `${i * 40}ms` }}>
                    <div>
                      <div class="paper-t">${p.title}</div>
                      <div class="paper-c">
                        ${p.citation}${p.doi ? html` · ` : null}
                        ${p.url ? html`<a href=${p.url} target="_blank" rel="noopener noreferrer">${p.doi || p.source}</a>` : p.source}
                      </div>
                    </div>
                    <div class="cites"><span class="n">${p.citations}</span>citations</div>
                  </div>`)}
              </div>
            </section>`}

          ${feed.length > 0 && html`
            <section class="sec">
              <div class="sec-hd"><${Icon} name="terminal" size=15 /><h2>Activity</h2></div>
              <div class="feed">
                ${feed.slice().reverse().map((l, i) => html`
                  <div class="fl ${l.hi ? "hi" : ""}" key=${i}><span class="ts">${l.t}</span><span class="tx">${l.m}</span></div>`)}
              </div>
            </section>`}
        <//>`,

      graph: () => html`
        <${React.Fragment}>
          <div class="work-hd"><h1>Evidence graph</h1>
            <span class="sub">claims, sources and what each one did to the other</span></div>
          <${GraphView} runId=${storeRunId} live=${running} />
        <//>`,

      runs: () => html`
        <${React.Fragment}>
          <div class="work-hd"><h1>Runs</h1><span class="sub">${runs.length} recorded</span></div>
          ${runs.length === 0
            ? html`<${Stub} icon="runs" title="No runs yet"
                     body="Every investigation is recorded here with its verdict, cost and evidence." />`
            : runs.map((r) => html`
                <button class="runcard" key=${r.run_id} onClick=${() => { setStoreRunId(r.run_id); setView("graph"); }}>
                  <div class="runcard-q">${r.question}</div>
                  <div class="runcard-m">
                    <span>${r.run_id.slice(0, 7)}</span>
                    <span>${r.hypotheses} hypotheses</span>
                    <span>${(r.tokens || 0).toLocaleString()} tokens</span>
                    <span>${r.status}</span>
                    <span>${String(r.started_at).slice(0, 16).replace("T", " ")}</span>
                  </div>
                  ${r.verdict?.answer && html`
                    <div style=${{ fontSize: 12.5, color: "var(--fg-3)", marginTop: 8, lineHeight: 1.5 }}>${r.verdict.answer}</div>`}
                </button>`)}
        <//>`,

      reports: () => html`
        <${React.Fragment}>
          <div class="work-hd"><h1>Reports</h1><span class="sub">evaluation packages</span></div>
          ${report
            ? html`<div class="verdict">
                <div class="verdict-l">Latest evaluation report</div>
                <div style=${{ marginTop: 14 }}>
                  ${Object.entries(report).map(([k, v]) => html`
                    <div class="kv" key=${k}><span class="k">${k.replace(/_/g, " ")}</span>
                      <span class="v">${typeof v === "number" ? v.toFixed(v > 100 ? 0 : 3) : v}</span></div>`)}
                </div>
                <div class="verdict-foot"><div><b>Package</b>research_package_${storeRunId || ""}.zip written to shutdown_output/</div></div>
              </div>`
            : html`<${Stub} icon="reports" title="No report yet"
                     body="A full evaluation report and research package are produced at the end of each run." />`}
        <//>`,

      library: () => html`
        <${React.Fragment}>
          <div class="work-hd"><h1>Library</h1><span class="sub">retrieved literature</span></div>
          ${papers.length === 0
            ? html`<${Stub} icon="library" title="Library is empty"
                     body="Papers retrieved from OpenAlex and arXiv during an investigation are collected here with their citation counts." />`
            : html`<div style=${{ border: "1px solid var(--line)", borderRadius: 12, padding: "4px 16px", background: "var(--s-1)" }}>
                ${papers.map((p, i) => html`
                  <div class="paper" key=${i}>
                    <div><div class="paper-t">${p.title}</div>
                      <div class="paper-c">${p.citation} · ${p.source}</div></div>
                    <div class="cites"><span class="n">${p.citations}</span>citations</div>
                  </div>`)}
              </div>`}
        <//>`,

      strategies: () => html`
        <${React.Fragment}>
          <div class="work-hd"><h1>Strategies</h1><span class="sub">the meta plane governs these</span></div>
          <${Stub} icon="strategies" title="Open the Meta Plane"
                   body="Strategy versions, evolution tickets, held-out benchmarks and rollback history live in the Meta Plane panel, kept deliberately separate from research." />
          <div style=${{ textAlign: "center", marginTop: 16 }}>
            <button class="run-btn" style=${{ margin: "0 auto" }} onClick=${() => setMetaOpen(true)}>
              <${Icon} name="dna" size=14 /> Open Meta Plane</button>
          </div>
        <//>`,

      memory: () => html`
        <${React.Fragment}>
          <div class="work-hd"><h1>Memory</h1><span class="sub">verdicts, proposals, rollback events</span></div>
          <${Stub} icon="memory" title="Memory browser not built"
                   body="Verdicts, synthesis proposals and rollback events are already persisted to the memory table each run — this view for browsing them across runs is not implemented yet." />
        <//>`,
    };

    return html`
      <div class="os">
        <nav class="rail">
          <div class="brand">
            <div class="brand-m"><${Icon} name="satellite" size=17 /></div>
            <div><div class="brand-n">Shutdown</div><div class="brand-s">Research OS</div></div>
          </div>

          <div class="nav-g">
            <div class="nav-t rail-label">Workspace</div>
            ${NAV.map((n) => html`
              <button class=${"nav-i " + (view === n.id ? "on" : "")} key=${n.id} onClick=${() => setView(n.id)}>
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

        <main class="work">
          ${(WORK[view] || (() => html`<${Stub} icon="settings" title="Settings"
              body="Model backend, keys and profile are configured through .env — GEMINI_API_KEY, NVIDIA_API_KEY, or SHUTDOWN_OFFLINE=1 for the offline mock." />`))()}
        </main>

        <${StatePanel} report=${report} stages=${stages} round=${round} hyps=${hyps}
                       backend=${backend} tokens=${report?.cost_tokens} strategyId=${strategyId} running=${running} />

        <button class="meta-fab" onClick=${() => setMetaOpen(true)}>
          <span class="d"></span> Meta Plane
          ${tickets.length > 0 && html`<span style=${{ color: "var(--fg-3)" }}>· ${tickets.length}</span>`}
        </button>

        ${metaOpen && html`<${MetaPanel} onClose=${() => setMetaOpen(false)}
                                         tickets=${tickets} rollback=${rollback} teacher=${teacher} />`}
      </div>`;
  }

  ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
})();
