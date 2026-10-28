"""Decision graph: claims as nodes, typed edges, structural queries.

The structural queries (conflicts, impact, supersession chains) are cheap and
deterministic, so the expensive Ultra model only sees the few candidates that
survive them."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import networkx as nx

from .schema import Claim, EdgeType, Status


class DecisionGraph:
    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()
        self.audit: list[dict] = []

    # ---- building -------------------------------------------------------
    def add_claim(self, claim: Claim) -> None:
        self.g.add_node(claim.id, claim=claim)

    def add_edge(self, src: str, dst: str, etype: EdgeType, confidence: float = 1.0) -> None:
        if src not in self.g or dst not in self.g:
            raise KeyError(f"unknown claim in edge {src}->{dst}")
        self.g.add_edge(src, dst, key=etype.value, etype=etype.value, confidence=confidence)

    def claim(self, cid: str) -> Claim:
        return self.g.nodes[cid]["claim"]

    def claims(self) -> list[Claim]:
        return [d["claim"] for _, d in self.g.nodes(data=True)]

    # ---- structural queries --------------------------------------------
    def _edges_of(self, etype: EdgeType) -> nx.DiGraph:
        h = nx.DiGraph()
        h.add_nodes_from(self.g.nodes)
        for u, v, d in self.g.edges(data=True):
            if d["etype"] == etype.value:
                h.add_edge(u, v)
        return h

    def impact(self, cid: str) -> list[str]:
        """Claims that (transitively) depend on `cid`. If cid goes stale, these
        are at risk. Edge A -> B with depends_on means A depends on B."""
        deps = self._edges_of(EdgeType.DEPENDS_ON)
        return sorted(nx.ancestors(deps, cid))

    def dependencies(self, cid: str) -> list[str]:
        return sorted(nx.descendants(self._edges_of(EdgeType.DEPENDS_ON), cid))

    def supersession_chain(self, cid: str) -> list[str]:
        """Follow supersedes edges from `cid` to the claim that currently holds."""
        sup = self._edges_of(EdgeType.SUPERSEDES)
        chain, cur, seen = [cid], cid, {cid}
        # who supersedes cur? predecessors in the supersedes graph
        while True:
            nxt = [p for p in sup.predecessors(cur) if p not in seen]
            if not nxt:
                return chain
            cur = nxt[0]
            seen.add(cur)
            chain.append(cur)

    def current(self, cid: str) -> str:
        return self.supersession_chain(cid)[-1]

    def find_conflicts(self) -> list[tuple[str, str]]:
        """Pairs of live claims about the same subject with different values
        and no supersedes edge between them."""
        sup = self._edges_of(EdgeType.SUPERSEDES)
        live = [c for c in self.claims() if c.status not in (Status.SUPERSEDED,)]
        by_subject: dict[tuple[str, str], list[Claim]] = {}
        for c in live:
            by_subject.setdefault((c.subject.lower(), (c.scope or '').lower()), []).append(c)
        out: list[tuple[str, str]] = []
        for group in by_subject.values():
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if a.value.lower() == b.value.lower():
                        continue
                    if sup.has_edge(a.id, b.id) or sup.has_edge(b.id, a.id):
                        continue
                    out.append((a.id, b.id))
        return out

    def load_bearing(self, top: int = 5) -> list[tuple[str, int]]:
        """Claims with the most downstream dependents: verify these first."""
        scored = [(c.id, len(self.impact(c.id))) for c in self.claims()]
        return sorted(scored, key=lambda t: -t[1])[:top]

    # ---- persistence ----------------------------------------------------
    def save(self, path: str | Path) -> None:
        data = {
            "audit": self.audit,
            "claims": [c.to_dict() for c in self.claims()],
            "edges": [
                {"src": u, "dst": v, "type": d["etype"], "confidence": d["confidence"]}
                for u, v, d in self.g.edges(data=True)
            ],
        }
        path = Path(path)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.dledger-', suffix='.tmp',
                                             delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    @classmethod
    def load(cls, path: str | Path) -> "DecisionGraph":
        data = json.loads(Path(path).read_text())
        dg = cls()
        dg.audit = data.get("audit", [])
        for c in data["claims"]:
            dg.add_claim(Claim.from_dict(c))
        for e in data["edges"]:
            dg.add_edge(e["src"], e["dst"], EdgeType(e["type"]), e.get("confidence", 1.0))
        return dg
