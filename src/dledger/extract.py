"""Ingestion: messages -> claims (Nano) -> edges (Super)."""
from __future__ import annotations

import json
from pathlib import Path

from .graph import DecisionGraph
from . import domains
from .llm import Tier, chat_json
from .schema import Claim, EdgeType

LINK_SYSTEM = """You link decisions into a dependency graph.
Given decisions (id, text), return a JSON list of edges:
{"src": id, "dst": id, "type": "depends_on"|"supersedes"|"contradicts", "confidence": 0..1}
- depends_on: src is only valid if dst holds.
- supersedes: src explicitly replaces dst.
- contradicts: both cannot hold. Only when clearly incompatible.
Use only the ids given. Return [] if none."""


def load_messages(path: str | Path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def extract_claims(messages: list[dict], batch: int = 10, domain: str = "engineering", tier: Tier = Tier.NANO) -> list[Claim]:
    dom = domains.get(domain)
    claims: list[Claim] = []
    by_id = {m["id"]: m for m in messages}
    for i in range(0, len(messages), batch):
        chunk = messages[i:i + batch]
        payload = json.dumps(
            [{"id": m["id"], "author": m.get("author"), "date": m.get("date"), "text": m["text"]} for m in chunk]
        )
        items = chat_json(tier, dom.extract_system, payload)
        for it in items:
            if it.get('message_id') not in by_id:
                raise ValueError('model returned a decision with no source message')
            if any(it.get(field) is not None and not isinstance(it[field], str) for field in ('scope', 'condition')):
                raise ValueError('model returned an invalid scope or condition')
            m = by_id.get(it.get("message_id"), {})
            claims.append(
                Claim(
                    id=f"c{len(claims) + 1}",
                    text=it["text"],
                    subject=str(it["subject"]).lower(),
                    value=str(it["value"]).lower(),
                    kind=it.get("kind", dom.kind),
                    owner=m.get("author"),
                    date=m.get("date"),
                    source=m.get("source") or it.get("message_id"),
                    reason=it.get("reason"),
                    confidence=float(it.get("confidence", 0.5)),
                    acl=m.get("acl"),
                    scope=it.get("scope"),
                    condition=it.get("condition"),
                )
            )
    return claims


def link_claims(claims: list[Claim]) -> list[dict]:
    if len(claims) < 2:
        return []
    payload = json.dumps([{"id": c.id, "text": c.text, "date": c.date, "scope": c.scope,
                           "condition": c.condition} for c in claims])
    return chat_json(Tier.SUPER, LINK_SYSTEM, payload)


def build_graph(messages: list[dict], domain: str = "engineering") -> DecisionGraph:
    dg = DecisionGraph()
    claims = extract_claims(messages, domain=domain)
    for c in claims:
        dg.add_claim(c)
    ids = {c.id for c in claims}
    for e in link_claims(claims):
        if e.get("src") in ids and e.get("dst") in ids and e["src"] != e["dst"]:
            try:
                dg.add_edge(e["src"], e["dst"], EdgeType(e["type"]), float(e.get("confidence", 0.5)))
            except ValueError:
                continue
    return dg
