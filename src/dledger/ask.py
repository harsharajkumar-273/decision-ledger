"""'Why did we decide X, and is it still true?'

Retrieval is hybrid: lexical always, plus NVIDIA embeddings through Token
Factory when DLEDGER_MODEL_EMBED is set. The graph then adds what plain RAG
cannot: supersession, open conflicts, verification status, and dependents."""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from typing import Callable, Optional

from .graph import DecisionGraph
from .llm import Tier, chat, _client
from .schema import Claim, Status

STOP = set("a an the of to for in on is are was we why did do how what which and or it our use using decide decided".split())
EmbedFn = Callable[[list[str]], list[list[float]]]
_embedder: Optional[EmbedFn] = None


def set_embedder(fn: Optional[EmbedFn]) -> None:
    global _embedder
    _embedder = fn


def _canon_map() -> dict[str, str]:
    from .verify import ALIASES

    m: dict[str, str] = {}
    for key, toks in ALIASES.items():
        for t in toks:
            m.setdefault(t, key if key != "postgres" else "postgresql")
        m.setdefault(key, key if key != "postgres" else "postgresql")
    return m


_CANON = _canon_map()


def _toks(s: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9]+", s.lower()):
        if t in STOP:
            continue
        out.append(_CANON.get(t, t))
    return out


def visible(c: Claim, groups: Optional[set[str]]) -> bool:
    """groups=None means an admin/CLI view with no filtering."""
    return groups is None or c.acl is None or bool(set(c.acl) & groups)


def _doc(c: Claim) -> str:
    return f"{c.text} {c.subject} {c.value} {c.reason or ''}"


def _canon_in(c: Claim, qt: Counter) -> bool:
    return any(_CANON.get(x.lower(), x.lower()) in qt for x in (c.subject, c.value))


def _lexical(graph: DecisionGraph, q: str, groups: Optional[set[str]] = None) -> dict[str, float]:
    qt = Counter(_toks(q))
    scores: dict[str, float] = {}
    for c in graph.claims():
        if not visible(c, groups):
            continue
        dt = Counter(_toks(_doc(c)))
        overlap = 0.0
        for t in qt:
            if dt[t]:
                overlap += min(qt[t], dt[t])
            elif len(t) >= 5 and any(d.startswith(t[:5]) for d in dt):
                overlap += 0.6          # cheap stemming: "migrating" ~ "migrate"
        if _canon_in(c, qt):
            overlap += 1.0              # the question names this decision's subject/value
        if overlap:
            scores[c.id] = overlap / math.sqrt(sum(dt.values()) or 1)
    return scores


def _embed(texts: list[str]) -> list[list[float]]:
    if _embedder is not None:
        return _embedder(texts)
    model = os.getenv("DLEDGER_MODEL_EMBED")
    resp = _client().embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]


def _semantic(graph: DecisionGraph, q: str, groups: Optional[set[str]] = None) -> dict[str, float]:
    if _embedder is None and not os.getenv("DLEDGER_MODEL_EMBED"):
        return {}
    claims = [c for c in graph.claims() if visible(c, groups)]
    vecs = _embed([q] + [_doc(c) for c in claims])
    qv, dvs = vecs[0], vecs[1:]

    def cos(a, b):
        na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
        return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0

    return {c.id: max(0.0, cos(qv, v)) for c, v in zip(claims, dvs)}


def retrieve(graph: DecisionGraph, q: str, k: int = 4, groups: Optional[set[str]] = None) -> list[Claim]:
    lex, sem = _lexical(graph, q, groups), _semantic(graph, q, groups)
    if lex:
        top = max(lex.values())
        lex = {i: s / top for i, s in lex.items()}
    ids = set(lex) | set(sem)
    ranked = sorted(ids, key=lambda i: -(0.5 * lex.get(i, 0) + 0.5 * sem.get(i, 0) if sem else lex.get(i, 0)))
    return [graph.claim(i) for i in ranked[:k]]


def warnings_for(graph: DecisionGraph, claims: list[Claim], groups: Optional[set[str]] = None) -> list[str]:
    out: list[str] = []
    vis = lambda i: visible(graph.claim(i), groups)
    conflicts = graph.find_conflicts()
    for c in claims:
        if c.status in (Status.CONTRADICTED, Status.STALE):
            out.append(f"{c.id} is {c.status.value}: the evidence no longer supports '{c.text}'.")
        elif c.status == Status.NEEDS_REVIEW:
            out.append(f"{c.id} needs review: something it depends on may have changed.")
        cur = graph.current(c.id)
        if cur != c.id and vis(cur):
            out.append(f"{c.id} was superseded by {cur}: '{graph.claim(cur).text}'.")
        for a, b in conflicts:
            if c.id in (a, b) and vis(b if a == c.id else a):
                other = graph.claim(b if a == c.id else a)
                out.append(f"{c.id} conflicts with {other.id} ('{other.text}', {other.date}); no supersession is recorded.")
        dep = [d for d in graph.impact(c.id) if vis(d)]
        if dep and c.status in (Status.CONTRADICTED, Status.STALE):
            out.append(f"{len(dep)} decision(s) depend on {c.id}: {', '.join(dep)}.")
    seen: set[str] = set()
    return [w for w in out if not (w in seen or seen.add(w))]


ANSWER_SYSTEM = """You answer 'why did we decide X?' questions about a team's decisions.
Use ONLY the decisions provided. Cite decision ids like [d1]. Be concise (3 sentences max).
If a decision is contradicted, stale, superseded or in conflict, say so plainly before anything else."""


def answer(graph: DecisionGraph, q: str, use_llm: bool = True, k: int = 4, groups: Optional[set[str]] = None) -> dict:
    # Status overview questions are graph queries, not lexical searches for the
    # words "review" or "decisions" in the original messages.
    overview = re.sub(r"[^a-z ]", "", q.lower()).strip() in {
        "which decisions need review", "what needs review", "show decisions needing review",
        "list decisions that need review",
    }
    if overview:
        matches = [c for c in graph.claims() if visible(c, groups) and c.status == Status.NEEDS_REVIEW]
        hits = matches[:k]
    else:
        hits = retrieve(graph, q, k, groups)
    warns = warnings_for(graph, hits, groups)
    cites = [
        {"id": c.id, "text": c.text, "owner": c.owner, "date": c.date, "source": c.source,
         "reason": c.reason, "status": c.status.value}
        for c in hits
    ]
    if not hits:
        return {"answer": "No visible decisions currently need review. Unchecked decisions have not been verified."
                if overview else "I couldn't find a recorded decision about that.", "citations": [], "warnings": []}
    text = None
    if use_llm:
        try:
            payload = json.dumps({"question": q, "decisions": cites, "warnings": warns})
            text = chat(Tier.SUPER, ANSWER_SYSTEM, payload).strip()
        except Exception:
            text = None
    if not text:
        if overview:
            text = f"{len(matches)} visible decision(s) need review:\n" + "\n".join(f"[{c.id}] {c.text}" for c in hits)
            if len(matches) > len(hits):
                text += f"\nShowing the first {len(hits)}; use the status filter to see the rest."
        else:
            top = hits[0]
            text = f"[{top.id}] {top.text}" + (f", because {top.reason[0].lower() + top.reason[1:]}" if top.reason else "") + f" ({top.owner}, {top.date})."
    return {"answer": text, "citations": cites, "warnings": warns}
