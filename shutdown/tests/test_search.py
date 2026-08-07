import unittest

from shutdown.search import SearchResult, _is_low_quality, is_non_evidentiary


class TestNonEvidentiaryHosts(unittest.TestCase):
    def test_rejects_video_and_social(self):
        for url in ("https://www.youtube.com/watch?v=abc", "https://reddit.com/r/x",
                    "https://twitter.com/someone/status/1"):
            self.assertTrue(is_non_evidentiary(url), url)

    def test_rejects_job_boards_and_storefronts(self):
        for url in ("https://career.wlgroup.eu/jobs/8149430-satcom-engineer",
                    "https://www.amazon.in/dp/B0001"):
            self.assertTrue(is_non_evidentiary(url), url)

    def test_accepts_technical_sources(self):
        for url in ("https://www.mathworks.com/help/satcom/gs/satellite-link-budget.html",
                    "https://en.wikipedia.org/wiki/Arbiter_(electronics)",
                    "https://ieeexplore.ieee.org/document/12345"):
            self.assertFalse(is_non_evidentiary(url), url)

    def test_host_match_is_not_substring_of_path(self):
        # a technical page that merely mentions a platform in its URL path
        # must not be rejected -- only the host is inspected
        self.assertFalse(is_non_evidentiary("https://arxiv.org/abs/youtube-recommender"))


class TestLowQualityFilter(unittest.TestCase):
    def test_short_snippet_rejected(self):
        self.assertTrue(_is_low_quality(SearchResult("t", "https://example.org/a", "tiny")))

    def test_anti_bot_snippet_rejected(self):
        self.assertTrue(_is_low_quality(
            SearchResult("t", "https://example.org/a", "Just a moment... Checking your browser before access")))

    def test_real_snippet_accepted(self):
        self.assertFalse(_is_low_quality(SearchResult(
            "Link budget", "https://example.org/a",
            "The link budget accounts for free-space path loss, antenna gain and transmit power across the channel.")))


if __name__ == "__main__":
    unittest.main()
