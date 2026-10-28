import json

from fastapi.testclient import TestClient
from dledger.graph import DecisionGraph
from dledger.schema import Claim, EdgeType, Status
from dledger.server import create_app
from dledger.workspace import summary
from dledger import llm


def test_coverage_tracks_assessments_and_retired_impact():
    g = DecisionGraph()
    g.add_claim(Claim('old', 'Old database', 'database', 'postgresql', status=Status.SUPERSEDED))
    g.add_claim(Claim('report', 'Reporting', 'reporting', 'sql', owner='Maya', status=Status.NEEDS_REVIEW))
    g.add_claim(Claim('new', 'New database', 'database', 'mongodb'))
    g.add_edge('report', 'old', EdgeType.DEPENDS_ON)
    data = summary(g, {'new': {'evidence': []}})
    assert data['coverage']['total'] == 2 and data['coverage']['assessed'] == 1
    assert data['coverage']['pending'][0]['id'] == 'report'
    assert data['impacts'][0]['owners'] == ['Maya']
    assert data['impacts'][0]['affected'][0]['id'] == 'report'


def test_batch_unchecked_and_selection_validation(tmp_path, monkeypatch):
    monkeypatch.setenv('DLEDGER_USE_LLM', '0')
    g = DecisionGraph()
    for cid in ('a', 'b'):
        g.add_claim(Claim(cid, 'Use Redis', 'cache', 'redis'))
    g.add_claim(Claim('old', 'Old cache', 'cache', 'redis', status=Status.SUPERSEDED))
    path = tmp_path / 'graph.json'
    g.save(path)
    (tmp_path / 'requirements.txt').write_text('redis==5.0')
    client = TestClient(create_app(str(path), str(tmp_path)))
    assert client.get('/api/workspace').json()['coverage']['assessed'] == 0
    first = client.post('/api/check', json={'ids': ['a', 'a']}).json()
    assert len(first['verdicts']) == 1
    batch = client.post('/api/check', json={'unchecked': True}).json()
    assert batch['selection'] == {'mode': 'unchecked', 'ids': ['b']}
    assert client.get('/api/workspace').json()['coverage']['pending'] == []
    assert client.post('/api/check', json={'unchecked': True}).json()['verdicts'] == []
    for body in ({'unchecked': 'yes'}, {'unchecked': True, 'full': True}, {'unchecked': True, 'ids': ['a']}):
        assert client.post('/api/check', json=body).status_code == 400


def test_model_import_preview_and_explicit_failures(tmp_path, monkeypatch):
    path = tmp_path / 'g.json'
    DecisionGraph().save(path)
    client = TestClient(create_app(str(path), str(tmp_path)))
    body = {'text': '# A\n## Decision\nUse Redis.', 'owner': 'Maya', 'use_llm': True}
    monkeypatch.delenv('NEBIUS_API_KEY', raising=False)
    assert client.post('/api/import/preview', json=body).status_code == 400
    monkeypatch.setenv('NEBIUS_API_KEY', 'test-only')
    monkeypatch.setenv('DLEDGER_MODEL_NANO', 'test-extractor')
    llm.set_transport(lambda tier, system, user: json.dumps([{'message_id': 'adr1', 'text': 'Use Redis.',
                      'subject': 'cache', 'value': 'redis', 'reason': 'Low latency', 'confidence': .8}]))
    try:
        response = client.post('/api/import/preview', json=body)
        assert response.status_code == 200
        assert response.json()['mode'] == 'models'
        row = response.json()['candidates'][0]
        assert row['fields']['owner'] == 'Maya' and row['warnings']
        assert client.get('/api/graph').json()['nodes'] == []
        def fail(*args):
            raise RuntimeError('private provider message')
        llm.set_transport(fail)
        failure = client.post('/api/import/preview', json=body)
        assert failure.status_code == 502
        assert 'private provider message' not in failure.text
    finally:
        llm.set_transport(None)
