"""Academic literature retrieval.

General web search returns Wikipedia, job listings and video pages -- fine for
answering a question, useless as *evidence* for a scientific claim. This module
queries scholarly indexes instead, so a hypothesis is tested against papers
that carry an author, a venue, a year, a DOI and a citation count.

Both backends are free and need no API key:
  - OpenAlex   — 250M+ works, citation counts, open-access links
  - arXiv      — preprints, reliable abstracts

stdlib only (urllib + json + xml), so this adds no dependency. Every failure
path degrades to an empty list; the caller falls back to web search.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date

# OpenAlex asks for a contact address in the UA for the polite pool (faster,
# more reliable). No account or key involved.
_UA = "Shutdown-ResearchAgent/1.0 (mailto:research-agent@example.org)"
_TIMEOUT = 15


@dataclass
class Paper:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    url: str = ""
    doi: str = ""
    abstract: str = ""
    citations: int = 0
    source: str = ""  # which index it came from

    @property
    def citation(self) -> str:
        """A human-readable citation line: 'Author et al. (2019), Venue'."""
        who = self.authors[0].split()[-1] if self.authors else "Unknown"
        if len(self.authors) > 1:
            who += " et al."
        bits = [who]
        if self.year:
            bits.append(f"({self.year})")
        if self.venue:
            bits.append(f"— {self.venue}")
        return " ".join(bits)

    def as_dict(self) -> dict:
        return {
            "title": self.title, "authors": self.authors, "year": self.year,
            "venue": self.venue, "url": self.url, "doi": self.doi,
            "citations": self.citations, "source": self.source,
            "citation": self.citation, "abstract": self.abstract[:600],
        }


def _get(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return r.read()
    except Exception:
        return None


def _reconstruct_abstract(inv: dict | None) -> str:
    """OpenAlex ships abstracts as an inverted index (word -> positions) for
    licensing reasons; rebuild the running text from it."""
    if not inv:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        positions.extend((i, word) for i in idxs)
    positions.sort()
    return " ".join(w for _, w in positions)


def search_openalex(query: str, limit: int = 4) -> list[Paper]:
    url = ("https://api.openalex.org/works?search="
           + urllib.parse.quote(query)
           + f"&per-page={limit}&sort=relevance_score:desc")
    raw = _get(url)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []

    out: list[Paper] = []
    for w in data.get("results", []):
        authors = [a.get("author", {}).get("display_name", "")
                   for a in (w.get("authorships") or [])[:6]]
        loc = (w.get("primary_location") or {}) or {}
        venue = ((loc.get("source") or {}) or {}).get("display_name", "") or ""
        # prefer a landing page a human can actually open
        url_ = loc.get("landing_page_url") or w.get("doi") or w.get("id") or ""
        out.append(Paper(
            title=(w.get("title") or "").strip(),
            authors=[a for a in authors if a],
            year=w.get("publication_year"),
            venue=venue,
            url=url_,
            doi=(w.get("doi") or "").replace("https://doi.org/", ""),
            abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
            citations=w.get("cited_by_count") or 0,
            source="OpenAlex",
        ))
    return [p for p in out if p.title]


_ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}


def search_arxiv(query: str, limit: int = 3) -> list[Paper]:
    url = ("http://export.arxiv.org/api/query?search_query=all:"
           + urllib.parse.quote(query)
           + f"&max_results={limit}&sortBy=relevance")
    raw = _get(url)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []

    out: list[Paper] = []
    for e in root.findall("a:entry", _ARXIV_NS):
        title = (e.findtext("a:title", "", _ARXIV_NS) or "").strip().replace("\n", " ")
        summary = (e.findtext("a:summary", "", _ARXIV_NS) or "").strip().replace("\n", " ")
        link = e.findtext("a:id", "", _ARXIV_NS) or ""
        published = e.findtext("a:published", "", _ARXIV_NS) or ""
        authors = [a.findtext("a:name", "", _ARXIV_NS) or ""
                   for a in e.findall("a:author", _ARXIV_NS)][:6]
        out.append(Paper(
            title=title, authors=[a for a in authors if a],
            year=int(published[:4]) if published[:4].isdigit() else None,
            venue="arXiv preprint", url=link, abstract=summary,
            source="arXiv",
        ))
    return [p for p in out if p.title]


def _dedupe(papers: list[Paper]) -> list[Paper]:
    seen: set[str] = set()
    out: list[Paper] = []
    for p in papers:
        key = "".join(ch for ch in p.title.lower() if ch.isalnum())[:70]
        if key and key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _recency_weight(year: int | None, *, today: date | None = None) -> float:
    """Exponential decay favoring recent work: a paper published this year
    scores ~1.0, one 8 years old ~0.37, older asymptotically toward 0. An
    unknown year is scored as moderately stale (neither rewarded nor zeroed
    out) rather than penalized as if it were ancient. `today` is injectable
    for deterministic tests -- real callers never pass it."""
    year_now = (today or date.today()).year
    if not year:
        return 0.3
    age_years = max(0, year_now - year)
    return math.exp(-age_years / 8.0)


def _rank_score(p: Paper, *, today: date | None = None) -> float:
    """Standing (citations, log-scaled so one outlier paper can't dominate)
    blended with recency. Citations still carry more absolute weight than
    recency alone -- a landmark paper from 2015 should usually beat a
    just-published preprint saying the same thing with zero citations yet --
    but a claim about *current* conditions can now be won by a fresher, less-
    cited source instead of recency being ignored entirely (previously `year`
    was only a tiebreaker after citations, which is not what AE-02's
    "time-aware ranking" requirement asks for)."""
    citation_weight = math.log1p(p.citations)
    return citation_weight + 2.0 * _recency_weight(p.year, today=today)


def search_literature(query: str, limit: int = 4) -> list[Paper]:
    """Peer-reviewed indexes first, preprints second -- but "first" now means
    citations-plus-recency, not citations alone.

    arXiv results carry no citation count, so they lean entirely on recency;
    a very recent preprint can still outrank a stale indexed paper, which is
    correct for a claim about current conditions, but won't usually beat a
    well-cited recent one -- a preprint is real evidence, not a tiebreaker of
    last resort.
    """
    papers = _dedupe(search_openalex(query, limit) + search_arxiv(query, max(1, limit // 2)))
    papers.sort(key=_rank_score, reverse=True)
    return papers[:limit]
