"""Jira export: JSON ({"issues": [...]}, as from the REST search API) or CSV."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def _adf_text(node) -> str:
    """Flatten Atlassian Document Format (or plain strings) to text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        return " ".join(_adf_text(c) for c in node.get("content", []))
    if isinstance(node, list):
        return " ".join(_adf_text(c) for c in node)
    return ""


def load(path: str | Path, base_url: str = "jira") -> list[dict]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return _from_csv(path, base_url)
    data = json.loads(path.read_text())
    out = []
    for it in data.get("issues", []):
        f = it.get("fields", {})
        comments = " ".join(_adf_text(c.get("body")) for c in (f.get("comment", {}) or {}).get("comments", []))
        text = " ".join(x for x in (f.get("summary", ""), _adf_text(f.get("description")), comments) if x).strip()
        out.append(
            {
                "id": f"jira:{it['key']}",
                "author": (f.get("reporter") or {}).get("displayName"),
                "date": (f.get("created") or "")[:10],
                "source": f"jira:{it['key']}",
                "text": text,
            }
        )
    return out


def _from_csv(path: Path, base_url: str) -> list[dict]:
    out = []
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            key = r.get("Issue key") or r.get("Key") or ""
            text = f"{r.get('Summary', '')} {r.get('Description', '')}".strip()
            out.append(
                {
                    "id": f"jira:{key}",
                    "author": r.get("Reporter") or r.get("Creator"),
                    "date": (r.get("Created") or "")[:10],
                    "source": f"jira:{key}",
                    "text": text,
                }
            )
    return out
