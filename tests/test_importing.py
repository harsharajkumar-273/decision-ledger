import pytest
from fastapi.testclient import TestClient

from dledger.graph import DecisionGraph
from dledger.importing import preview
from dledger.server import create_app

ADR = '''# Choose Redis
Status: Accepted
Owner: Maya

## Context
Postgres was considered but session lookups need low latency.

## Decision
Use Redis for sessions.

## Consequences
Additional operational overhead.
'''


def test_preview_retains_provenance_and_ignores_alternatives():
    rows = preview({'text': ADR + '\n# Next decision\n## Decision\nUse MongoDB for documents.', 'source': 'docs/adr.md'})
    assert len(rows) == 2
    assert rows[0]['fields']['subject'] == 'cache'
    assert rows[0]['fields']['value'] == 'redis'
    assert rows[0]['fields']['owner'] == 'Maya'
    assert rows[0]['fields']['source'] == 'docs/adr.md:L1'
    assert rows[0]['warnings'] == []
    assert rows[1]['warnings']
    assert rows[1]['fields']['source'].startswith('docs/adr.md:L')


def test_ambiguous_or_unstructured_documents_require_review():
    row = preview({'text': '# Draft\nStatus: Proposed\n## Decision\nUse Redis or MongoDB.', 'owner': 'Raj'})[0]
    assert row['fields']['subject'] == ''
    assert 'Document status is proposed' in str(row['warnings'])
    assert preview({'text': 'Some notes about redis'})[0]['fields']['text'] == ''


@pytest.mark.parametrize('body', [[], {}, {'text': 123}, {'text': 'x' * 100001}, {'text': '# A\n' * 21}, {'text': ADR, 'owner': []}])
def test_invalid_preview(body):
    with pytest.raises(ValueError):
        preview(body)


def test_import_atomic_duplicate_safe_and_durable(tmp_path, monkeypatch):
    monkeypatch.setenv('DLEDGER_PERSIST', '1')
    path = tmp_path / 'ledger.json'
    DecisionGraph().save(path)
    client = TestClient(create_app(str(path), str(tmp_path)))
    fields = client.post('/api/import/preview', json={'text': ADR}).json()['candidates'][0]['fields']
    assert client.get('/api/graph').json()['nodes'] == []
    bad = {**fields, 'owner': ''}
    assert client.post('/api/import', json={'decisions': [fields, bad]}).status_code == 400
    assert client.get('/api/graph').json()['nodes'] == []
    assert client.get('/api/history').json()['events'] == []
    result = client.post('/api/import', json={'decisions': [fields, fields]}).json()
    assert len(result['created_decision_ids']) == 1
    assert result['skipped_duplicates'] == 1
    assert result['event_type'] == 'decisions_imported'
    assert result['graph']['nodes'][0]['status'] == 'active'
    assert len(result['graph']['audit']) == 1
    retry = client.post('/api/import', json={'decisions': [fields]}).json()
    assert retry['skipped_duplicates'] == 1 and retry['created_decision_ids'] == []
    assert len(client.get('/api/history').json()['events']) == 1
    restored = TestClient(create_app(str(path), str(tmp_path)))
    assert restored.get('/api/report').json()['event_id'] == result['event_id']
    assert len(DecisionGraph.load(path).claims()) == 1
