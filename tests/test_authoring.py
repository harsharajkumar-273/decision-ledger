from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dledger.graph import DecisionGraph
from dledger.schema import Claim, Status
from dledger.server import create_app
from dledger.workflow import create_decision


def payload(**overrides):
    return dict(text='Use MongoDB for application storage', subject='database', value='mongodb',
                owner='Raj', reason='Document storage matches our ingestion workload.', **overrides)


@pytest.mark.parametrize('change', [dict(status='valid'), dict(dependencies='db'), dict(dependencies=['missing']),
                                   dict(kind='unknown'), dict(date='tomorrow'), dict(owner=123), dict(reason=' ')])
def test_invalid_creation_is_atomic(change):
    graph = DecisionGraph()
    body = payload()
    body.update(change)
    with pytest.raises(ValueError):
        create_decision(graph, body)
    assert not graph.claims() and not graph.audit


def test_prerequisite_risk_and_retired_rejection():
    graph = DecisionGraph()
    graph.add_claim(Claim('db', 'Use Postgres', 'database', 'postgresql', status=Status.CONTRADICTED))
    event = create_decision(graph, payload(dependencies=['db', 'db']))
    assert graph.claim(event['decision_id']).status == Status.NEEDS_REVIEW
    assert len(list(graph.g.edges())) == 1
    graph.claim('db').status = Status.SUPERSEDED
    with pytest.raises(ValueError):
        create_decision(graph, payload(dependencies=['db']))


def test_create_verify_and_restore(tmp_path, monkeypatch):
    monkeypatch.setenv('DLEDGER_PERSIST', '1')
    monkeypatch.setenv('DLEDGER_USE_LLM', '0')
    path = tmp_path / 'ledger.json'
    DecisionGraph().save(path)
    (tmp_path / 'compose.yml').write_text('services:\n  db:\n    image: mongo:7\n')
    client = TestClient(create_app(str(path), str(tmp_path)))
    response = client.post('/api/decisions', json=payload())
    assert response.status_code == 200
    created = response.json()
    cid = created['created_decision_id']
    assert created['event_type'] == 'decision_created'
    assert created['graph']['nodes'][0]['status'] == 'active'
    assert created['graph']['audit'][0]['reviewer'] == 'Raj'
    assert created['known_verdicts'] == []
    verified = client.post('/api/check', json={'ids': [cid]}).json()
    assert verified['verdicts'][0]['id'] == cid
    assert verified['verdicts'][0]['status'] == 'valid'
    restored = TestClient(create_app(str(path), str(tmp_path)))
    assert restored.get('/api/report').json()['event_id'] == verified['event_id']
    original = restored.get('/api/history/' + created['event_id']).json()
    assert original['graph']['nodes'][0]['status'] == 'active'
    for ids in ([], ['missing'], 'all', [1]):
        assert client.post('/api/check', json={'ids': ids}).status_code == 400
    assert client.post('/api/check', json={'ids': [cid], 'full': True}).status_code == 400
    assert client.post('/api/decisions', content='{invalid').status_code == 400


def test_targeted_check_retains_failed_prerequisite_risk(tmp_path):
    from dledger.pipeline import check
    graph = DecisionGraph()
    graph.add_claim(Claim('db', 'Retired assumption', 'database', 'postgresql', status=Status.CONTRADICTED))
    event = create_decision(graph, payload(dependencies=['db']))
    (tmp_path / 'compose.yml').write_text('services:\n  db:\n    image: mongo:7\n')
    verdicts = check(graph, str(tmp_path), use_llm=False, ids=[event['decision_id']])
    assert verdicts[0].status == Status.NEEDS_REVIEW
    assert graph.claim(event['decision_id']).status == Status.NEEDS_REVIEW
