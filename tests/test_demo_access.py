import pytest
from fastapi.testclient import TestClient
from dledger.graph import DecisionGraph
from dledger.server import create_app


def test_demo_protects_ui_and_api_but_allows_health(tmp_path, monkeypatch):
    monkeypatch.setenv('DLEDGER_DEMO_USER', 'judge')
    monkeypatch.setenv('DLEDGER_DEMO_PASSWORD', 'test-only-password')
    path = tmp_path / 'g.json'
    DecisionGraph().save(path)
    client = TestClient(create_app(str(path)))
    assert client.get('/healthz').status_code == 200
    for url in ('/', '/api/graph', '/api/history', '/api/usage'):
        response = client.get(url)
        assert response.status_code == 401
        assert 'WWW-Authenticate' in response.headers
        assert 'test-only-password' not in response.text
    assert client.post('/api/check', json={}).status_code == 401
    assert client.get('/', auth=('judge', 'wrong')).status_code == 401
    assert client.get('/api/graph', auth=('judge', 'test-only-password')).status_code == 200
    for header in ('Basic !!!', 'Basic dGVzdA==', 'Bearer nope'):
        assert client.get('/', headers={'Authorization': header}).status_code == 401


def test_incomplete_demo_credentials_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv('DLEDGER_DEMO_USER', 'judge')
    monkeypatch.delenv('DLEDGER_DEMO_PASSWORD', raising=False)
    path = tmp_path / 'g.json'
    DecisionGraph().save(path)
    with pytest.raises(ValueError, match='set both'):
        create_app(str(path))
