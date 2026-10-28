"""Preview pasted Markdown ADRs without treating document text as instructions."""
from __future__ import annotations

import re

TECHNOLOGIES = {'database': ('postgresql', 'postgres', 'mongodb', 'mysql', 'sqlite'),
                'cache': ('redis', 'memcached'), 'queue': ('celery', 'rabbitmq', 'kafka'),
                'orm': ('sqlalchemy', 'prisma')}


def preview(body: dict) -> list[dict]:
    if not isinstance(body, dict):
        raise ValueError('import must be an object')
    text, source, owner = body.get('text'), body.get('source', 'Pasted ADR'), body.get('owner', '')
    if not isinstance(text, str) or not text.strip() or len(text) > 100_000:
        raise ValueError('paste Markdown between 1 and 100,000 characters')
    if any(not isinstance(v, str) or len(v) > 400 for v in (source, owner)):
        raise ValueError('source and owner must be text of at most 400 characters')
    # Top-level headings start records. Section headings remain inside each ADR.
    starts = list(re.finditer(r'^#\s+(.+)$', text, re.M))
    blocks = [(m.start(), starts[i + 1].start() if i + 1 < len(starts) else len(text), m.group(1))
              for i, m in enumerate(starts)] or [(0, len(text), 'Imported decision')]
    if len(blocks) > 20:
        raise ValueError('preview at most 20 decisions at a time')
    result = []
    for start, end, title in blocks:
        block = text[start:end]
        def metadata(key):
            match = re.search(r'^\s*(?:[-*]\s*)?(?:\*\*)?' + key + r'(?:\*\*)?\s*:\s*(.+)$', block, re.I | re.M)
            return match.group(1).strip() if match else ''
        def section(key):
            match = re.search(r'^##\s+' + key + r'\s*\n(.*?)(?=^##?\s|\Z)', block, re.I | re.M | re.S)
            return match.group(1).strip() if match else ''
        decision = section('Decision') or metadata('Decision')
        # Do not infer a choice from rejected alternatives in Context/Consequences.
        matches = [(subject, value) for subject, values in TECHNOLOGIES.items() for value in values
                   if re.search(r'\b' + re.escape(value) + r'\b', decision, re.I)]
        matches = list(dict.fromkeys((subject, 'postgresql' if value == 'postgres' else value) for subject, value in matches))
        subject, value = matches[0] if len(matches) == 1 else ('', '')
        fields = {'text': decision, 'subject': metadata('Subject') or subject,
                  'value': metadata('Value') or value, 'owner': metadata('Owner') or owner.strip(),
                  'reason': section('Context') or metadata('Reason') or section('Rationale'),
                  'scope': metadata('Scope'), 'condition': metadata('Condition'),
                  'kind': 'tech_choice', 'source': f'{source.strip() or "Pasted ADR"}:L{text[:start].count(chr(10)) + 1}'}
        # Keep provenance intact; ask the reviewer to shorten oversized fields.
        warnings = [f'Add {key} before saving.' for key in ('text', 'subject', 'value', 'owner', 'reason') if not fields[key]]
        status = metadata('Status').lower()
        if status and status not in ('accepted', 'approved'):
            warnings.append(f'Document status is {status}; confirm it should be recorded.')
        result.append({'title': title, 'fields': fields, 'warnings': warnings})
    return result


def identity(fields):
    return tuple((fields.get(key) or '').strip().casefold() for key in ('text', 'subject', 'value', 'scope'))


def preview_with_models(body):
    """Use the configured extraction model; failures are explicit, never rules fallback."""
    import os
    from .extract import extract_claims
    from .llm import Tier, USAGE
    # Reuse all input limits, but pass the original source document to the model.
    preview(body)
    if not os.getenv('NEBIUS_API_KEY') or not os.getenv('DLEDGER_MODEL_NANO'):
        raise ValueError('configure NEBIUS_API_KEY and DLEDGER_MODEL_NANO before model extraction')
    before = dict(USAGE['nano'])
    messages = [{'id': 'adr1', 'text': body['text'], 'author': body.get('owner', '').strip(),
                 'source': (body.get('source', 'Pasted ADR').strip() or 'Pasted ADR') + ':L1'}]
    claims = extract_claims(messages, tier=Tier.NANO)
    if len(claims) > 20:
        raise ValueError('model returned more than 20 decisions; import a smaller document')
    rows = []
    for c in claims:
        fields = {key: getattr(c, key) or '' for key in ('text', 'subject', 'value', 'owner', 'reason', 'scope', 'condition', 'kind', 'source')}
        warnings = [f'Add {key} before saving.' for key in ('text', 'subject', 'value', 'owner', 'reason') if not fields[key]]
        warnings.append('Model suggestion: review the choice, attribution and reasoning against the source.')
        rows.append({'title': c.text, 'fields': fields, 'warnings': warnings})
    return {'candidates': rows, 'mode': 'models', 'model': os.getenv('DLEDGER_MODEL_NANO'),
            'usage': {key: value - before[key] for key, value in USAGE['nano'].items()}}
