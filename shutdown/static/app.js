/* Shutdown UI — React via htm tagged templates, so there's no JSX build step
   and the file you read is the file that runs. */
(function () {
  const { useState, useEffect, useRef, useCallback } = React;
  const html = htm.bind(React.createElement);
  const Icon = window.Icon;

  const STAGES = [
    { id: "framing",   label: "Framing",      icon: "branch", hint: "Generating competing falsifiable claims" },
    { id: "hunting",   label: "Hunting",      icon: "hunt",   hint: "Looking for evidence that kills them" },
    { id: "verifying", label: "Verifying",    icon: "beaker", hint: "Recomputing a claim in a sandbox" },
    { id: "evolving",  label: "Evolving",     icon: "dna",    hint: "Scoring a strategy change on held-out data" },
    { id: "verdict",   label: "Verdict",      icon: "seal",   hint: "Approval gate, then publish" },
  ];

  const SRC_ICON = { pdf: "doc", dataset: "database", web: "globe", code_output: "terminal", inline: "doc" };

  const pctOf = (n) => Math.round((n || 0) * 100);
  const hue = (s) => (s === "survived" ? "var(--moss)" : s === "eliminated" ? "var(--rose)" : "var(--amber)");

  function shortSrc(s) {
    if (!s) return "";
    if (s.startsWith("sandbox://")) return s;
    if (/^https?:/.test(s)) {
      try { const u = new URL(s); return u.hostname.replace(/^www\./, "") + (u.pathname.length > 1 ? u.pathname.slice(0, 24) : ""); }
      catch { return s; }
    }
    return s.split(/[\\/]/).pop();
  }

  /* Count-up so a confidence figure reads as something that moved, not a
     value that was always there. */
  function useCountUp(target, ms = 700) {
    const [v, setV] = useState(target);
    const from = useRef(target);
    useEffect(() => {
      const start = performance.now(), a = from.current, b = target;
      if (a === b) return;
      let raf;
      const tick = (t) => {
        const k = Math.min(1, (t - start) / ms);
        setV(a + (b - a) * (1 - Math.pow(1 - k, 3)));
        if (k < 1) raf = requestAnimationFrame(tick); else from.current = b;
      };
      raf = requestAnimationFrame(tick);
      return () => cancelAnimationFrame(raf);
    }, [target, ms]);
    return v;
  }

  const Tag = ({ k, children }) => html`<span class="t t-${k}">${children}</span>`;

  /* ── pipeline ─────────────────────────────────────────── */
  function Flow({ stages, round }) {
    return html`
      <div class="flow">
        ${STAGES.map((s, i) => {
          const st = stages[s.id] || "idle";
          const prevDone = i > 0 && (stages[STAGES[i - 1].id] === "done");
          return html`
            <div class="node ${st} ${prevDone ? "lit" : ""}" key=${s.id}>
              <div class="orb"><${Icon} name=${st === "done" ? "check" : s.icon} size=17 /></div>
              <div class="node-l">${s.label}</div>
              <div class="node-h">${s.hint}</div>
            </div>`;
        })}
        ${round > 1 && html`
          <div class="replan-flag">
            <${Icon} name="loop" size=14 /> replanned — now on round ${round} (evidence contradicted a live claim)
          </div>`}
      </div>`;
  }

  /* ── evidence ─────────────────────────────────────────── */
  function Ev({ e }) {
    const isUrl = /^https?:/.test(e.source || "");
    return html`
      <div class="ev">
        <span class="ev-ic"><${Icon} name=${SRC_ICON[e.source_type] || "doc"} size=15 /></span>
        <div class="ev-b">
          <div class="ev-r">${e.reason}</div>
          <div class="ev-s">
            ${isUrl ? html`<a href=${e.source} target="_blank" rel="noopener noreferrer">${shortSrc(e.source)}</a>`
                    : shortSrc(e.source)}
          </div>
          ${e.locator && html`<span class="loc"><${Icon} name="doc" size=11 /> ${e.locator}</span>`}
        </div>
        <${Tag} k=${e.relation}>${e.relation}<//>
      </div>`;
  }

  /* ── hypothesis ───────────────────────────────────────── */
  function Hyp({ h, evidence, rank, lead, open, onToggle }) {
    const shown = useCountUp(pctOf(h.confidence));
    return html`
      <div class="hyp ${lead ? "lead" : ""} ${h.status === "eliminated" ? "dead" : ""}"
           style=${{ animationDelay: `${rank * 70}ms` }}>
        <div class="hyp-hd" onClick=${onToggle} role="button" tabIndex=${0}
             onKeyDown=${(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onToggle())}>
          <div class="rank">${rank + 1}</div>
          <div>
            <div class="hyp-txt">${h.statement}</div>
            ${h.kills_it && open && html`
              <div class="hyp-kills"><b>Killed by:</b> <span>${h.kills_it}</span></div>`}
          </div>
          <div class="gauge">
            <span class="gauge-n" style=${{ color: hue(h.status) }}>${Math.round(shown)}%</span>
            <div class="track"><div class="fill" style=${{ width: shown + "%", background: hue(h.status) }} /></div>
            <${Tag} k=${h.status}>${h.status}<//>
          </div>
        </div>
        ${open && evidence.length > 0 && html`
          <div class="ev-wrap">${evidence.map((e, i) => html`<${Ev} e=${e} key=${i} />`)}</div>`}
      </div>`;
  }

  /* ── injection ────────────────────────────────────────── */
  function Breach({ a }) {
    const phrase = (a.detail.match(/'(.+)'/) || [])[1];
    let body = a.excerpt;
    if (phrase && a.excerpt) {
      const i = a.excerpt.toLowerCase().indexOf(phrase.toLowerCase());
      if (i >= 0) body = html`${a.excerpt.slice(0, i)}<mark>${a.excerpt.substr(i, phrase.length)}</mark>${a.excerpt.slice(i + phrase.length)}`;
    }
    return html`
      <div class="breach">
        <div class="breach-hd"><${Icon} name="shieldAlert" size=18 /> Prompt injection found and refused</div>
        <div class="breach-src">
          ${shortSrc(a.source)}${a.locator ? html` — <b>${a.locator}</b>` : null}
        </div>
        ${a.excerpt && html`<div class="breach-q">${body}</div>`}
        <div class="breach-ok"><${Icon} name="shield" size=15 /> Logged as evidence. Never executed, never trusted as instructions.</div>
      </div>`;
  }

  /* ── meta plane ───────────────────────────────────────── */
  function Ticket({ t }) {
    const b = t.before?.accuracy ?? 0, a = t.after?.accuracy ?? 0;
    const dir = a > b ? "improved" : a < b ? "regressed" : "no change";
    return html`
      <div class="card ${t.kind === "regressive" ? "ro" : "cy"}">
        <div class="card-h">
          <${Icon} name=${t.kind === "regressive" ? "shieldAlert" : "dna"} size=15
                   style=${{ color: t.kind === "regressive" ? "var(--rose)" : "var(--cyan)" }} />
          ${t.kind === "regressive" ? "Regressive proposal (rollback drill)" : "Improvement proposal"}
        </div>
        <div class="card-w">${t.failure}</div>
        <div class="code">${JSON.stringify(t.proposed_diff)}</div>
        <div class="score">
          <span class="a">held-out</span><span>${b.toFixed(3)}</span><span class="a">→</span>
          <span class=${a > b ? "up" : a < b ? "dn" : "eq"}>${a.toFixed(3)}</span>
          <${Tag} k=${a > b ? "supports" : a < b ? "refutes" : "unknown"}>${dir}<//>
        </div>
      </div>`;
  }

  /* ── metrics ──────────────────────────────────────────── */
  const LABEL = {
    end_to_end_success: "End-to-end", citation_precision: "Citation prec.", citation_recall: "Citation recall",
    unsupported_claim_rate: "Unsupported", source_quality: "Source quality", browser_success: "Fetch success",
    code_execution_success: "Code exec", prompt_injection_resistance: "Injection resist", cost_tokens: "Tokens",
    cost_usd: "Est. cost", human_interventions: "Approvals", hypothesis_elimination_rate: "Elimination",
    strategy_improvement_rate: "Strategy accept", rollback_frequency: "Rollbacks",
  };
  const COUNTS = ["cost_tokens", "human_interventions", "rollback_frequency"];

  function Metrics({ report }) {
    if (!report) return null;
    const tone = (k, v) => {
      if (["citation_precision", "citation_recall", "prompt_injection_resistance", "end_to_end_success", "code_execution_success"].includes(k))
        return v >= 1 ? "good" : v >= .5 ? "warn" : "bad";
      if (k === "unsupported_claim_rate") return v === 0 ? "good" : "bad";
      if (k === "browser_success") return v >= .8 ? "good" : v >= .4 ? "warn" : "bad";
      return "info";
    };
    const fmt = (k, v) => k === "cost_usd" ? "$" + Number(v).toFixed(5)
      : COUNTS.includes(k) ? Number(v).toLocaleString()
      : typeof v === "number" ? v.toFixed(2) : String(v);
    return html`
      <section class="sec">
        <div class="sec-h"><${Icon} name="spark" size=15 style=${{ color: "var(--cyan)" }} />
          <h2>Evaluation report</h2><div class="rule"></div></div>
        <div class="mgrid">
          ${Object.entries(report).map(([k, v], i) => html`
            <div class="m" key=${k} style=${{ animationDelay: `${i * 30}ms` }}>
              <span class="k">${LABEL[k] || k}</span>
              <span class="v ${tone(k, v)}">${fmt(k, v)}</span>
            </div>`)}
        </div>
      </section>`;
  }

  /* ── app ──────────────────────────────────────────────── */
  const DEFAULT_Q = "For a LEO swarm satellite communication system, does enforcing single-master bus arbitration keep peak power draw within the swarm's thermal budget?";

  function App() {
    const [q, setQ] = useState(DEFAULT_Q);
    const [file, setFile] = useState(null);
    const [over, setOver] = useState(false);
    const [running, setRunning] = useState(false);
    const [backend, setBackend] = useState(null);

    const [stages, setStages] = useState({});
    const [round, setRound] = useState(1);
    const [hyps, setHyps] = useState([]);
    const [ev, setEv] = useState({});
    const [breaches, setBreaches] = useState([]);
    const [tickets, setTickets] = useState([]);
    const [rollback, setRollback] = useState(null);
    const [report, setReport] = useState(null);
    const [feed, setFeed] = useState([]);
    const [err, setErr] = useState(null);
    const [openIds, setOpenIds] = useState({});
    const [docName, setDocName] = useState(null);
    const fileRef = useRef(null);

    useEffect(() => { fetch("/api/health").then((r) => r.json()).then(setBackend).catch(() => {}); }, []);

    const log = useCallback((m, hi) =>
      setFeed((F) => [...F.slice(-70), { t: new Date().toLocaleTimeString([], { hour12: false }), m, hi }]), []);

    async function launch() {
      setStages({}); setRound(1); setHyps([]); setEv({}); setBreaches([]);
      setTickets([]); setRollback(null); setReport(null); setFeed([]); setErr(null);
      setOpenIds({}); setDocName(null); setRunning(true);

      const fd = new FormData();
      fd.append("question", q);
      if (file) fd.append("document", file);

      let id;
      try {
        const r = await fetch("/api/run", { method: "POST", body: fd });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || "could not start");
        id = j.run_id;
      } catch (e) { setErr(String(e.message || e)); setRunning(false); return; }

      const es = new EventSource(`/api/events/${id}`);
      const on = (n, f) => es.addEventListener(n, (m) => f(JSON.parse(m.data)));

      on("backend", (d) => log(`backend ${d.llm} · ${d.model}`));
      on("run_started", (d) => {
        setDocName(d.document);
        log(`run ${d.run_id} · strategy ${String(d.strategy_version_id).slice(0, 8)}`);
        if (d.document) log(`${d.user_document ? "your document" : "bundled demo doc"}: ${d.document}`, !!d.user_document);
      });
      on("stage", (d) => setStages((s) => ({ ...s, [d.stage]: d.status })));
      on("hypotheses", (d) => {
        setHyps(d.hypotheses);
        setOpenIds(Object.fromEntries(d.hypotheses.map((h) => [h.id, true])));
        log(`framed ${d.hypotheses.length} competing hypotheses`, true);
      });
      on("round", (d) => { setRound(d.round); log(`round ${d.round} · ${d.steps.length} step(s)`); });
      on("fetching", (d) => log(`fetch ${d.kind} · ${String(d.source).slice(0, 58)}`));
      on("evidence", (d) => {
        setEv((E) => ({ ...E, [d.hypothesis_id]: [...(E[d.hypothesis_id] || []), d] }));
        if (d.new_confidence != null)
          setHyps((H) => H.map((h) => h.id === d.hypothesis_id ? { ...h, confidence: d.new_confidence, status: d.status } : h));
        log(`${d.relation} · ${shortSrc(d.source)}`, d.relation === "refutes");
      });
      on("injection_refused", (d) => { setBreaches((B) => [...B, d]); log(`INJECTION REFUSED · ${d.locator}`, true); });
      on("replan", (d) => { setRound(d.to_round); log(`replanning → round ${d.to_round}`, true); });
      on("verification", (d) => log(`sandbox ${d.ok ? "ok" : "failed"} · ${String(d.stdout).replace(/\n/g, " · ")}`));
      on("ticket", (d) => setTickets((T) => [...T, d]));
      on("rollback", (d) => { setRollback(d); log(`rolled back to ${String(d.rolled_back_to).slice(0, 8)}`, true); });
      on("approval", (d) => log(`gate ${d.action} · ${d.approved ? "approved" : "rejected"}`));
      on("budget_reached", (d) => log(`token budget ${d.budget} reached`, true));
      on("finished", (d) => { setReport(d.report); log("finalized", true); });
      on("error", (d) => setErr(d.message));
      on("close", () => { es.close(); setRunning(false); });
      es.onerror = () => { es.close(); setRunning(false); };
    }

    const ranked = [...hyps].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
    const evCount = Object.values(ev).reduce((n, a) => n + a.length, 0);
    const quota = err && /429|RESOURCE_EXHAUSTED|quota/i.test(err);

    return html`
      <div class="wrap">
        <header class="hdr">
          <div class="logo"><${Icon} name="satellite" size=20 /></div>
          <div>
            <h1>Shutdown</h1>
            <div class="tag">Falsification research agent · AE-02</div>
          </div>
          <div class="spacer"></div>
          ${backend && html`<span class="pill ${backend.live ? "live" : "mock"}">
            <span class="d"></span>${backend.live ? backend.model : "offline mock"}</span>`}
          ${running && html`<span class="pill busy"><span class="d"></span>running</span>`}
        </header>

        <section class="hero">
          <h2 class="hero-lead">Give it a claim. It goes looking for what <em>kills</em> it.</h2>
          <p class="hero-sub">
            Competing hypotheses, evidence hunted for contradiction rather than confirmation,
            replanning the moment two sources disagree — and a governed self-improvement loop
            that can be rolled back.
          </p>

          <div class="composer">
            <textarea rows="3" value=${q} disabled=${running} placeholder="What claim should be tested?"
                      onChange=${(e) => setQ(e.target.value)} />
            <div class="composer-bar">
              <div class="attach ${file ? "set" : ""} ${over ? "over" : ""}"
                   onClick=${() => fileRef.current.click()}
                   onDragOver=${(e) => { e.preventDefault(); setOver(true); }}
                   onDragLeave=${() => setOver(false)}
                   onDrop=${(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}>
                <input ref=${fileRef} type="file" accept="application/pdf" style=${{ display: "none" }}
                       onChange=${(e) => e.target.files[0] && setFile(e.target.files[0])} />
                <${Icon} name=${file ? "doc" : "upload"} size=15 />
                ${file ? html`<span class="nm">${file.name}</span>` : html`<span>Attach a PDF</span>`}
              </div>
              ${file && !running && html`
                <button class="linkbtn" onClick=${() => setFile(null)}>remove</button>`}
              <button class="go" onClick=${launch} disabled=${running || !q.trim()}>
                <${Icon} name=${running ? "clock" : "hunt"} size=16 />
                ${running ? html`<span class="dots">Investigating</span>` : "Run falsification"}
              </button>
            </div>
          </div>

          ${file && !running && q === DEFAULT_Q && html`
            <div style=${{ marginTop: ".7rem", fontSize: ".82rem", color: "var(--amber)", display: "flex", gap: ".45rem" }}>
              <${Icon} name="shieldAlert" size=15 />
              <span>You attached a document but the question is still the built-in satellite one —
                    edit it to ask about <b>${file.name}</b>, or the hypotheses won't be about your file.</span>
            </div>`}

          ${err && html`
            <div class="err" style=${{ marginTop: "1rem" }}>
              <${Icon} name="shieldAlert" size=16 />
              <div>
                ${quota ? "Gemini free-tier quota exhausted (20 requests/day)." : err}
                ${quota && html`<span class="hint">
                  Wait for the daily reset, or set NVIDIA_API_KEY in .env for a backend without that cap.
                  With no key at all the pipeline still runs offline on MockLLM.</span>`}
              </div>
            </div>`}
        </section>

        ${(running || hyps.length > 0) && html`<${Flow} stages=${stages} round=${round} />`}

        ${breaches.map((b, i) => html`<${Breach} a=${b} key=${i} />`)}

        ${(hyps.length > 0 || running) && html`
          <section class="sec">
            <div class="sec-h">
              <${Icon} name="branch" size=15 style=${{ color: "var(--amber)" }} />
              <h2>Hypotheses</h2><div class="rule"></div>
              <span class="n">${hyps.length} claims · ${evCount} evidence${docName ? ` · ${docName}` : ""}</span>
            </div>
            <div class="arena">
              ${hyps.length === 0
                ? html`<div class="empty">
                    <div class="t1"><span class="dots">Framing competing hypotheses</span></div>
                    <div class="t2">Each one has to state what would disprove it.</div>
                  </div>`
                : ranked.map((h, i) => html`
                    <${Hyp} h=${h} evidence=${ev[h.id] || []} rank=${i} lead=${i === 0 && h.status !== "eliminated"}
                            open=${openIds[h.id] !== false} key=${h.id}
                            onToggle=${() => setOpenIds((O) => ({ ...O, [h.id]: O[h.id] === false }))} />`)}
            </div>
          </section>`}

        ${tickets.length > 0 && html`
          <section class="sec">
            <div class="sec-h">
              <${Icon} name="dna" size=15 style=${{ color: "var(--cyan)" }} />
              <h2>Meta plane — governed self-improvement</h2><div class="rule"></div>
              <span class="n">held-out scored · human approved</span>
            </div>
            <div class="grid2">
              ${tickets.map((t, i) => html`<${Ticket} t=${t} key=${i} />`)}
              ${rollback && html`
                <div class="card vi">
                  <div class="card-h"><${Icon} name="rewind" size=15 style=${{ color: "var(--violet)" }} /> Rollback executed</div>
                  <div class="card-w">Regression caught after promotion — the previously active version was restored.</div>
                  <div class="score">
                    <span class="dn">${rollback.bad_version_accuracy.toFixed(3)}</span>
                    <span class="a">→</span>
                    <span class="up">${rollback.restored_version_accuracy.toFixed(3)}</span>
                    <${Tag} k="meta">v ${String(rollback.rolled_back_to).slice(0, 8)}<//>
                  </div>
                </div>`}
            </div>
          </section>`}

        <${Metrics} report=${report} />

        ${feed.length > 0 && html`
          <section class="sec">
            <div class="sec-h"><${Icon} name="terminal" size=15 /><h2>Activity</h2><div class="rule"></div></div>
            <div class="feed">
              ${feed.slice().reverse().map((l, i) => html`
                <div class="fl ${l.hi ? "hi" : ""}" key=${i}><span class="ts">${l.t}</span><span class="tx">${l.m}</span></div>`)}
            </div>
          </section>`}
      </div>`;
  }

  ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
})();
