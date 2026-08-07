import unittest

from shutdown.planner import build_query

PROFILE = {"search_keywords": ["satellite", "link budget", "RF"]}


class TestBuildQuery(unittest.TestCase):
    def test_distills_a_long_statement_into_few_terms(self):
        statement = (
            "Single-master bus arbitration causes thermal budget failure due to master-node "
            "polling latency, which extends transmitter queue wait-times and inflates baseline "
            "thermal accumulation beyond dissipation capacity."
        )
        q = build_query(statement, PROFILE)
        # regression: the full sentence used to be the query, which returned
        # near-random pages and was the real source of "noisy web evidence"
        self.assertLess(len(q), len(statement))
        self.assertLessEqual(len(q.split()), 12)

    def test_drops_stopwords_and_hedges(self):
        q = build_query("The power draw exceeds the budget because of polling", PROFILE).lower()
        for dropped in ("the", "of", "because", "exceeds"):
            self.assertNotIn(f" {dropped} ", f" {q} ")

    def test_keeps_numbers_and_units(self):
        q = build_query("Power exceeds budget above 40% duty cycle at 12 GHz", PROFILE)
        self.assertIn("40%", q)
        self.assertIn("12", q)

    def test_appends_domain_keywords(self):
        q = build_query("Arbitration raises baseline load", PROFILE)
        self.assertIn("satellite", q)

    def test_empty_statement_still_yields_domain_anchored_query(self):
        self.assertTrue(build_query("", PROFILE).strip())


if __name__ == "__main__":
    unittest.main()
