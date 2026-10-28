import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dledger.graph import DecisionGraph
from dledger.server import create_app
from dledger.workflow import resolve

ROOT = Path(__file__).parent.parent / 'data/sample'


def local_client(tmp_path, monkeypatch):
    monkeypatch.setenv('DLEDGER_USE_LLM', '0')
    monkeypatch.setenv('DLEDGER_PERSIST', '1')
    path = tmp_path / 'ledger.json'
    DecisionGraph.load(ROOT / 'graph.json').save(path)
    return TestClient(create_app(str(path), str(ROOT / 'repo'))), path


def test_history_restores_latest_evidence_and_audit_after_restart(tmp_path, monkeypatch):
    c, path = local_client(tmp_path, monkeypatch)
    checked = c.post('/api/check', json={'full': True}).json()
    resolved = c.post('/api/decisions/d1/resolve', json={'action': 'supersede', 'target_id': 'd5',
                     'reviewer': 'Reviewer', 'note': 'The MongoDB decision now replaces the earlier database choice.'}).json()
    reopened = TestClient(create_app(str(path), str(ROOT / 'repo')))
    assert reopened.get('/api/report').json() == resolved
    history = reopened.get('/api/history').json()
    assert history['durable'] is True
    assert [e['event_type'] for e in history['events']] == ['resolution', 'check']
    assert history['events'][0]['mode'] == 'human' and history['events'][0]['checked'] == 0
    original = reopened.get('/api/history/' + checked['event_id']).json()
    assert next(n['status'] for n in original['graph']['nodes'] if n['id'] == 'd1') == 'contradicted'
    assert next(n['status'] for n in resolved['graph']['nodes'] if n['id'] == 'd1') == 'superseded'
    assert original['drafts']  # the historical follow-up draft is preserved


def test_review_queue_keeps_dependent_owners_after_supersession(tmp_path, monkeypatch):
    c, _ = local_client(tmp_path, monkeypatch)
    c.post('/api/check', json={'full': True})
    c.post('/api/decisions/d1/resolve', json={'action': 'supersede', 'target_id': 'd5',
           'reviewer': 'Reviewer', 'note': 'New database configuration is reviewed and approved.'})
    items = c.get('/api/reviews').json()['items']
    assert {item['id'] for item in items} == {'d3', 'd4'}
    assert {p['status'] for item in items for p in item['prerequisites']} == {'superseded'}
    assert [item['id'] for item in c.get('/api/reviews', params={'owner': 'li'}).json()['items']] == ['d4']
    assert c.get('/api/reviews', params={'owner': 'unknown'}).json()['items'] == []


def test_selective_check_keeps_previous_evidence(tmp_path, monkeypatch):
    c, _ = local_client(tmp_path, monkeypatch)
    full = c.post('/api/check', json={'full': True}).json()
    selective = c.post('/api/check', json={}).json()
    assert {v['id'] for v in selective['verdicts']} == {'d1', 'd5'}
    assert len(selective['known_verdicts']) == 6
    old_cache = next(v for v in full['known_verdicts'] if v['id'] == 'd2')
    assert next(v for v in selective['known_verdicts'] if v['id'] == 'd2') == old_cache
    assert all(t['before'] != t['after'] for t in selective['transitions'])


def test_reset_keeps_history_but_clears_current_report(tmp_path, monkeypatch):
    c, _ = local_client(tmp_path, monkeypatch)
    checked = c.post('/api/check', json={}).json()
    c.post('/api/reset')
    assert c.get('/api/report').json()['checked_at'] is None
    events = c.get('/api/history').json()['events']
    assert events[0]['event_type'] == 'reset'
    assert c.get('/api/history/' + checked['event_id']).json()['checked_at'] is not None
    assert c.get('/api/history/missing').status_code == 404
    assert c.get('/api/history', params={'limit': 0}).status_code == 400


def test_failed_persistence_does_not_change_current_graph(tmp_path, monkeypatch):
    c, _ = local_client(tmp_path, monkeypatch)
    before = c.get('/api/graph').json()
    def fail(*args):
        raise OSError('disk unavailable')
    monkeypatch.setattr(DecisionGraph, 'save', fail)
    with pytest.raises(OSError):
        c.post('/api/check', json={})
    assert c.get('/api/graph').json() == before
    assert c.get('/api/history').json()['events'] == []


def test_atomic_graph_write_keeps_old_file_if_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / 'ledger.json'
    g = DecisionGraph.load(ROOT / 'graph.json')
    g.save(path)
    before = path.read_bytes()
    monkeypatch.setattr(Path, 'replace', lambda *args: (_ for _ in ()).throw(OSError('replacement failed')))
    with pytest.raises(OSError):
        g.save(path)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('.dledger-*.tmp'))


def test_supersession_cannot_cross_environment_scope():
    g = DecisionGraph.load(ROOT / 'graph.json')
    g.claim('d1').scope = 'production'
    g.claim('d5').scope = 'staging'
    with pytest.raises(ValueError):
        resolve(g, 'd1', 'supersede', 'Reviewer', 'This replacement belongs to a different environment.', 'd5')
    assert g.audit == []
