import unittest

from shutdown.db import Store, new_id
from shutdown.evidence import add_evidence, add_source, update_confidence


class TestConfidenceUpdate(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.hyp_id = new_id()
        self.store.insert(
            "hypotheses",
            {
                "hypothesis_id": self.hyp_id, "run_id": new_id(), "statement": "test",
                "confidence_prior": 0.5, "confidence_current": 0.5,
                "expected_supporting_evidence": "", "expected_contradicting_evidence": "",
                "stop_condition": "", "status": "alive",
            },
        )

    def test_refutes_pulls_confidence_down_and_eventually_eliminates(self):
        conf = update_confidence(self.store, self.hyp_id, "refutes")
        self.assertAlmostEqual(conf, 0.15)
        row = self.store.read_one("SELECT status FROM hypotheses WHERE hypothesis_id = ?", (self.hyp_id,))
        self.assertEqual(row["status"], "eliminated")  # 0.15 lands exactly on the elimination boundary

    def test_supports_pushes_confidence_up(self):
        conf = update_confidence(self.store, self.hyp_id, "supports")
        self.assertAlmostEqual(conf, 0.62)

    def test_custom_deltas_override_default_rule(self):
        conf = update_confidence(self.store, self.hyp_id, "weakens", deltas={"weakens": -0.5})
        self.assertAlmostEqual(conf, 0.0)


if __name__ == "__main__":
    unittest.main()
