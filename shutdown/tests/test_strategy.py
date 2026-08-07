import unittest

from shutdown.strategy import DEFAULT_STRATEGY, is_policy_violation, score_strategy


class TestScoreStrategy(unittest.TestCase):
    def test_perfect_accuracy_on_trivial_case(self):
        held_out = [{"start_confidence": 0.5, "evidence_sequence": ["refutes", "refutes"], "expected_status": "eliminated"}]
        result = score_strategy(DEFAULT_STRATEGY, held_out)
        self.assertEqual(result["accuracy"], 1.0)

    def test_float_drift_at_boundary_does_not_misclassify(self):
        # 0.5 + supports*? crafted to land exactly on a classification edge after
        # float arithmetic -- regression test for the float-drift bug noted in HANDOFF.md
        held_out = [{"start_confidence": 0.85, "evidence_sequence": ["weakens", "weakens", "weakens", "weakens"],
                     "expected_status": "alive"}]
        result = score_strategy(DEFAULT_STRATEGY, held_out)
        self.assertEqual(result["n_correct"], 1)

    def test_empty_held_out_set_does_not_divide_by_zero(self):
        result = score_strategy(DEFAULT_STRATEGY, [])
        self.assertEqual(result["accuracy"], 0.0)


class TestPolicyGuard(unittest.TestCase):
    def test_allows_confidence_delta_change(self):
        self.assertFalse(is_policy_violation({"confidence_deltas": {"weakens": -0.1}}))

    def test_rejects_trusted_control_change(self):
        self.assertTrue(is_policy_violation({"approval_policy": "auto_approve_all"}))

    def test_rejects_sandbox_limit_change(self):
        self.assertTrue(is_policy_violation({"sandbox_limits": {"timeout": 999}}))


if __name__ == "__main__":
    unittest.main()
