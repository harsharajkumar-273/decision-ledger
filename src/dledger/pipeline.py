"""check(): candidates -> verifiers -> judge -> write verdicts back into the graph."""
from __future__ import annotations

from .graph import DecisionGraph
from .judge import judge
from .schema import Status, Verdict
from .sandbox import run_verifier


def candidates(graph: DecisionGraph) -> list[str]:
    ids: list[str] = []
    for a, b in graph.find_conflicts():
        ids += [a, b]
    ids += [cid for cid, n in graph.load_bearing(top=10) if n > 0]
    seen: set[str] = set()
    return [i for i in ids if graph.claim(i).status != Status.SUPERSEDED and not (i in seen or seen.add(i))]


def check(
    graph: DecisionGraph,
    repo: str | None,
    use_llm: bool = True,
    ids: list[str] | None = None,
    web: bool = False,
) -> list[Verdict]:
    """Verify `ids` (default: graph-selected candidates) and propagate failures."""
    verdicts: list[Verdict] = []
    for cid in (candidates(graph) if ids is None else ids):
        if graph.claim(cid).status == Status.SUPERSEDED:
            continue
        v = judge(graph, cid, run_verifier(graph.claim(cid), repo, web=web), use_llm=use_llm)
        retired = {dep for dep in graph.dependencies(cid) if graph.claim(dep).status == Status.SUPERSEDED}
        last_supersession = max((i for i, event in enumerate(graph.audit)
                                if event['decision_id'] in retired and event['action'] == 'supersede'), default=-1)
        confirmed = any(event['decision_id'] == cid and event['action'] == 'review' and i > last_supersession
                        for i, event in enumerate(graph.audit))
        if retired and not confirmed and v.status == Status.VALID:
            v.status = Status.NEEDS_REVIEW
            v.rationale = 'A prerequisite was superseded; its dependent reasoning needs an explicit human review.'
        graph.claim(cid).status = v.status
        verdicts.append(v)
    # propagate: anything depending on a failed decision needs a human look
    for claim in graph.claims():
        if claim.status in (Status.CONTRADICTED, Status.STALE):
            for dep in graph.impact(claim.id):
                if graph.claim(dep).status in (Status.ACTIVE, Status.VALID):
                    graph.claim(dep).status = Status.NEEDS_REVIEW
    for v in verdicts:
        if v.status == Status.VALID and graph.claim(v.claim_id).status == Status.NEEDS_REVIEW:
            v.status = Status.NEEDS_REVIEW
            v.rationale = 'Direct evidence supports this decision, but a prerequisite no longer holds; review the dependent reasoning.'
    return verdicts
