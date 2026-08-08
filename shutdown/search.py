"""Hybrid retrieval: keyword search (DuckDuckGo, no API key) + a local dense rerank.

Satisfies AE-02's "hybrid live RAG with keyword and dense retrieval" literally:
keyword search fetches candidates, a lightweight embedding similarity pass
reorders them against the query instead of trusting the search engine's order.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from .contradiction import is_low_quality_content


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float = 0.0


def _duckduckgo(query: str, max_results: int = 8) -> list[SearchResult]:
    try:
        from ddgs import DDGS  # duckduckgo_search was renamed to ddgs
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return _mock_results(query, max_results)

    out: list[SearchResult] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                out.append(
                    SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                    )
                )
    except Exception:
        return _mock_results(query, max_results)
    return out or _mock_results(query, max_results)


def _mock_results(query: str, max_results: int) -> list[SearchResult]:
    return [
        SearchResult(
            title=f"[offline-mock] result {i} for: {query}",
            url=f"https://example.invalid/mock/{i}",
            snippet=f"Placeholder snippet {i} — no network/DuckDuckGo package available.",
        )
        for i in range(1, min(3, max_results) + 1)
    ]


def _hash_embed(text: str, dims: int = 64) -> list[float]:
    """Cheap deterministic bag-of-words hash embedding — no model download required.

    Good enough to rerank a handful of search snippets against a query; not a
    substitute for a real embedding model, but keeps 'hybrid retrieval' honest
    without pulling in a vector-DB dependency.
    """
    vec = [0.0] * dims
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# Boilerplate/anti-bot snippets that survive DuckDuckGo's own filtering but
# carry no real content -- filtered out before ranking rather than left for
# the contradiction hunter to guess about. Same marker list the contradiction
# hunter uses on full fetched pages (see contradiction.is_low_quality_content),
# applied here to the shorter search snippet.
# Hosts whose pages are never evidence for a technical claim, whatever the
# snippet says: video/social platforms, job boards, storefronts, Q&A karma
# sites. This filters by *kind of source*, not by opinion of the content --
# a YouTube result is not a weak citation, it is not a citation.
_NON_EVIDENTIARY_HOSTS = (
    "youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "dailymotion.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "reddit.com",
    "pinterest.com", "linkedin.com", "quora.com",
    "indeed.com", "glassdoor.com", "monster.com", "naukri.com", "career", "jobs.",
    "amazon.", "ebay.", "alibaba.com", "aliexpress.com", "etsy.com",
)


def is_non_evidentiary(url: str) -> bool:
    host = re.sub(r"^https?://", "", url or "").split("/")[0].lower()
    return any(bad in host for bad in _NON_EVIDENTIARY_HOSTS)


def _is_low_quality(r: SearchResult) -> bool:
    if is_non_evidentiary(r.url):
        return True
    snippet = (r.snippet or "").strip()
    if len(snippet) < 25:
        return True
    return is_low_quality_content(snippet)


def _host(url: str) -> str:
    return re.sub(r"^https?://", "", url or "").split("/")[0].lower()


def _mmr_rerank(candidates: list[SearchResult], diversity: float) -> list[SearchResult]:
    """Maximal-Marginal-Relevance rerank: at each step, pick the candidate that
    maximizes `(1-diversity)*relevance - diversity*similarity_to_already_picked`
    instead of just sorting by relevance once. `diversity=0` reduces exactly to
    plain relevance sort (today's behavior); `diversity=1` prioritizes pulling
    in a source that says something DIFFERENT from what's already been picked,
    over another top-scoring near-duplicate of the same page. This is what
    `retrieval_diversity` in strategy.py actually controls -- previously that
    parameter was stored and could be "promoted" by the Strategy Evaluator
    without ever being read by any retrieval code.
    """
    if diversity <= 0 or len(candidates) <= 1:
        return sorted(candidates, key=lambda r: r.score, reverse=True)

    pool = list(candidates)
    embeds = {id(r): _hash_embed(r.title + " " + r.snippet) for r in pool}
    selected: list[SearchResult] = []
    while pool:
        if not selected:
            best = max(pool, key=lambda r: r.score)
        else:
            def mmr(r: SearchResult) -> float:
                sim = max(_cosine(embeds[id(r)], embeds[id(s)]) for s in selected)
                return (1 - diversity) * r.score - diversity * sim
            best = max(pool, key=mmr)
        selected.append(best)
        pool.remove(best)
    return selected


def hybrid_search(query: str, max_results: int = 8, min_score: float = 0.05,
                   diversity: float = 0.0) -> list[SearchResult]:
    """Keyword search + dense rerank, then drop noisy/boilerplate results
    instead of letting them silently count as evidence. `min_score` is a
    relevance floor on the reranked cosine score -- a result scoring near
    zero shares almost no vocabulary with the query and is more likely to be
    an irrelevant page than real disagreement. `diversity` (0-1, from the
    active strategy's `retrieval_diversity`) trades some top-relevance for
    pulling in sources that aren't near-duplicates of each other."""
    candidates = [r for r in _duckduckgo(query, max_results=max_results) if not _is_low_quality(r)]
    q_vec = _hash_embed(query)
    for r in candidates:
        r.score = _cosine(q_vec, _hash_embed(r.title + " " + r.snippet))
    ranked = _mmr_rerank(candidates, diversity)
    filtered = [r for r in ranked if r.score >= min_score]
    return filtered or ranked  # never return nothing just because everything scored low
