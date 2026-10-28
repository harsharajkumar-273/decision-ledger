"""Local decision workspace, repository watcher, audited resolutions and drafts."""
from __future__ import annotations

import asyncio
import base64
import binascii
import copy
import hashlib
import hmac
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import actions, ask as askmod, llm, watch, workflow, importing, workspace, readiness
from .graph import DecisionGraph
from .pipeline import check
from .schema import Status
from .schema import Evidence, Verdict
from .history import ReportStore
from .reviews import queue as review_queue

UI = Path(__file__).parent / 'ui' / 'index.html'


def _use_llm() -> bool:
    mode = os.getenv('DLEDGER_USE_LLM', 'auto')
    return bool(os.getenv('NEBIUS_API_KEY')) if mode == 'auto' else mode == '1'


def graph_payload(g: DecisionGraph) -> dict:
    return {'nodes': [c.to_dict() for c in g.claims()],
            'edges': [{'src': u, 'dst': v, 'type': d['etype']} for u, v, d in g.g.edges(data=True)],
            'conflicts': [list(p) for p in g.find_conflicts()], 'audit': copy.deepcopy(g.audit)}


def serialize(v):
    return {'id': v.claim_id, 'status': v.status.value, 'rationale': v.rationale, 'impacted': v.impacted,
            'evidence': [e.__dict__ for e in v.evidence]}


