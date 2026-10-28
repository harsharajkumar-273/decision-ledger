import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dledger import actions, watch, workflow
from dledger.graph import DecisionGraph
from dledger.pipeline import check
from dledger.schema import Claim, Status
from dledger.server import create_app
from dledger.verify import verify_tech_choice

ROOT = Path(__file__).parent.parent / 'data' / 'sample'


def database():
    return Claim('db', 'Use Postgres', 'database', 'postgresql')


@pytest.mark.parametrize('url,expected', [('postgresql://secret:password@remote/db', True),
                                        ('mongodb://secret:password@remote/db', False),
                                        ('${DATABASE_URL}', None)])
def test_native_url_config_is_redacted(tmp_path, url, expected):
    (tmp_path / '.env.example').write_text('DATABASE_URL=' + url)
    evidence = verify_tech_choice(database(), tmp_path)
    assert evidence[0].supports is expected
    assert 'password' not in str(evidence) and 'secret' not in str(evidence)
    assert evidence[0].ref == '.env.example:1'


def test_remote_url_overrides_leftover_driver(tmp_path):
    (tmp_path / 'requirements.txt').write_text('pymongo==4.8')
    (tmp_path / '.env.example').write_text('DATABASE_URL=postgresql://managed.example/db')
    assert verify_tech_choice(database(), tmp_path)[0].supports is True


def test_compose_partial_migration_returns_mixed_evidence(tmp_path):
    (tmp_path / 'compose.yml').write_text('services:\n  old:\n    image: postgres:16\n  new:\n    image: mongo:7\n')
    # Docker Hub's mongo image name is canonicalized to MongoDB.
    evidence = verify_tech_choice(database(), tmp_path)
    assert {e.supports for e in evidence} == {True, False}


def test_literal_engine_calls_not_executed(tmp_path):
    (tmp_path / 'app.py').write_text('raise RuntimeError("never execute")\nengine = create_engine("mongodb://secret:password@host/db")')
    assert verify_tech_choice(database(), tmp_path)[0].supports is False


def test_human_supersession_survives_recheck_and_needs_review(tmp_path):
    g = DecisionGraph.load(ROOT / 'graph.json')
    verdicts = check(g, ROOT / 'repo', use_llm=False)
    assert actions.issue_drafts(g, verdicts)[0]['owners'] == ['li', 'maya']
    workflow.resolve(g, 'd1', 'supersede', 'Raj', 'Migration to MongoDB is now approved.', 'd5')
    check(g, ROOT / 'repo', use_llm=False, ids=[c.id for c in g.claims()])
    assert g.claim('d1').status == Status.SUPERSEDED
    assert g.claim('d3').status == Status.NEEDS_REVIEW
    workflow.resolve(g, 'd3', 'review', 'Maya', 'ORM usage was reviewed against an independent service unaffected by this migration.')
    path = tmp_path / 'ledger.json'
    g.save(path)
    restored = DecisionGraph.load(path)
    assert len(restored.audit) == 2 and restored.claim('d3').status == Status.VALID
    assert not actions.issue_drafts(g, verdicts)


def test_cannot_confirm_failed_decision_or_create_cycle():
    g = DecisionGraph.load(ROOT / 'graph.json')
    check(g, ROOT / 'repo', use_llm=False)
    with pytest.raises(ValueError):
        workflow.resolve(g, 'd1', 'review', 'Maya', 'Ignore the evidence without replacement.')
    workflow.resolve(g, 'd1', 'supersede', 'Raj', 'New database replaces the old one.', 'd5')
    with pytest.raises(ValueError):
        workflow.resolve(g, 'd5', 'supersede', 'Raj', 'Attempt to reverse the replacement.', 'd1')


def test_watcher_runs_full_check_on_native_config_change(tmp_path, monkeypatch):
    monkeypatch.setenv('DLEDGER_USE_LLM', '0')
    monkeypatch.setenv('DLEDGER_PERSIST', '1')
    g = DecisionGraph.load(ROOT / 'graph.json')
    path = tmp_path / 'ledger.json'
    g.save(path)
    (tmp_path / '.env.example').write_text('DATABASE_URL=postgresql://db/app')
    app = create_app(str(path), str(tmp_path))
    c = TestClient(app)
    assert c.post('/api/watch', json={'enabled': True}).status_code == 200
    (tmp_path / '.env.example').write_text('DATABASE_URL=mongodb://db/app')
    app.state.poll_changes()
    report = c.get('/api/report').json()
    assert report['trigger'] == 'repo_change'
    assert report['changes'] == [{'path': '.env.example', 'change': 'modified'}]
    assert len(report['verdicts']) == 6
    assert next(n for n in report['graph']['nodes'] if n['id'] == 'd1')['status'] == 'contradicted'
    app.state.poll_changes()
    assert c.get('/api/report').json()['checked_at'] == report['checked_at']  # saved ledger is excluded
    resolved = c.post('/api/decisions/d1/resolve', json={'action': 'supersede', 'target_id': 'd5',
                     'reviewer': 'Raj', 'note': 'Migration completed; retire the Postgres decision.'})
    assert resolved.status_code == 200 and resolved.json()['drafts'] == []
    assert json.loads(path.read_text())['audit'][0]['reviewer'] == 'Raj'


def test_snapshot_detects_deletion_and_ignores_symlinks(tmp_path):
    file = tmp_path / 'app.py'
    file.write_text('x=1')
    (tmp_path / 'config.json').symlink_to('/etc/passwd')
    before = watch.snapshot(tmp_path)
    file.unlink()
    assert watch.changes(before, watch.snapshot(tmp_path)) == [{'path': 'app.py', 'change': 'deleted'}]


def test_report_verdicts_match_dependency_propagation(monkeypatch):
    monkeypatch.setenv('DLEDGER_USE_LLM', '0')
    c = TestClient(create_app(str(ROOT / 'graph.json'), str(ROOT / 'repo')))
    report = c.post('/api/check', json={'full': True}).json()
    statuses = {n['id']: n['status'] for n in report['graph']['nodes']}
    assert all(v['status'] == statuses[v['id']] for v in report['verdicts'])
    assert next(v for v in report['verdicts'] if v['id'] == 'd3')['status'] == 'needs_review'
