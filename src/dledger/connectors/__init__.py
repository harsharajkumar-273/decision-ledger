"""Connectors turn source systems into the common message shape:
{"id", "author", "date", "source", "text", "acl"?}

File-based connectors (Slack export, Jira export, Notion/Drive markdown) work
offline. The GitHub connector reads the REST API (public repos need no token)."""
from __future__ import annotations

import json
from pathlib import Path


def write_jsonl(messages: list[dict], out: str | Path) -> int:
    Path(out).write_text("\n".join(json.dumps(m) for m in messages) + "\n")
    return len(messages)
