"""Plain-language coverage and impact summaries derived from recorded evidence."""
from .schema import Status


def summary(graph, known):
    current = [c for c in graph.claims() if c.status != Status.SUPERSEDED]
    pending = [c for c in current if c.id not in known]
    impacts = []
    for claim in graph.claims():
        if claim.status not in (Status.CONTRADICTED, Status.STALE, Status.SUPERSEDED):
            continue
        affected = [graph.claim(cid) for cid in graph.impact(claim.id)
                    if graph.claim(cid).status == Status.NEEDS_REVIEW]
        if claim.status == Status.SUPERSEDED and not affected:
            continue
        evidence = (known.get(claim.id) or {}).get('evidence', [])
        impacts.append({'id': claim.id, 'text': claim.text, 'status': claim.status.value,
                        'affected': [{'id': c.id, 'text': c.text, 'owner': c.owner} for c in affected],
                        'owners': sorted({c.owner for c in affected if c.owner}),
                        'evidence': evidence})
    return {'coverage': {'total': len(current), 'assessed': len(current) - len(pending),
                         'pending': [{'id': c.id, 'text': c.text, 'owner': c.owner} for c in pending]},
            'impacts': sorted(impacts, key=lambda item: -len(item['affected']))}
