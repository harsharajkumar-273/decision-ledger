"""Unresolved work remains visible after its prerequisite has been retired."""
from __future__ import annotations

from .schema import Status


def queue(graph, known_verdicts=None):
    known = {v['id']: v for v in known_verdicts or []}
    items = []
    for claim in graph.claims():
        if claim.status not in (Status.CONTRADICTED, Status.STALE, Status.NEEDS_REVIEW):
            continue
        prerequisites = [graph.claim(cid) for cid in graph.dependencies(claim.id)
                         if graph.claim(cid).status in (Status.CONTRADICTED, Status.STALE, Status.SUPERSEDED)]
        verdict = known.get(claim.id)
        if prerequisites:
            why = 'Review reasoning that depends on changed or retired decisions.'
        elif verdict and verdict['status'] == claim.status.value:
            why = verdict['rationale']
        else:
            why = 'Evidence is incomplete or conflicting; confirm the applicable decision.'
        items.append({'id': claim.id, 'text': claim.text, 'owner': claim.owner, 'status': claim.status.value,
                      'reason': why, 'prerequisites': [{'id': c.id, 'text': c.text, 'status': c.status.value}
                                                       for c in prerequisites],
                      'impact_count': len(graph.impact(claim.id)),
                      'verified_at': (verdict or {}).get('verified_at')})
    return sorted(items, key=lambda item: (item['status'] == 'needs_review', -item['impact_count'], item['id']))
