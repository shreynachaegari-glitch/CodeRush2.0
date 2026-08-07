"""Single-writer SQLite store for Shutdown.

WAL mode + a process-wide lock around every write serializes concurrent
agent writes (Hypothesis Framer, Contradiction Hunter, Verification Agent,
Strategy Evaluator all touch the same store). Reads don't take the lock.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    question TEXT,
    started_at TEXT,
    finished_at TEXT,
    status TEXT,
    strategy_version_id TEXT,
    total_cost_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0,
    human_interventions INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    run_id TEXT,
    statement TEXT,
    confidence_prior REAL,
    confidence_current REAL,
    expected_supporting_evidence TEXT,
    expected_contradicting_evidence TEXT,
    stop_condition TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    run_id TEXT,
    url_or_path TEXT,
    fetched_at TEXT,
    source_type TEXT,
    content_hash TEXT,
    injection_flagged INTEGER DEFAULT 0,
    injection_detail TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    hypothesis_id TEXT,
    source_id TEXT,
    relation TEXT,
    contradiction_class TEXT,
    confidence REAL,
    transformation TEXT,
    timestamp TEXT
);

CREATE TABLE IF NOT EXISTS strategy_versions (
    version_id TEXT PRIMARY KEY,
    parent_version_id TEXT,
    created_at TEXT,
    diff_json TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS evolution_tickets (
    ticket_id TEXT PRIMARY KEY,
    raised_from_run_id TEXT,
    failure_description TEXT,
    root_cause TEXT,
    hypothesis TEXT,
    proposed_version_id TEXT,
    expected_gain TEXT,
    risk TEXT,
    eval_metric TEXT,
    held_out_result_before TEXT,
    held_out_result_after TEXT,
    decision TEXT,
    cost_tokens_spent INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT,
    ticket_id TEXT,
    action_type TEXT,
    context_snapshot TEXT,
    status TEXT,
    requested_at TEXT,
    resolved_at TEXT,
    resolved_by TEXT
);

CREATE TABLE IF NOT EXISTS memory (
    memory_id TEXT PRIMARY KEY,
    memory_type TEXT,
    content TEXT,
    provenance TEXT,
    created_at TEXT,
    expires_at TEXT
);
"""

_write_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Store:
    def __init__(self, path: str | Path = "shutdown.db"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # -- single-writer gate ------------------------------------------------
    @contextmanager
    def write(self):
        with _write_lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def read(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        cur = self._conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()

    def read_one(self, query: str, params: tuple = ()) -> sqlite3.Row | None:
        rows = self.read(query, params)
        return rows[0] if rows else None

    # -- convenience insert helpers ----------------------------------------
    def insert(self, table: str, row: dict) -> None:
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        with self.write() as cur:
            cur.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                tuple(row.values()),
            )

    def update(self, table: str, key_col: str, key_val: str, fields: dict) -> None:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        with self.write() as cur:
            cur.execute(
                f"UPDATE {table} SET {set_clause} WHERE {key_col} = ?",
                (*fields.values(), key_val),
            )

    def close(self) -> None:
        self._conn.close()


def dumps(obj) -> str:
    return json.dumps(obj, default=str)
