"""Lightweight trace viewer + machine-readable research package bundler.

No external tracing service (Langfuse etc.) -- renders straight from the
SQLite store, per the locked scope decision to avoid a second service to
keep alive during the demo.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .db import Store
from .evidence import graph_for_run


_STATUS_COLOR = {"eliminated": "#c0392b", "survived": "#1e8449", "alive": "#b9770e"}
_RELATION_COLOR = {"supports": "#1e8449", "weakens": "#b9770e", "refutes": "#c0392b", "unknown": "#7f8c8d"}
_APPROVAL_COLOR = {"approved": "#1e8449", "rejected": "#c0392b", "pending": "#b9770e"}


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_trace_html(store: Store, run_id: str) -> str:
    run = store.read_one("SELECT * FROM runs WHERE run_id = ?", (run_id,))
    graph = graph_for_run(store, run_id)
    approvals = store.read("SELECT * FROM approvals WHERE run_id = ? ORDER BY requested_at", (run_id,))
    tickets = store.read("SELECT * FROM evolution_tickets WHERE raised_from_run_id = ?", (run_id,))
    rollbacks = store.read("SELECT * FROM memory WHERE memory_type = 'rollback_event' ORDER BY created_at")

    css = """
    body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;margin:2rem auto;
         padding:0 1rem;color:#1c1c1c;background:#fafafa}
    h1{font-size:1.4rem} h2{font-size:1.1rem;margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:.25rem}
    .meta{color:#555;font-size:.9rem}
    .hyp{border:1px solid #ddd;border-radius:8px;padding:.75rem 1rem;margin:.75rem 0;background:#fff}
    .hyp-head{display:flex;justify-content:space-between;align-items:center;gap:1rem}
    .badge{display:inline-block;color:#fff;border-radius:4px;padding:.1rem .5rem;font-size:.75rem;font-weight:600}
    .bar-track{background:#eee;border-radius:6px;height:10px;margin:.4rem 0 .6rem}
    .bar-fill{height:10px;border-radius:6px}
    .ev-list{list-style:none;padding:0;margin:0;font-size:.85rem}
    .ev-list li{padding:.25rem 0;border-top:1px dashed #eee}
    .tag{display:inline-block;color:#fff;border-radius:3px;padding:0 .35rem;font-size:.7rem;margin-right:.4rem}
    table{border-collapse:collapse;width:100%;font-size:.85rem}
    td,th{border-bottom:1px solid #eee;padding:.35rem .5rem;text-align:left}
    """

    parts = [f"<style>{css}</style>", f"<h1>Run {_esc(run_id)}</h1>",
             f"<p class='meta'>Question: {_esc(run['question'] if run else '?')}</p>",
             f"<p class='meta'>Status: {_esc(run['status'] if run else '?')} &middot; "
             f"Human interventions: {run['human_interventions'] if run else 0} &middot; "
             f"Cost: {run['total_cost_tokens'] if run else 0} tokens "
             f"(~${run['total_cost_usd'] if run else 0:.5f})</p>"]

    parts.append("<h2>Hypotheses &amp; Evidence Graph</h2>")
    for h in graph["hypotheses"]:
        color = _STATUS_COLOR.get(h["status"], "#7f8c8d")
        pct = round(h["confidence"] * 100)
        parts.append("<div class='hyp'>")
        parts.append(
            f"<div class='hyp-head'><div>{_esc(h['statement'])}</div>"
            f"<span class='badge' style='background:{color}'>{_esc(h['status'])} {pct}%</span></div>"
        )
        parts.append(f"<div class='bar-track'><div class='bar-fill' style='width:{pct}%;background:{color}'></div></div>")
        parts.append("<ul class='ev-list'>")
        for e in h["evidence"]:
            rcolor = _RELATION_COLOR.get(e["relation"], "#7f8c8d")
            cls = f"<span class='tag' style='background:#555'>{_esc(e['contradiction_class'])}</span>" if e["contradiction_class"] else ""
            parts.append(
                f"<li><span class='tag' style='background:{rcolor}'>{_esc(e['relation'])}</span>{cls}"
                f"{_esc(e['url_or_path'])} <span class='meta'>(conf {e['confidence']:.2f})</span></li>"
            )
        parts.append("</ul></div>")

    parts.append("<h2>Approval Gates</h2><table><tr><th>Action</th><th>Status</th><th>Requested</th></tr>")
    for a in approvals:
        color = _APPROVAL_COLOR.get(a["status"], "#7f8c8d")
        parts.append(
            f"<tr><td>{_esc(a['action_type'])}</td>"
            f"<td><span class='badge' style='background:{color}'>{_esc(a['status'])}</span></td>"
            f"<td class='meta'>{_esc(a['requested_at'])}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>Evolution Tickets</h2><table><tr><th>Failure</th><th>Decision</th><th>Before &rarr; After</th></tr>")
    for t in tickets:
        before = json.loads(t["held_out_result_before"])["accuracy"] if t["held_out_result_before"] else "-"
        after = json.loads(t["held_out_result_after"])["accuracy"] if t["held_out_result_after"] else "-"
        parts.append(
            f"<tr><td>{_esc(t['failure_description'])}</td><td>{_esc(t['decision'])}</td>"
            f"<td>{before} &rarr; {after}</td></tr>"
        )
    parts.append("</table>")

    if rollbacks:
        parts.append("<h2>Rollback Events</h2><ul class='ev-list'>")
        for r in rollbacks:
            parts.append(f"<li>{_esc(r['content'])} <span class='meta'>({_esc(r['created_at'])})</span></li>")
        parts.append("</ul>")

    return "<html><head><title>Shutdown trace</title></head><body>" + "\n".join(parts) + "</body></html>"


def render_trace_cli(store: Store, run_id: str) -> str:
    run = store.read_one("SELECT * FROM runs WHERE run_id = ?", (run_id,))
    graph = graph_for_run(store, run_id)
    lines = [f"Run {run_id}", f"Question: {run['question'] if run else '?'}", ""]
    for h in graph["hypotheses"]:
        lines.append(f"  [{h['status']:<10} {h['confidence']:.2f}] {h['statement']}")
        for e in h["evidence"]:
            cls = f" ({e['contradiction_class']})" if e["contradiction_class"] else ""
            lines.append(f"      - {e['relation']}{cls}: {e['url_or_path']}")
    return "\n".join(lines)


def build_research_package(store: Store, run_id: str, out_dir: str | Path,
                            extra_files: dict | None = None) -> Path:
    """Bundles report + evidence graph + trace + strategy diff into one
    research_package.zip -- the handbook's own term for this deliverable.
    `extra_files` maps archive filename -> JSON-serializable object (used for
    the evaluation report)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"research_package_{run_id}.zip"

    graph = graph_for_run(store, run_id)
    run = store.read_one("SELECT * FROM runs WHERE run_id = ?", (run_id,))
    tickets = [dict(t) for t in store.read("SELECT * FROM evolution_tickets WHERE raised_from_run_id = ?", (run_id,))]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("evidence_graph.json", json.dumps(graph, indent=2, default=str))
        zf.writestr("run.json", json.dumps(dict(run) if run else {}, indent=2, default=str))
        zf.writestr("evolution_tickets.json", json.dumps(tickets, indent=2, default=str))
        zf.writestr("trace.html", render_trace_html(store, run_id))
        zf.writestr("trace.txt", render_trace_cli(store, run_id))
        for name, obj in (extra_files or {}).items():
            zf.writestr(name, json.dumps(obj, indent=2, default=str))

    return zip_path
