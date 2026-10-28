"""Slack workspace export (the folder from Admin > Export data).

  users.json, channels.json, <channel>/<YYYY-MM-DD>.json

Private channels get an ACL so answers never leak them to people outside."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

SKIP_SUBTYPES = {"channel_join", "channel_leave", "bot_message", "channel_topic", "channel_purpose"}


def load(root: str | Path, min_chars: int = 25) -> list[dict]:
    root = Path(root)
    users = {}
    if (root / "users.json").exists():
        users = {u["id"]: u.get("real_name") or u.get("name") for u in json.loads((root / "users.json").read_text())}
    private: set[str] = set()
    if (root / "channels.json").exists():
        for ch in json.loads((root / "channels.json").read_text()):
            if ch.get("is_private"):
                private.add(ch["name"])
    out: list[dict] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        for f in sorted(d.glob("*.json")):
            for m in json.loads(f.read_text()):
                text = _clean(m.get("text", ""), users)
                if m.get("subtype") in SKIP_SUBTYPES or len(text) < min_chars:
                    continue
                ts = m.get("ts", "0")
                out.append(
                    {
                        "id": f"slack:{d.name}/{ts}",
                        "author": users.get(m.get("user"), m.get("user_name") or m.get("user")),
                        "date": dt.datetime.fromtimestamp(float(ts), dt.timezone.utc).date().isoformat(),
                        "source": f"slack:#{d.name}/{ts}",
                        "text": text,
                        "acl": [f"channel:{d.name}"] if d.name in private else None,
                    }
                )
    return out


def _clean(text: str, users: dict) -> str:
    text = re.sub(r"<@(\w+)>", lambda m: "@" + str(users.get(m.group(1), m.group(1))), text)
    text = re.sub(r"<(https?://[^|>]+)\|?[^>]*>", r"\1", text)
    return text.strip()
