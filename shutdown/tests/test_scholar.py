"""AE-02 asks for time-aware ranking, not just a citation-count sort. These
cover that recency is an actual, measurable input to ranking -- not just a
tiebreaker after citations, which is what the ranking did before."""

import unittest
from datetime import date

from shutdown.scholar import Paper, _rank_score, _recency_weight


class TestRecencyWeight(unittest.TestCase):
    def test_current_year_scores_near_one(self):
        self.assertAlmostEqual(_recency_weight(2026, today=date(2026, 1, 1)), 1.0, places=2)

    def test_older_paper_scores_lower_than_newer(self):
        older = _recency_weight(2010, today=date(2026, 1, 1))
        newer = _recency_weight(2024, today=date(2026, 1, 1))
        self.assertLess(older, newer)

    def test_unknown_year_is_not_zeroed_out(self):
        self.assertGreater(_recency_weight(None), 0.0)


class TestRankScore(unittest.TestCase):
    def test_a_fresh_source_can_outrank_a_slightly_more_cited_stale_one(self):
        today = date(2026, 8, 8)
        fresh = Paper(title="fresh", citations=20, year=2026)
        stale = Paper(title="stale", citations=25, year=2015)
        # under a citations-only sort, stale (25 > 20) would always win;
        # time-aware ranking should be able to flip that for a big age gap
        self.assertGreater(_rank_score(fresh, today=today), _rank_score(stale, today=today))

    def test_a_landmark_paper_still_beats_a_barely_cited_fresh_one(self):
        today = date(2026, 8, 8)
        landmark = Paper(title="landmark", citations=500, year=2010)
        brand_new = Paper(title="new", citations=1, year=2026)
        # recency should not fully override real standing
        self.assertGreater(_rank_score(landmark, today=today), _rank_score(brand_new, today=today))


if __name__ == "__main__":
    unittest.main()
