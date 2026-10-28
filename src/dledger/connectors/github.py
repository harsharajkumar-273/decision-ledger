"""GitHub issues and pull requests (both come from the issues endpoint) plus
their comments. Public repos work without a token; set GITHUB_TOKEN for rate limits."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable, Optional

Getter = Callable[[str], object]
_getter: Optional[Getter] = None


def set_getter(fn: Optional[Getter]) -> None:
    global _getter
    _getter = fn


def _get(url: str):
    if _getter is not None:
        return _getter(url)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "decision-ledger"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.loads(r.read())


def load(repo: str, max_items: int = 200, with_comments: bool = False, min_chars: int = 40) -> list[dict]:
    """repo is 'owner/name'."""
    out: list[dict] = []
    page = 1
    while len(out) < max_items:
        items = _get(f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100&page={page}")
        if not items:
            break
        for it in items:
            body = (it.get("body") or "").strip()
            text = f"{it['title']}. {body}"[:3000]
            kind = "pr" if "pull_request" in it else "issue"
            if len(text) >= min_chars:
                out.append(
                    {
                        "id": f"github:{repo}#{it['number']}",
                        "author": (it.get("user") or {}).get("login"),
                        "date": (it.get("created_at") or "")[:10],
                        "source": it.get("html_url") or f"github:{repo}#{it['number']} ({kind})",
                        "text": text,
                    }
                )
            if with_comments and it.get("comments"):
                for c in _get(it["comments_url"]):
                    ct = (c.get("body") or "").strip()
                    if len(ct) >= min_chars:
                        out.append(
                            {
                                "id": f"github:{repo}#{it['number']}/c{c['id']}",
                                "author": (c.get("user") or {}).get("login"),
                                "date": (c.get("created_at") or "")[:10],
                                "source": c.get("html_url"),
                                "text": ct[:3000],
                            }
                        )
        page += 1
        if len(items) < 100:
            break
    return out[:max_items]