def create_app(graph_path: str | None = None, repo: str | None = None) -> FastAPI:
    graph_path = graph_path or os.getenv('DLEDGER_GRAPH', 'graph.json')
    repo = repo or os.getenv('DLEDGER_REPO')
    lock = threading.RLock()
    store_path = os.getenv('DLEDGER_STATE', str(graph_path) + '.history.sqlite3') if os.getenv('DLEDGER_PERSIST') == '1' else ':memory:'
    history = ReportStore(store_path)
    state = {'g': DecisionGraph.load(graph_path), 'last': [], 'report': None,
             'known': {},
             'watch': {'enabled': False, 'interval_seconds': 5, 'last_changes': [], 'error': None,
                       'baseline': None, 'commit': None}}

    restored = history.latest()
    if restored and restored['graph'] == graph_payload(state['g']) and restored['event_type'] != 'reset':
        state['report'] = restored
        state['known'] = {v['id']: v for v in restored.get('known_verdicts', restored['verdicts'])}
        state['last'] = [Verdict(v['id'], Status(v['status']), v['rationale'],
                                [Evidence(**e) for e in v['evidence']], v['impacted']) for v in state['known'].values()]

    def persist(graph=None):
        if os.getenv('DLEDGER_PERSIST') == '1':
            (graph or state['g']).save(graph_path)

    def perform_check(body, trigger='manual', changed=None, commit=None):
        with lock:
            if not repo:
                raise HTTPException(400, 'server has no DLEDGER_REPO to verify against')
            before_graph = graph_payload(state['g'])
            g = copy.deepcopy(state['g'])
            requested = body.get('use_llm', _use_llm())
            before = {tier: dict(values) for tier, values in llm.USAGE.items()}
            started = time.monotonic()
            selected_ids = (list(dict.fromkeys(body['ids'])) if 'ids' in body else
                            [c.id for c in g.claims() if c.status != Status.SUPERSEDED and c.id not in state['known']]
                            if body.get('unchecked') else [c.id for c in g.claims()] if body.get('full') else None)
            verdicts = check(g, repo, use_llm=requested, web=bool(body.get('web')), ids=selected_ids)
            delta = {tier: {key: value - before[tier][key] for key, value in values.items()}
                     for tier, values in llm.USAGE.items()}
            calls = sum(v['calls'] for v in delta.values())
            fallbacks = sum('LLM judge unavailable:' in v.rationale for v in verdicts)
            checked_at = datetime.now(timezone.utc).isoformat()
            known = {**state['known'], **{v.claim_id: {**serialize(v), 'verified_at': checked_at} for v in verdicts}}
            all_verdicts = {v.claim_id: v for v in state['last']}
            all_verdicts.update({v.claim_id: v for v in verdicts})
            result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'trigger': trigger,
                      'changes': changed or [], 'commit': commit,
                      'selection': {'mode': 'unchecked' if body.get('unchecked') else 'full' if body.get('full') else 'selected' if 'ids' in body else 'graph', 'ids': [v.claim_id for v in verdicts]},
                      'execution': {'mode': 'models' if calls and not fallbacks else 'partial_fallback' if calls
                                    else 'fallback' if requested and verdicts else 'rules',
                                    'model_calls': calls, 'fallbacks': fallbacks,
                                    'models': {tier: os.getenv('DLEDGER_MODEL_' + tier.upper())
                                               for tier, usage in delta.items() if usage['calls']},
                                    'seconds': round(time.monotonic() - started, 3), 'usage': delta},
                      'verdicts': [serialize(v) for v in verdicts], 'graph': graph_payload(g),
                      'known_verdicts': list(known.values()), 'review_queue': review_queue(g, list(known.values())),
                      'drafts': actions.issue_drafts(g, list(all_verdicts.values()))}
            persist(g)
            result = history.record(result, before=before_graph)
            state['g'], state['known'], state['last'] = g, known, list(all_verdicts.values())
            state['report'] = result
            return copy.deepcopy(result)

    def poll_changes():
        with lock:
            w = state['watch']
            if not w['enabled'] or not repo:
                return
            try:
                current = watch.snapshot(repo, (graph_path, store_path))
                changed = watch.changes(w['baseline'], current)
                commit_changed = current['commit'] != w['baseline']['commit']
                if changed or commit_changed:
                    # Sweep all current decisions: Git signals also find silent drift.
                    perform_check({'full': True}, 'repo_change', changed, current['commit'])
                    w['baseline'] = current
                    w['commit'] = current['commit']
                    w['last_changes'] = changed
                w['error'] = None
            except Exception as exc:
                w['error'] = f'Watch paused on error: {type(exc).__name__}'
                w['enabled'] = False

    @asynccontextmanager
    async def lifespan(app):
        async def monitor():
            while True:
                await asyncio.sleep(5)
                await asyncio.to_thread(poll_changes)
        task = asyncio.create_task(monitor())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title='Decision Ledger', lifespan=lifespan)
    demo_user, demo_password = os.getenv('DLEDGER_DEMO_USER'), os.getenv('DLEDGER_DEMO_PASSWORD')
    if bool(demo_user) != bool(demo_password):
        raise ValueError('set both DLEDGER_DEMO_USER and DLEDGER_DEMO_PASSWORD')

    @app.middleware('http')
    async def demo_access(request: Request, call_next):
        if demo_user and request.url.path != '/healthz':
            allowed = False
            header = request.headers.get('authorization', '')
            if header.startswith('Basic ') and len(header) <= 4096:
                try:
                    user, password = base64.b64decode(header[6:], validate=True).decode('utf-8').split(':', 1)
                    allowed = (hmac.compare_digest(user.encode(), demo_user.encode()) and
                               hmac.compare_digest(password.encode(), demo_password.encode()))
                except (ValueError, UnicodeError, binascii.Error):
                    pass
            if not allowed:
                return JSONResponse({'detail': 'Demo sign-in required'}, status_code=401,
                                    headers={'WWW-Authenticate': 'Basic realm="Decision Ledger demo", charset="UTF-8"',
                                             'Cache-Control': 'no-store'})
        return await call_next(request)

    app.state.poll_changes = poll_changes  # deterministic integration testing

    @app.get('/', response_class=HTMLResponse)
    def index():
        return UI.read_text()

    @app.get('/healthz')
    def health():
        with lock:
            return {'ok': True, 'claims': len(state['g'].claims())}

    @app.get('/api/graph')
    def graph():
        with lock:
            return graph_payload(state['g'])

    @app.get('/api/report')
    def report():
        with lock:
            return copy.deepcopy(state['report']) if state['report'] else {
                'graph': graph_payload(state['g']), 'verdicts': [], 'execution': None, 'checked_at': None, 'drafts': [],
                'known_verdicts': [], 'review_queue': review_queue(state['g'])}

    @app.get('/api/workspace')
    def workspace_status():
        with lock:
            return {**workspace.summary(state['g'], state['known']),
                    'models': readiness.run(False)}

    @app.get('/api/history')
    def timeline(limit: int = 30):
        if not 1 <= limit <= 100:
            raise HTTPException(400, 'history limit must be between 1 and 100')
        with lock:
            return {'events': history.summaries(limit), 'durable': store_path != ':memory:'}

    @app.get('/api/history/{event_id}')
    def historical_report(event_id: str):
        with lock:
            result = history.get(event_id)
            if result is None:
                raise HTTPException(404, 'unknown history event')
            return result

    @app.get('/api/reviews')
    def reviews(owner: str | None = None):
        with lock:
            items = review_queue(state['g'], list(state['known'].values()))
            if owner is not None:
                items = [item for item in items if (item['owner'] or '') == owner]
            return {'items': items}

    @app.post('/api/check')
    async def run_check(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict) or any(key in body and not isinstance(body[key], bool)
                                             for key in ('full', 'web', 'use_llm', 'unchecked')):
            raise HTTPException(400, 'check options must be an object with boolean full, unchecked, web and use_llm fields')
        if sum((bool(body.get('full')), bool(body.get('unchecked')), 'ids' in body)) > 1:
            raise HTTPException(400, 'choose one of ids, full or unchecked')
        if 'ids' in body:
            ids = body['ids']
            if not isinstance(ids, list) or not ids or len(ids) > 100 or any(not isinstance(cid, str) for cid in ids):
                raise HTTPException(400, 'ids must contain 1 to 100 decision IDs')
            with lock:
                if any(cid not in state['g'].g for cid in ids):
                    raise HTTPException(400, 'unknown decision ID')
            if body.get('full'):
                raise HTTPException(400, 'choose either ids or full')
        return await asyncio.to_thread(perform_check, body)

    @app.post('/api/reset')
    def reset():
        with lock:
            before_graph = graph_payload(state['g'])
            state['g'] = DecisionGraph.load(graph_path)
            state['last'], state['report'] = [], None
            state['known'] = {}
            history.record({'graph': graph_payload(state['g']), 'verdicts': [], 'checked_at': None,
                            'known_verdicts': [], 'execution': None, 'drafts': []}, 'reset', before_graph)
            return graph_payload(state['g'])

    @app.get('/api/watch')
    def watch_state():
        with lock:
            return copy.deepcopy({k: v for k, v in state['watch'].items() if k != 'baseline'})

    @app.post('/api/watch')
    async def watch_settings(request: Request):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, 'provide an enabled boolean')
        if not isinstance(body, dict) or not isinstance(body.get('enabled'), bool):
            raise HTTPException(400, 'provide an enabled boolean')
        with lock:
            w = state['watch']
            if body['enabled']:
                if not repo:
                    raise HTTPException(400, 'no repository configured')
                try:
                    w['baseline'] = watch.snapshot(repo, (graph_path, store_path))
                except (OSError, ValueError) as exc:
                    raise HTTPException(400, str(exc))
                w['commit'] = w['baseline']['commit']
            w['enabled'], w['error'] = body['enabled'], None
        return watch_state()

    @app.post('/api/import/preview')
    async def preview_import(request: Request):
        try:
            body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get('use_llm', False), bool):
                raise ValueError('provide an import object with a boolean use_llm option')
            if body.get('use_llm'):
                try:
                    return await asyncio.to_thread(importing.preview_with_models, body)
                except ValueError:
                    raise
                except Exception:
                    raise HTTPException(502, 'model extraction failed; check model access and retry, or select Markdown rules')
            return {'candidates': importing.preview(body), 'mode': 'markdown_rules'}
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))

    @app.post('/api/import')
    async def import_decisions(request: Request):
        try:
            body = await request.json()
            items = body.get('decisions') if isinstance(body, dict) else None
            if not isinstance(items, list) or not 1 <= len(items) <= 20 or any(not isinstance(item, dict) for item in items):
                raise ValueError('select between 1 and 20 decisions')
            with lock:
                before_graph = graph_payload(state['g'])
                g = copy.deepcopy(state['g'])
                existing = {importing.identity(c.to_dict()) for c in g.claims()}
                created, skipped = [], 0
                for item in items:
                    # Validate even duplicates; a malformed batch must never partially save.
                    event = workflow.create_decision(g, item)
                    key = importing.identity(g.claim(event['decision_id']).to_dict())
                    if key in existing:
                        g.g.remove_node(event['decision_id'])
                        g.audit.pop()
                        skipped += 1
                    else:
                        existing.add(key)
                        created.append(event['decision_id'])
                previous = state['report'] or {'checked_at': None, 'execution': None, 'verdicts': []}
                result = {**previous, 'graph': graph_payload(g), 'created_decision_ids': created,
                          'skipped_duplicates': skipped, 'known_verdicts': list(state['known'].values()),
                          'review_queue': review_queue(g, list(state['known'].values())),
                          'drafts': actions.issue_drafts(g, state['last'])}
                for key in ('last_resolution', 'created_decision_id', 'trigger', 'commit', 'changes'):
                    result.pop(key, None)
                if created:
                    persist(g)
                    result = history.record(result, 'decisions_imported', before_graph)
                    state['g'], state['report'] = g, result
                return copy.deepcopy(result)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))

    @app.post('/api/decisions')
    async def record_decision(request: Request):
        try:
            body = await request.json()
            with lock:
                before_graph = graph_payload(state['g'])
                g = copy.deepcopy(state['g'])
                event = workflow.create_decision(g, body)
                previous = state['report'] or {'checked_at': None, 'execution': None, 'verdicts': []}
                result = {**previous, 'graph': graph_payload(g),
                          'known_verdicts': list(state['known'].values()),
                          'review_queue': review_queue(g, list(state['known'].values())),
                          'drafts': actions.issue_drafts(g, state['last']),
                          'created_decision_id': event['decision_id']}
                result.pop('last_resolution', None)
                persist(g)
                result = history.record(result, 'decision_created', before_graph)
                state['g'], state['report'] = g, result
                return copy.deepcopy(result)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))

    @app.post('/api/decisions/{cid}/resolve')
    async def resolve_decision(cid: str, request: Request):
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError('resolution must be an object')
            with lock:
                before_graph = graph_payload(state['g'])
                g = copy.deepcopy(state['g'])
                event = workflow.resolve(g, cid, body.get('action'), body.get('reviewer'),
                                         body.get('note'), body.get('target_id'))
                v = workflow.review_verdict(g, event)
                last = [previous for previous in state['last'] if previous.claim_id != cid] + [v]
                known = {**state['known'], cid: {**serialize(v), 'verified_at': event['at']}}
                persist(g)
                previous = state['report'] or {'checked_at': None, 'execution': None}
                result = {**previous, 'graph': graph_payload(g), 'verdicts': [serialize(v) for v in last],
                          'known_verdicts': list(known.values()), 'review_queue': review_queue(g, list(known.values())),
                          'drafts': actions.issue_drafts(g, last), 'last_resolution': event}
                state['report'] = history.record(result, 'resolution', before_graph)
                state['g'], state['last'], state['known'] = g, last, known
                return copy.deepcopy(state['report'])
        except KeyError:
            raise HTTPException(404, 'unknown decision')
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))

    @app.get('/api/issues/drafts')
    def drafts():
        with lock:
            return {'drafts': actions.issue_drafts(state['g'], state['last'])}

    @app.get('/api/ask')
    def ask(q: str, groups: str | None = None):
        with lock:
            return askmod.answer(state['g'], q, use_llm=_use_llm(), groups=set(groups.split(',')) if groups else None)

    @app.get('/api/impact/{cid}')
    def impact(cid: str):
        with lock:
            g = state['g']
            if cid not in g.g:
                raise HTTPException(404, 'unknown decision')
            return {'id': cid, 'impacted': g.impact(cid), 'chain': g.supersession_chain(cid)}

    @app.get('/api/usage')
    def usage():
        with lock:
            return copy.deepcopy(llm.USAGE)

    @app.post('/slack/command')
    async def slack_command(request: Request):
        raw = await request.body()
        secret = os.getenv('SLACK_SIGNING_SECRET')
        if secret:
            ts = request.headers.get('X-Slack-Request-Timestamp', '0')
            sig = request.headers.get('X-Slack-Signature', '')
            expect = 'v0=' + hmac.new(secret.encode(), f'v0:{ts}:{raw.decode()}'.encode(), hashlib.sha256).hexdigest()
            try:
                timestamp = float(ts)
            except ValueError:
                raise HTTPException(401, 'bad signature')
            if abs(time.time() - timestamp) > 300 or not hmac.compare_digest(expect, sig):
                raise HTTPException(401, 'bad signature')
        form = {k: v[0] for k, v in parse_qs(raw.decode()).items()}
        q = form.get('text', '').strip()
        if not q:
            return {'response_type': 'ephemeral', 'text': 'Ask why we decided something, e.g. `/why postgres`.'}
        with lock:
            out = askmod.answer(state['g'], q, use_llm=_use_llm(), groups=set())
        lines = [out['answer']] + [f':warning: {w}' for w in out['warnings']]
        cites = ', '.join(f"{c['id']} ({c['source']})" for c in out['citations'][:3])
        if cites:
            lines.append(f'_Sources: {cites}_')
        return JSONResponse({'response_type': 'ephemeral', 'text': '\n'.join(lines)})

    return app


def app_factory() -> FastAPI:
    return create_app()
