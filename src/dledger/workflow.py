"""Human decisions with audit trails; no external publication."""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from .graph import DecisionGraph
from .schema import Claim, EdgeType, Evidence, Status, Verdict


def resolve(graph: DecisionGraph, cid: str, action: str, reviewer: str, note: str, target: str | None = None) -> dict:
    if cid not in graph.g:
        raise KeyError('unknown decision')
    if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(note, str) or len(note.strip()) < 10:
        raise ValueError('provide a reviewer and an explanation of at least 10 characters')
    if len(reviewer) > 200 or len(note) > 4000:
        raise ValueError('reviewer or explanation is too long')
    claim = graph.claim(cid)
    prior = claim.status.value
    if action == 'supersede':
        if claim.status == Status.SUPERSEDED:
            raise ValueError('this decision is already superseded')
        if target not in graph.g or target == cid:
            raise ValueError('choose a different existing replacement decision')
        replacement = graph.claim(target)
        if (replacement.subject != claim.subject or (replacement.scope or '') != (claim.scope or '')
                or replacement.status == Status.SUPERSEDED):
            raise ValueError('replacement must be a current decision about the same subject and environment scope')
        if cid in graph.supersession_chain(target):
            raise ValueError('replacement would introduce a supersession cycle')
        graph.add_edge(target, cid, EdgeType.SUPERSEDES)
        claim.status = Status.SUPERSEDED
        # Supersession closes the old decision, not the downstream work.
        for dep in graph.impact(cid):
            if graph.claim(dep).status in (Status.ACTIVE, Status.VALID):
                graph.claim(dep).status = Status.NEEDS_REVIEW
    elif action == 'review':
        if claim.status != Status.NEEDS_REVIEW:
            raise ValueError('only decisions needing review can be confirmed by a reviewer')
        claim.status = Status.VALID
    else:
        raise ValueError('action must be supersede or review')
    event = {'id': f'r{len(graph.audit) + 1}', 'decision_id': cid, 'action': action, 'reviewer': reviewer.strip(),
             'note': note.strip(), 'target_id': target, 'previous_status': prior, 'status': claim.status.value,
             'at': datetime.now(timezone.utc).isoformat()}
    graph.audit.append(event)
    return event


def review_verdict(graph: DecisionGraph, event: dict) -> Verdict:
    return Verdict(event['decision_id'], Status(event['status']), f"Human review by {event['reviewer']}: {event['note']}",
                   [Evidence('review', event['note'], True if event['action'] == 'review' else None,
                             f"review:{event['id']}")], graph.impact(event['decision_id']))


def create_decision(graph: DecisionGraph, body: dict) -> dict:
    """Record an attributed, unchecked decision and its existing prerequisites."""
    if not isinstance(body, dict):
        raise ValueError('decision must be an object')
    allowed = {'text', 'subject', 'value', 'owner', 'reason', 'kind', 'scope', 'condition', 'source', 'date', 'dependencies'}
    if set(body) - allowed:
        raise ValueError('unknown decision fields')
    fields = {}
    for key in allowed - {'dependencies'}:
        value = body.get(key, '')
        if not isinstance(value, str) or len(value) > (4000 if key in ('text', 'reason', 'condition') else 500):
            raise ValueError(f'{key} must be text within the allowed length')
        fields[key] = value.strip()
    for key in ('text', 'subject', 'value', 'owner', 'reason'):
        if not fields[key]:
            raise ValueError(f'{key} is required')
    fields['kind'] = fields['kind'] or 'tech_choice'
    if fields['kind'] not in ('tech_choice', 'commitment', 'policy'):
        raise ValueError('choose a technology decision, commitment or policy')
    if fields['date']:
        try:
            date.fromisoformat(fields['date'])
        except ValueError:
            raise ValueError('date must use YYYY-MM-DD')
    else:
        fields['date'] = datetime.now(timezone.utc).date().isoformat()
    dependencies = body.get('dependencies', [])
    if not isinstance(dependencies, list) or len(dependencies) > 100 or any(not isinstance(cid, str) for cid in dependencies):
        raise ValueError('dependencies must be a list of decision IDs (maximum 100)')
    dependencies = list(dict.fromkeys(dependencies))
    for cid in dependencies:
        if cid not in graph.g or graph.claim(cid).status == Status.SUPERSEDED:
            raise ValueError('choose existing prerequisites that have not been superseded')
    cid = 'd' + uuid4().hex
    claim = Claim(id=cid, **{key: value or None for key, value in fields.items()})
    if any(graph.claim(dep).status in (Status.STALE, Status.CONTRADICTED, Status.NEEDS_REVIEW) for dep in dependencies):
        claim.status = Status.NEEDS_REVIEW
    graph.add_claim(claim)
    for dep in dependencies:
        graph.add_edge(cid, dep, EdgeType.DEPENDS_ON)
    event = {'id': f'r{len(graph.audit) + 1}', 'decision_id': cid, 'action': 'create',
             'reviewer': claim.owner, 'note': claim.reason, 'previous_status': None,
             'status': claim.status.value, 'at': datetime.now(timezone.utc).isoformat()}
    graph.audit.append(event)
    return event
