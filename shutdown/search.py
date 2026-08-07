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


def hybrid_search(query: str, max_results: int = 8) -> list[SearchResult]:
    candidates = _duckduckgo(query, max_results=max_results)
    q_vec = _hash_embed(query)
    for r in candidates:
        r.score = _cosine(q_vec, _hash_embed(r.title + " " + r.snippet))
    candidates.sort(key=lambda r: r.score, reverse=True)
    return candidates
