"""Notion / Google Drive exports as markdown or text files. Each file becomes
one message (optionally with 'date:' and 'author:' front-matter lines)."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path


def load(root: str | Path, max_chars: int = 4000) -> list[dict]:
    root = Path(root)
    out = []
    for f in sorted(root.rglob("*")):
        if f.suffix.lower() not in {".md", ".txt"} or not f.is_file():
            continue
        raw = f.read_text(errors="ignore")
        meta = dict(re.findall(r"^(date|author):\s*(.+)$", raw[:500], flags=re.M | re.I))
        body = re.sub(r"^---.*?---\s*", "", raw, count=1, flags=re.S).strip()
        if len(body) < 40:
            continue
        rel = f.relative_to(root).as_posix()
        out.append(
            {
                "id": f"doc:{rel}",
                "author": meta.get("author"),
                "date": meta.get("date") or dt.date.fromtimestamp(f.stat().st_mtime).isoformat(),
                "source": f"doc:{rel}",
                "text": body[:max_chars],
            }
        )
    return out
