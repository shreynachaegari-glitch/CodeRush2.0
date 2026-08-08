"""AE-02 asks for long-term memory "with expiry rules". `expires_at` existed
on the schema from the start but nothing ever set it or read it -- these
cover that expiry is now real: a TTL is actually computed, prune_expired
actually deletes, and active_memory actually filters.
"""

import unittest
from datetime import datetime, timedelta, timezone

from shutdown import memory as memory_mod
from shutdown.db import Store, dumps, new_id, now


class TestExpiry(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def test_remember_sets_a_real_expiry_for_a_ttl_type(self):
        memory_id = memory_mod.remember(self.store, "unresolved_question", "run-1", {"x": 1}, provenance="test")
        row = self.store.read_one("SELECT * FROM memory WHERE memory_id = ?", (memory_id,))
        self.assertIsNotNone(row["expires_at"])

    def test_verdict_type_has_no_default_expiry(self):
        memory_id = memory_mod.remember(self.store, "verdict", "run-1", {"x": 1}, provenance="test")
        row = self.store.read_one("SELECT * FROM memory WHERE memory_id = ?", (memory_id,))
        self.assertIsNone(row["expires_at"])

    def test_prune_expired_actually_deletes_past_rows(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.store.insert("memory", {
            "memory_id": new_id(), "memory_type": "unresolved_question", "run_id": "run-1",
            "content": dumps({}), "provenance": "test", "created_at": now(), "expires_at": past,
        })
        deleted = memory_mod.prune_expired(self.store)
        self.assertEqual(deleted, 1)
        self.assertIsNone(self.store.read_one("SELECT * FROM memory WHERE run_id = 'run-1'"))

    def test_prune_expired_leaves_future_and_null_expiry_rows(self):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.store.insert("memory", {
            "memory_id": new_id(), "memory_type": "unresolved_question", "run_id": "run-2",
            "content": dumps({}), "provenance": "test", "created_at": now(), "expires_at": future,
        })
        memory_mod.remember(self.store, "verdict", "run-2", {}, provenance="test")  # no expiry
        deleted = memory_mod.prune_expired(self.store)
        self.assertEqual(deleted, 0)

    def test_active_memory_excludes_expired_rows_even_before_pruning(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.store.insert("memory", {
            "memory_id": new_id(), "memory_type": "unresolved_question", "run_id": "run-3",
            "content": dumps({}), "provenance": "test", "created_at": now(), "expires_at": past,
        })
        active = memory_mod.active_memory(self.store, memory_type="unresolved_question")
        self.assertEqual(active, [])

    def test_active_memory_filters_by_type(self):
        memory_mod.remember(self.store, "verdict", "run-4", {"a": 1}, provenance="test")
        memory_mod.remember(self.store, "synthesis", "run-4", {"b": 2}, provenance="test")
        only_verdicts = memory_mod.active_memory(self.store, memory_type="verdict")
        self.assertEqual(len(only_verdicts), 1)
        self.assertEqual(only_verdicts[0]["memory_type"], "verdict")


class TestRunGroundedMemory(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def test_only_alive_hypotheses_become_unresolved_questions(self):
        class FakeHyp:
            def __init__(self, hid, status):
                self.hypothesis_id = hid
                self.status = status
                self.statement = "s"
                self.confidence_current = 0.5
                self.stop_condition = "sc"

        hyps = [FakeHyp("h1", "alive"), FakeHyp("h2", "survived"), FakeHyp("h3", "eliminated")]
        ids = memory_mod.remember_unresolved_questions(self.store, "run-5", hyps)
        self.assertEqual(len(ids), 1)
        row = self.store.read_one("SELECT * FROM memory WHERE memory_id = ?", (ids[0],))
        self.assertEqual(row["memory_type"], "unresolved_question")

    def test_source_summary_counts_by_type(self):
        sources = [{"source_type": "pdf", "url_or_path": "a.pdf"},
                   {"source_type": "pdf", "url_or_path": "b.pdf"},
                   {"source_type": "web", "url_or_path": "https://x"}]
        memory_id = memory_mod.remember_source_summary(self.store, "run-6", "q", sources)
        row = self.store.read_one("SELECT * FROM memory WHERE memory_id = ?", (memory_id,))
        import json
        content = json.loads(row["content"])
        self.assertEqual(content["source_counts"], {"pdf": 2, "web": 1})

    def test_source_summary_with_no_sources_writes_nothing(self):
        self.assertIsNone(memory_mod.remember_source_summary(self.store, "run-7", "q", []))


if __name__ == "__main__":
    unittest.main()
