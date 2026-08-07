/* Shutdown UI — React via htm tagged templates, so there's no JSX build step
   and the file you read is the file that runs. */
(function () {
  const { useState, useEffect, useRef, useCallback } = React;
  const html = htm.bind(React.createElement);
  const Icon = window.Icon;

  /* ── pipeline stages, in the order the agent runs them ─────────────── */
  const STAGES = [
    { id: "framing",   label: "Hypothesis framing", icon: "branch",
      note: "Competing falsifiable claims — each must state what would kill it." },
    { id: "hunting",   label: "Contradiction hunt", icon: "hunt",
      note: "Reads sources looking for what disproves them, replanning on conflict." },
    { id: "verifying", label: "Verification",       icon: "beaker",
      note: "Recomputes a closed-form claim in a sandboxed subprocess." },
    { id: "evolving",  label: "Strategy evolution", icon: "dna",
      note: "Meta plane: proposes a parameter change, scored on held-out data." },
    { id: "verdict",   label: "Verdict",            icon: "seal",
      note: "Human approval gate, then the traceable evidence graph is published." },
  ];

  const SOURCE_ICON = { pdf: "doc", dataset: "database", web: "globe", code_output: "terminal", inline: "doc" };

  const pct = (n) => Math.round((n || 0) * 100);
  const confColor = (status) =>
    status === "survived" ? "var(--moss)" : status === "eliminated" ? "var(--rose)" : "var(--amber)";

  const shortSource = (s) => {
    if (!s) return "";
    if (s.startsWith("sandbox://")) return s;
    if (/^https?:/.test(s)) { try { return new URL(s).hostname.replace(/^www\./, "") + new URL(s).pathname.slice(0, 28); } catch { return s; } }
    return s.split(/[\\/]/).pop();
  };

  /* ── small presentational pieces ───────────────────────────────────── */
  const Chip = ({ kind, children }) => html`<span class="chip chip-${kind}">${children}</span>`;

  function Stepper({ stages }) {
    return html`
      <div class="panel">
        <div class="panel-head">
          <${Icon} name="satellite" size=15 />
          <h2>Pipeline</h2>
        </div>
        <div class="stepper">
          ${STAGES.map((s) => {
            const st = stages[s.id] || "idle";
            return html`
              <div class="step ${st}" key=${s.id}>
                <div class="step-dot">
                  <${Icon} name=${st === "done" ? "check" : s.icon} size=14 />
                </div>
                <div>
                  <div class="step-label">${s.label}</div>
                  <div class="step-note">${s.note}</div>
                </div>
              </div>`;
          })}
        </div>
      </div>`;
  }

  function EvidenceRow({ e }) {
    const isUrl = /^https?:/.test(e.source || "");
    return html`
      <div class="ev">
        <${Icon} name=${SOURCE_ICON[e.source_type] || "doc"} size=15
                 style=${{ color: "var(--text-faint)", marginTop: "2px" }} />
        <div class="ev-body">
          <div class="ev-reason">${e.reason}</div>
          <div class="ev-src">
            ${isUrl
              ? html`<a href=${e.source} target="_blank" rel="noopener noreferrer">${shortSource(e.source)}</a>`
              : shortSource(e.source)}
          </div>
          ${e.locator ? html`<span class="ev-loc">found at ${e.locator}</span>` : null}
        </div>
        <div style=${{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "4px" }}>
          <${Chip} kind=${e.relation}>${e.relation}<//>
          ${e.confidence > 0 ? html`<span class="ev-conf">w ${e.confidence.toFixed(2)}</span>` : null}
        </div>
      </div>`;
  }

  function HypothesisCard({ h: hyp, evidence }) {
    const conf = hyp.confidence ?? 0.5;
    return html`
      <div class="hyp">
        <div class="hyp-top">
          <div class="hyp-statement">${hyp.statement}</div>
          <div class="hyp-meta">
            <${Chip} kind=${hyp.status}>${hyp.status}<//>
            <div class="bar-track" style=${{ flex: 1 }}>
              <div class="bar-fill" style=${{ width: pct(conf) + "%", background: confColor(hyp.status) }} />
            </div>
            <span class="conf-num" style=${{ color: confColor(hyp.status) }}>${pct(conf)}%</span>
          </div>
        </div>
        <div class="hyp-evidence">
          ${evidence.map((e, i) => html`<${EvidenceRow} e=${e} key=${i} />`)}
        </div>
      </div>`;
  }

  function InjectionAlert({ a }) {
    // highlight the matched phrase inside the excerpt so the attack is visible,
    // not just asserted
    const phrase = (a.detail.match(/'(.+)'/) || [])[1];
    let body = a.excerpt;
    if (phrase && a.excerpt) {
      const i = a.excerpt.toLowerCase().indexOf(phrase.toLowerCase());
      if (i >= 0) {
        body = html`${a.excerpt.slice(0, i)}<mark>${a.excerpt.substr(i, phrase.length)}</mark>${a.excerpt.slice(i + phrase.length)}`;
      }
    }
    return html`
      <div class="alert-injection">
        <div class="hd"><${Icon} name="shieldAlert" size=16 /> Prompt injection detected in source</div>
        <div style=${{ fontSize: ".78rem", color: "var(--text-dim)" }}>
          ${shortSource(a.source)}${a.locator ? html` — <strong style=${{ color: "var(--amber)" }}>${a.locator}</strong>` : null}
        </div>
        ${a.excerpt ? html`<div class="excerpt">${body}</div>` : null}
        <div class="verdict">
          <${Icon} name="shield" size=14 /> Refused — logged as evidence, never trusted as instructions.
        </div>
      </div>`;
  }

  function TicketCard({ t }) {
    const before = t.before?.accuracy ?? 0, after = t.after?.accuracy ?? 0;
    // three states, not two -- "no change" is the common outcome when a
    // proposal is already at ceiling, and calling that "regressed" is a lie
    const dir = after > before ? "improved" : after < before ? "regressed" : "no change";
    const dirKind = dir === "improved" ? "supports" : dir === "regressed" ? "refutes" : "unknown";
    return html`
      <div class="ticket ${t.kind === "regressive" ? "regressive" : ""}">
        <div class="hd">
          <${Icon} name=${t.kind === "regressive" ? "shieldAlert" : "dna"} size=15
                   style=${{ color: t.kind === "regressive" ? "var(--rose)" : "var(--cyan)" }} />
          ${t.kind === "regressive" ? "Regressive proposal (rollback drill)" : "Improvement proposal"}
        </div>
        <div class="why">${t.failure}</div>
        <div class="diff">${JSON.stringify(t.proposed_diff)}</div>
        <div class="score-row">
          <span style=${{ color: "var(--text-faint)" }}>held-out</span>
          <span class="score-before">${before.toFixed(3)}</span>
          <span class="arrow">→</span>
          <span class="score-after ${dir === "improved" ? "up" : dir === "regressed" ? "down" : ""}">
            ${after.toFixed(3)}
          </span>
          <${Chip} kind=${dirKind}>${dir}<//>
        </div>
      </div>`;
  }

  function Metrics({ report }) {
    if (!report) return null;
    const tone = (k, v) => {
      if (["citation_precision", "citation_recall", "prompt_injection_resistance", "end_to_end_success", "code_execution_success"].includes(k))
        return v >= 1 ? "good" : v >= 0.5 ? "warn" : "bad";
      if (k === "unsupported_claim_rate") return v === 0 ? "good" : "bad";
      if (k === "browser_success") return v >= 0.8 ? "good" : v >= 0.4 ? "warn" : "bad";
      return "info";
    };
    // counts stay integers; every 0..1 ratio gets two decimals so the column
    // of numbers lines up instead of mixing "1" with "0.52"
    const COUNTS = ["cost_tokens", "human_interventions", "rollback_frequency"];
    const fmt = (k, v) => {
      if (k === "cost_usd") return "$" + Number(v).toFixed(5);
      if (COUNTS.includes(k)) return Number(v).toLocaleString();
      if (typeof v === "number") return v.toFixed(2);
      return String(v);
    };
    const LABEL = {
      end_to_end_success: "End-to-end", citation_precision: "Citation prec.",
      citation_recall: "Citation recall", unsupported_claim_rate: "Unsupported",
      source_quality: "Source quality", browser_success: "Fetch success",
      code_execution_success: "Code exec", prompt_injection_resistance: "Injection resist",
      cost_tokens: "Tokens", cost_usd: "Est. cost", human_interventions: "Approvals",
      hypothesis_elimination_rate: "Elimination", strategy_improvement_rate: "Strategy accept",
      rollback_frequency: "Rollbacks",
    };
    return html`
      <div class="panel">
        <div class="panel-head"><${Icon} name="spark" size=15 /><h2>Evaluation report</h2></div>
        <div class="metrics">
          ${Object.entries(report).map(([k, v]) => html`
            <div class="metric" key=${k}>
              <span class="k">${LABEL[k] || k}</span>
              <span class="v ${tone(k, v)}">${fmt(k, v)}</span>
            </div>`)}
        </div>
      </div>`;
  }

  function DropZone({ file, onFile }) {
    const [over, setOver] = useState(false);
    const ref = useRef(null);
    return html`
      <div class="drop ${over ? "over" : ""} ${file ? "has-file" : ""}"
           onClick=${() => ref.current.click()}
           onDragOver=${(e) => { e.preventDefault(); setOver(true); }}
           onDragLeave=${() => setOver(false)}
           onDrop=${(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) onFile(f); }}>
        <input ref=${ref} type="file" accept="application/pdf" style=${{ display: "none" }}
               onChange=${(e) => e.target.files[0] && onFile(e.target.files[0])} />
        <${Icon} name=${file ? "doc" : "upload"} size=22 />
        ${file
          ? html`<span class="fname">${file.name}</span><span class="hint">Click to replace</span>`
          : html`<span style=${{ fontWeight: 600, fontSize: ".85rem" }}>Drop a PDF to investigate</span>
                 <span class="hint">Optional — uses the bundled satellite spec sheet if empty</span>`}
      </div>`;
  }

  /* ── main app ──────────────────────────────────────────────────────── */
  function App() {
    const [question, setQuestion] = useState(
      "For a LEO swarm satellite communication system, does enforcing single-master bus arbitration keep peak power draw within the swarm's thermal budget?"
    );
    const [file, setFile] = useState(null);
    const [running, setRunning] = useState(false);
    const [backend, setBackend] = useState(null);

    const [stages, setStages] = useState({});
    const [hyps, setHyps] = useState([]);
    const [evidence, setEvidence] = useState({});   // hypothesis_id -> [evidence]
    const [injections, setInjections] = useState([]);
    const [tickets, setTickets] = useState([]);
    const [rollback, setRollback] = useState(null);
    const [report, setReport] = useState(null);
    const [log, setLog] = useState([]);
    const [error, setError] = useState(null);

    useEffect(() => {
      fetch("/api/health").then((r) => r.json()).then(setBackend).catch(() => {});
    }, []);

    const addLog = useCallback((m, hit) => {
      setLog((L) => [...L.slice(-60), { t: new Date().toLocaleTimeString([], { hour12: false }), m, hit }]);
    }, []);

    const reset = () => {
      setStages({}); setHyps([]); setEvidence({}); setInjections([]);
      setTickets([]); setRollback(null); setReport(null); setLog([]); setError(null);
    };

    async function launch() {
      reset();
      setRunning(true);
      const fd = new FormData();
      fd.append("question", question);
      if (file) fd.append("document", file);

      let runId;
      try {
        const res = await fetch("/api/run", { method: "POST", body: fd });
        const j = await res.json();
        if (!res.ok) throw new Error(j.error || "failed to start");
        runId = j.run_id;
      } catch (err) {
        setError(String(err.message || err)); setRunning(false); return;
      }

      const es = new EventSource(`/api/events/${runId}`);
      const on = (name, fn) => es.addEventListener(name, (ev) => fn(JSON.parse(ev.data)));

      on("backend", (d) => addLog(`backend: ${d.llm} (${d.model})`));
      on("run_started", (d) => addLog(`run ${d.run_id} · strategy ${d.strategy_version_id.slice(0, 8)}`));
      on("stage", (d) => setStages((s) => ({ ...s, [d.stage]: d.status })));
      on("hypotheses", (d) => { setHyps(d.hypotheses); addLog(`framed ${d.hypotheses.length} competing hypotheses`, true); });
      on("round", (d) => addLog(`round ${d.round}: ${d.steps.length} search step(s)`));
      on("fetching", (d) => addLog(`fetch · ${d.kind} · ${String(d.source).slice(0, 60)}`));
      on("evidence", (d) => {
        setEvidence((E) => ({ ...E, [d.hypothesis_id]: [...(E[d.hypothesis_id] || []), d] }));
        if (d.new_confidence != null) {
          setHyps((H) => H.map((h) => h.id === d.hypothesis_id
            ? { ...h, confidence: d.new_confidence, status: d.status } : h));
        }
        addLog(`${d.relation} · ${shortSource(d.source)}`, d.relation === "refutes");
      });
      on("injection_refused", (d) => { setInjections((I) => [...I, d]); addLog(`INJECTION REFUSED · ${d.locator}`, true); });
      on("replan", (d) => addLog(`replanning → round ${d.to_round} (${d.why})`, true));
      on("verification", (d) => addLog(`sandbox recompute ${d.ok ? "ok" : "failed"}: ${String(d.stdout).replace(/\n/g, " · ")}`));
      on("ticket", (d) => setTickets((T) => [...T, d]));
      on("rollback", (d) => { setRollback(d); addLog(`rolled back to ${d.rolled_back_to.slice(0, 8)}`, true); });
      on("approval", (d) => addLog(`approval gate · ${d.action} · ${d.approved ? "approved" : "rejected"}`));
      on("budget_reached", (d) => addLog(`token budget ${d.budget} reached — finalizing early`, true));
      on("finished", (d) => { setReport(d.report); addLog("finalized"); });
      on("error", (d) => setError(d.message));
      on("close", () => { es.close(); setRunning(false); });
      es.onerror = () => { es.close(); setRunning(false); };
    }

    const totalEvidence = Object.values(evidence).reduce((n, a) => n + a.length, 0);

    return html`
      <div class="shell">
        <header class="topbar">
          <div class="brand">
            <div class="brand-mark"><${Icon} name="satellite" size=18 /></div>
            <div>
              <h1>Shutdown</h1>
              <div class="sub">Falsification research agent · AE-02</div>
            </div>
          </div>
          <div class="topbar-spacer"></div>
          ${backend && html`
            <span class="status-pill ${backend.live ? "live" : "mock"}">
              <span class="dot"></span>${backend.live ? backend.model : "offline mock"}
            </span>`}
          ${running && html`<span class="status-pill running"><span class="dot"></span>investigating</span>`}
        </header>

        <div class="cols">
          <aside style=${{ display: "flex", flexDirection: "column", gap: "1rem", position: "sticky", top: "1rem" }}>
            <${Stepper} stages=${stages} />
            ${log.length > 0 && html`
              <div class="panel">
                <div class="panel-head"><${Icon} name="terminal" size=15 /><h2>Activity</h2></div>
                <div class="panel-body" style=${{ padding: ".6rem .8rem" }}>
                  <div class="log">
                    ${log.slice().reverse().map((l, i) => html`
                      <div class="log-line ${l.hit ? "hit" : ""}" key=${i}>
                        <span class="t">${l.t}</span><span class="m">${l.m}</span>
                      </div>`)}
                  </div>
                </div>
              </div>`}
          </aside>

          <main style=${{ display: "flex", flexDirection: "column", gap: "1.25rem", minWidth: 0 }}>
            <div class="panel">
              <div class="panel-head"><${Icon} name="bolt" size=15 /><h2>New investigation</h2></div>
              <div class="panel-body">
                <div class="launch">
                  <div class="field">
                    <label for="q">Research question</label>
                    <textarea id="q" rows="3" value=${question} disabled=${running}
                              onChange=${(e) => setQuestion(e.target.value)} />
                  </div>
                  <${DropZone} file=${file} onFile=${setFile} />
                  <div style=${{ display: "flex", gap: ".6rem", alignItems: "center" }}>
                    <button class="btn btn-primary" onClick=${launch} disabled=${running || !question.trim()}>
                      <${Icon} name=${running ? "clock" : "hunt"} size=16 />
                      ${running ? "Investigating…" : "Start falsification run"}
                    </button>
                    ${file && !running && html`
                      <button class="btn btn-ghost" onClick=${() => setFile(null)}>
                        <${Icon} name="x" size=14 /> Clear document
                      </button>`}
                  </div>
                  ${error && html`
                    <div class="alert-injection" style=${{ background: "none" }}>
                      <div class="hd"><${Icon} name="shieldAlert" size=16 /> ${error}</div>
                    </div>`}
                </div>
              </div>
            </div>

            ${injections.map((a, i) => html`<${InjectionAlert} a=${a} key=${i} />`)}

            <div class="panel">
              <div class="panel-head">
                <${Icon} name="branch" size=15 /><h2>Hypotheses & evidence</h2>
                <span class="count">${hyps.length} claims · ${totalEvidence} evidence</span>
              </div>
              <div class="panel-body">
                ${hyps.length === 0
                  ? html`<div class="empty">
                      <${Icon} name="branch" size=26 />
                      <span class="t">${running ? "Framing hypotheses…" : "No run yet"}</span>
                      <span class="d">${running
                        ? "The agent is generating competing falsifiable claims."
                        : "Start a run to watch the agent generate competing claims and hunt for evidence that would kill each one."}</span>
                      ${running && html`<div class="skel" style=${{ width: "60%", marginTop: ".6rem" }} />`}
                    </div>`
                  : hyps.map((h) => html`
                      <${HypothesisCard} h=${h} evidence=${evidence[h.id] || []} key=${h.id} />`)}
              </div>
            </div>

            ${tickets.length > 0 && html`
              <div class="panel">
                <div class="panel-head">
                  <${Icon} name="dna" size=15 /><h2>Meta plane — strategy evolution</h2>
                  <span class="count">governed · held-out scored</span>
                </div>
                <div class="panel-body">
                  ${tickets.map((t, i) => html`<${TicketCard} t=${t} key=${i} />`)}
                  ${rollback && html`
                    <div class="ticket" style=${{ borderLeftColor: "var(--violet)" }}>
                      <div class="hd">
                        <${Icon} name="rewind" size=15 style=${{ color: "var(--violet)" }} /> Rollback executed
                      </div>
                      <div class="why">
                        Regression caught after promotion — restored the previously active version.
                      </div>
                      <div class="score-row">
                        <span class="score-after down">${rollback.bad_version_accuracy.toFixed(3)}</span>
                        <span class="arrow">→</span>
                        <span class="score-after up">${rollback.restored_version_accuracy.toFixed(3)}</span>
                        <${Chip} kind="meta">v ${rollback.rolled_back_to.slice(0, 8)}<//>
                      </div>
                    </div>`}
                </div>
              </div>`}

            <${Metrics} report=${report} />
          </main>
        </div>
      </div>`;
  }

  ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
})();
