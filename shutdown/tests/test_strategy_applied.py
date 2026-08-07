"""The meta plane only means something if its output reaches the control
plane. These cover that seam -- a promoted strategy must actually change how
the next run scores evidence, and the version used must be recorded.
"""

import unittest

from shutdown import strategy as strategy_mod
from shutdown.db import Store, new_id
from shutdown.evidence import update_confidence


class TestActiveStrategyReachesControlPlane(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def _new_hypothesis(self) -> str:
        hyp_id = new_id()
        self.store.insert(
            "hypotheses",
            {
                "hypothesis_id": hyp_id, "run_id": new_id(), "statement": "test",
                "confidence_prior": 0.5, "confidence_current": 0.5,
                "expected_supporting_evidence": "", "expected_contradicting_evidence": "",
                "stop_condition": "", "status": "alive",
            },
        )
        return hyp_id

    def test_promoted_strategy_changes_the_delta_actually_applied(self):
        ticket_id = strategy_mod.raise_ticket(
            self.store, run_id=new_id(),
            failure_description="x", root_cause="x", hypothesis="x",
            proposed_diff={"confidence_deltas": {"weakens": -0.30}},
            expected_gain="x", risk="x",
        )
        strategy_mod.finalize_ticket(self.store, ticket_id, approved=True)

        deltas = strategy_mod.active_strategy(self.store)["strategy"]["confidence_deltas"]
        self.assertAlmostEqual(deltas["weakens"], -0.30)

        # regression: main.py used to call update_confidence() without deltas,
        # so a promoted strategy never affected a single real run
        conf = update_confidence(self.store, self._new_hypothesis(), "weakens", deltas=deltas)
        self.assertAlmostEqual(conf, 0.20)

    def test_default_strategy_is_not_mutated_by_callers(self):
        active = strategy_mod.active_strategy(self.store)
        active["strategy"]["confidence_deltas"]["supports"] = 99.0
        fresh = strategy_mod.active_strategy(self.store)
        self.assertNotEqual(fresh["strategy"]["confidence_deltas"]["supports"], 99.0)

    def test_rollback_restores_the_previous_delta(self):
        before = strategy_mod.active_version_id(self.store)
        ticket_id = strategy_mod.raise_ticket(
            self.store, run_id=new_id(),
            failure_description="x", root_cause="x", hypothesis="x",
            proposed_diff={"confidence_deltas": {"refutes": 0.0}},
            expected_gain="x", risk="x",
        )
        strategy_mod.finalize_ticket(self.store, ticket_id, approved=True)
        self.assertAlmostEqual(
            strategy_mod.active_strategy(self.store)["strategy"]["confidence_deltas"]["refutes"], 0.0
        )

        strategy_mod.rollback(self.store, before, run_id="run-1", reason="regression")
        self.assertAlmostEqual(
            strategy_mod.active_strategy(self.store)["strategy"]["confidence_deltas"]["refutes"], -0.35
        )

    def test_rollback_event_is_attributed_to_its_run(self):
        before = strategy_mod.active_version_id(self.store)
        strategy_mod.rollback(self.store, before, run_id="run-42")
        rows = self.store.read(
            "SELECT * FROM memory WHERE memory_type = 'rollback_event' AND run_id = ?", ("run-42",)
        )
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
