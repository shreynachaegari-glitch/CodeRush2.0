/* Evidence graph — canvas force layout.
   Hand-written rather than pulling in d3: the simulation we need is three
   forces and ~120 lines, and this keeps the app dependency-free and offline.

   Edges grow in rather than appearing, because the graph is a record of an
   investigation unfolding — motion here carries meaning, not decoration. */
(function () {
  const REL = {
    supports:    { color: "#5ec98a", label: "supports" },
    weakens:     { color: "#e0a942", label: "weakens" },
    refutes:     { color: "#ef6a80", label: "refutes" },
    unknown:     { color: "#5c6a7d", label: "unknown" },
    verified_by: { color: "#4cc4dd", label: "verified by" },
  };
  const STATUS = { survived: "#5ec98a", eliminated: "#ef6a80", alive: "#e0a942" };

  class EvidenceGraph {
    constructor(canvas) {
      this.c = canvas;
      this.ctx = canvas.getContext("2d");
      this.nodes = [];
      this.edges = [];
      this.hover = null;
      this.t = 0;
      this.raf = null;
      this.dpr = Math.min(2, window.devicePixelRatio || 1);

      this._onMove = (e) => {
        const r = this.c.getBoundingClientRect();
        this.mx = e.clientX - r.left;
        this.my = e.clientY - r.top;
      };
      this._onLeave = () => { this.mx = this.my = null; this.hover = null; };
      canvas.addEventListener("mousemove", this._onMove);
      canvas.addEventListener("mouseleave", this._onLeave);
      canvas.addEventListener("dblclick", () => {
        if (this.hover && this.hover.kind === "source" && /^https?:/.test(this.hover.label))
          window.open(this.hover.label, "_blank", "noopener");
      });

      this.resize();
      this._ro = new ResizeObserver(() => this.resize());
      this._ro.observe(canvas.parentElement || canvas);
    }

    resize() {
      const p = this.c.parentElement;
      const w = (p ? p.clientWidth : 800), h = (p ? p.clientHeight : 460);
      this.w = w; this.h = h;
      this.c.width = w * this.dpr;
      this.c.height = h * this.dpr;
      this.c.style.width = w + "px";
      this.c.style.height = h + "px";
      this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    }

    /* Merge, never replace: existing nodes keep their positions so the layout
       doesn't jump every time a new piece of evidence lands. */
    setData({ nodes, edges }) {
      const byId = new Map(this.nodes.map((n) => [n.id, n]));
      this.nodes = nodes.map((n) => {
        const prev = byId.get(n.id);
        if (prev) return Object.assign(prev, n);
        const hyp = n.kind === "hypothesis";
        return Object.assign({
          x: this.w / 2 + (Math.random() - .5) * (hyp ? 140 : 320),
          y: this.h / 2 + (Math.random() - .5) * (hyp ? 140 : 260),
          vx: 0, vy: 0, born: performance.now(),
        }, n);
      });
      const known = new Set(this.edges.map((e) => e.from + ">" + e.to + e.relation));
      this.edges = edges.map((e) => {
        const k = e.from + ">" + e.to + e.relation;
        return Object.assign({ born: known.has(k) ? 0 : performance.now() }, e);
      });
      this.index = new Map(this.nodes.map((n) => [n.id, n]));
      if (!this.raf) this.start();
    }

    start() { const loop = () => { this.step(); this.draw(); this.raf = requestAnimationFrame(loop); }; loop(); }
    stop() { cancelAnimationFrame(this.raf); this.raf = null;
             this.c.removeEventListener("mousemove", this._onMove);
             this.c.removeEventListener("mouseleave", this._onLeave);
             this._ro && this._ro.disconnect(); }

    radius(n) { return n.kind === "hypothesis" ? 20 : n.kind === "verification" ? 11 : 9; }

    step() {
      this.t++;
      const N = this.nodes, cx = this.w / 2, cy = this.h / 2;

      for (let i = 0; i < N.length; i++) {
        const a = N[i];
        // gentle pull to centre keeps the graph framed
        a.vx += (cx - a.x) * (a.kind === "hypothesis" ? 0.0022 : 0.0012);
        a.vy += (cy - a.y) * (a.kind === "hypothesis" ? 0.0022 : 0.0012);

        for (let j = i + 1; j < N.length; j++) {
          const b = N[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) { dx = Math.random() - .5; dy = Math.random() - .5; d2 = 1; }
          const min = this.radius(a) + this.radius(b) + 34;
          if (d2 < min * min * 4) {
            const d = Math.sqrt(d2), f = (min * 2 - d) / d * 0.045;
            a.vx -= dx * f; a.vy -= dy * f;
            b.vx += dx * f; b.vy += dy * f;
          }
        }
      }

      for (const e of this.edges) {
        const a = this.index.get(e.from), b = this.index.get(e.to);
        if (!a || !b) continue;
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.hypot(dx, dy) || 1;
        const rest = 118;
        const f = (d - rest) * 0.0055;
        a.vx += dx / d * f; a.vy += dy / d * f;
        b.vx -= dx / d * f; b.vy -= dy / d * f;
      }

      for (const n of N) {
        n.vx *= 0.86; n.vy *= 0.86;
        n.x += n.vx; n.y += n.vy;
        const r = this.radius(n) + 8;
        n.x = Math.max(r, Math.min(this.w - r, n.x));
        n.y = Math.max(r, Math.min(this.h - r, n.y));
      }

      this.hover = null;
      if (this.mx != null) {
        let best = 1e9;
        for (const n of N) {
          const d = Math.hypot(n.x - this.mx, n.y - this.my);
          if (d < this.radius(n) + 10 && d < best) { best = d; this.hover = n; }
        }
        this.c.style.cursor = this.hover ? "pointer" : "default";
      }
    }

    draw() {
      const g = this.ctx, now = performance.now();
      g.clearRect(0, 0, this.w, this.h);

      for (const e of this.edges) {
        const a = this.index.get(e.from), b = this.index.get(e.to);
        if (!a || !b) continue;
        const grow = e.born ? Math.min(1, (now - e.born) / 620) : 1;
        const ease = 1 - Math.pow(1 - grow, 3);
        const rel = REL[e.relation] || REL.unknown;
        const dim = this.hover && this.hover !== a && this.hover !== b;

        g.save();
        g.globalAlpha = (dim ? 0.12 : 0.5) * ease;
        g.strokeStyle = rel.color;
        g.lineWidth = e.relation === "refutes" ? 2 : 1.2;
        if (e.relation === "unknown") g.setLineDash([3, 4]);
        // slight arc so parallel edges stay distinguishable
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        const nx = -(b.y - a.y) * 0.11, ny = (b.x - a.x) * 0.11;
        g.beginPath();
        g.moveTo(a.x, a.y);
        g.quadraticCurveTo(mx + nx, my + ny, a.x + (b.x - a.x) * ease, a.y + (b.y - a.y) * ease);
        g.stroke();
        g.restore();
      }

      for (const n of this.nodes) {
        const r = this.radius(n);
        const appear = Math.min(1, (now - n.born) / 500);
        const s = 1 - Math.pow(1 - appear, 3);
        const dim = this.hover && this.hover !== n;
        g.save();
        g.globalAlpha = dim ? 0.35 : 1;
        g.translate(n.x, n.y);
        g.scale(s, s);

        if (n.kind === "hypothesis") {
          const col = STATUS[n.status] || STATUS.alive;
          g.beginPath(); g.arc(0, 0, r + 5, 0, 7); g.fillStyle = col + "1a"; g.fill();
          // confidence arc — the ring reads as a gauge, not an outline
          g.beginPath(); g.arc(0, 0, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (n.confidence || 0));
          g.strokeStyle = col; g.lineWidth = 3; g.lineCap = "round"; g.stroke();
          g.beginPath(); g.arc(0, 0, r, 0, 7); g.strokeStyle = col + "33"; g.lineWidth = 3; g.stroke();
          g.fillStyle = "#0b0e13"; g.beginPath(); g.arc(0, 0, r - 4, 0, 7); g.fill();
          g.fillStyle = col; g.font = "600 10px ui-monospace, monospace";
          g.textAlign = "center"; g.textBaseline = "middle";
          g.fillText(Math.round((n.confidence || 0) * 100), 0, 0);
        } else if (n.kind === "verification") {
          g.rotate(Math.PI / 4);
          g.fillStyle = "#4cc4dd22"; g.strokeStyle = "#4cc4dd"; g.lineWidth = 1.4;
          g.fillRect(-r, -r, r * 2, r * 2); g.strokeRect(-r, -r, r * 2, r * 2);
        } else {
          g.beginPath(); g.arc(0, 0, r, 0, 7);
          g.fillStyle = "#161d28"; g.fill();
          g.strokeStyle = "#33465c"; g.lineWidth = 1.3; g.stroke();
          g.beginPath(); g.arc(0, 0, 3, 0, 7); g.fillStyle = "#7d8fa6"; g.fill();
        }
        g.restore();
      }

      if (this.hover) this.tooltip(this.hover);
    }

    tooltip(n) {
      const g = this.ctx;
      const lines = n.kind === "hypothesis"
        ? [n.label, `confidence ${Math.round((n.confidence || 0) * 100)}% · ${n.status}`]
        : [n.label, n.kind === "verification" ? "sandboxed recompute" : `source · ${n.source_type || "?"}`];

      g.font = "12px Inter, system-ui, sans-serif";
      const wrap = [];
      for (const [i, line] of lines.entries()) {
        if (i === 0) {
          let cur = "";
          for (const word of String(line).split(" ")) {
            if (g.measureText(cur + word).width > 250) { wrap.push(cur); cur = word + " "; }
            else cur += word + " ";
          }
          wrap.push(cur);
        } else wrap.push(line);
      }
      const w = Math.min(266, Math.max(...wrap.map((l) => g.measureText(l).width)) + 20);
      const h = wrap.length * 17 + 14;
      let x = n.x + 18, y = n.y - h / 2;
      if (x + w > this.w) x = n.x - w - 18;
      if (y < 4) y = 4;
      if (y + h > this.h) y = this.h - h - 4;

      g.save();
      g.fillStyle = "rgba(10,13,18,.96)"; g.strokeStyle = "#2a3646"; g.lineWidth = 1;
      g.beginPath(); g.roundRect(x, y, w, h, 9); g.fill(); g.stroke();
      g.textAlign = "left"; g.textBaseline = "top";
      wrap.forEach((l, i) => {
        g.fillStyle = i === 0 ? "#e8eef6" : "#8fa0b4";
        g.font = i === 0 ? "500 12px Inter, sans-serif" : "11px ui-monospace, monospace";
        g.fillText(l, x + 10, y + 8 + i * 17);
      });
      g.restore();
    }
  }

  window.EvidenceGraph = EvidenceGraph;
  window.GRAPH_REL = REL;
})();
