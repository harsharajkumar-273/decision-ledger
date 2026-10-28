"""External fact checks with Tavily: has the world moved on from this decision?

Web evidence is deliberately conservative. Finding a deprecation signal adds
contradicting evidence (which turns a clean repo verdict into 'needs review');
finding nothing adds neutral evidence, never support."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Callable, Optional

from .schema import Claim, Evidence

SIGNAL = re.compile(
    r"(deprecated|end[- ]of[- ]life|\beol\b|unmaintained|no longer maintained|archived|sunset|reached end of support)",
    re.I,
)

Fetcher = Callable[[str], list[dict]]
_fetcher: Optional[Fetcher] = None


def set_fetcher(fn: Optional[Fetcher]) -> None:
    global _fetcher
    _fetcher = fn


def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    if _fetcher is not None:
        return _fetcher(query)
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps({"query": query, "max_results": max_results, "search_depth": "basic"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read()).get("results", [])


def web_evidence(claim: Claim) -> list[Evidence]:
    if _fetcher is None and not os.getenv("TAVILY_API_KEY"):
        return []
    try:
        results = tavily_search(f"is {claim.value} deprecated OR end of life OR unmaintained")
    except Exception as exc:
        return [Evidence("web", f"web check unavailable: {type(exc).__name__}", None)]
    val = claim.value.lower()
    for r in results:
        text = f"{r.get('title', '')} {r.get('content', '')}"
        # require the signal to appear close to a mention of the technology itself
        for m in SIGNAL.finditer(text):
            window = text[max(0, m.start() - 120): m.end() + 120].lower()
            if val in window:
                return [Evidence("web", f"possible '{m.group(0).lower()}' signal for {claim.value}: {r.get('title', '')[:80]}", False, r.get("url"))]
    return [Evidence("web", f"no deprecation signals found for {claim.value} in {len(results)} results", None)]
