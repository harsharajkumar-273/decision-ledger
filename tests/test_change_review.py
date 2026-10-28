import copy
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dledger import change_review
from dledger.graph import DecisionGraph
from dledger.schema import Claim, Status
from dledger.server import create_app, graph_payload


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), '-c', 'user.name=Test',
                                    '-c', 'user.email=test@example.invalid', *args], stderr=subprocess.PIPE).decode().strip()


@pytest.fixture
def migration(tmp_path):
    repo = tmp_path / 'repo'
    shutil.copytree(change_review.DEMO / 'before', repo)
    git(repo, 'init')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'base')
    base = git(repo, 'rev-parse', 'HEAD')
    shutil.copyfile(change_review.DEMO / 'after' / 'compose.yml', repo / 'compose.yml')
    git(repo, 'add', 'compose.yml')
    git(repo, 'commit', '-m', 'migrate')
    return repo, base


def test_commit_comparison_traces_evidence_and_does_not_mutate(migration):
    repo, base = migration
    graph = DecisionGraph.load(change_review.DEMO / 'ledger.json')
    old = graph_payload(graph)
    head, status = git(repo, 'rev-parse', 'HEAD'), git(repo, 'status', '--porcelain')
    result = change_review.review(graph, repo, base)
    assert result['counts'] == {'new': 3, 'existing': 0, 'resolved': 1, 'unchanged': 2}
    rows = {r['id']: r for r in result['findings']}
    assert rows['d1']['before']['status'] == 'valid'
    assert rows['d1']['after']['status'] == 'contradicted'
    assert {c['owner'] for c in rows['d1']['affected']} == {'maya', 'li'}
    assert rows['d1']['affected'][0]['path'][0]['id'] == 'd1'
    assert any(e['ref'] == 'compose.yml:3' for e in rows['d1']['after']['evidence'])
    assert result['changes'] == [{'path': 'compose.yml', 'change': 'modified'}]
    assert graph_payload(graph) == old
    assert git(repo, 'rev-parse', 'HEAD') == head and git(repo, 'status', '--porcelain') == status


def test_same_snapshot_retains_existing_findings(migration):
    repo, base = migration
    graph = DecisionGraph.load(change_review.DEMO / 'ledger.json')
    result = change_review.review(graph, repo, base, base)
    assert result['counts']['new'] == 0 and result['counts']['resolved'] == 0
    assert result['counts']['existing'] == 1
    assert result['changes'] == []


def test_working_tree_tracks_uncommitted_change_without_checkout(migration):
    repo, base = migration
    shutil.copyfile(change_review.DEMO / 'before' / 'compose.yml', repo / 'compose.yml')
    graph = DecisionGraph.load(change_review.DEMO / 'ledger.json')
    status = git(repo, 'status', '--porcelain')
    result = change_review.review(graph, repo, 'HEAD', 'WORKTREE')
    assert result['target']['working_tree'] is True
    assert next(r for r in result['findings'] if r['id'] == 'd1')['category'] == 'resolved'
    assert git(repo, 'status', '--porcelain') == status


@pytest.mark.parametrize('ref', ['--help', '', None, 'missing-branch', 'HEAD\n--help'])
def test_invalid_revisions_are_rejected(migration, ref):
    repo, _ = migration
    with pytest.raises(ValueError):
        change_review.review(DecisionGraph(), repo, ref)


def test_relevant_symlink_and_oversized_blob_fail_closed(migration, tmp_path, monkeypatch):
    repo, base = migration
    (repo / 'evil.py').symlink_to(tmp_path / 'outside.py')
    git(repo, 'add', 'evil.py')
    git(repo, 'commit', '-m', 'link')
    with pytest.raises(ValueError, match='symlinks'):
        change_review.review(DecisionGraph(), repo, base)
    monkeypatch.setattr(change_review.watch, 'MAX_BYTES', 1)
    with pytest.raises(ValueError, match='size limits'):
        change_review.review(DecisionGraph(), repo, base, base)


def test_api_demo_and_real_review_preserve_ledger_and_history(migration, tmp_path):
    repo, base = migration
    graph_path = tmp_path / 'ledger.json'
    graph = DecisionGraph.load(change_review.DEMO / 'ledger.json')
    graph.save(graph_path)
    client = TestClient(create_app(str(graph_path), str(repo)))
    before = client.get('/api/report').json()
    raw = graph_path.read_bytes()
    assert client.get('/api/change-review/options').json()['git_available']
    for body in ({'demo': True}, {'base': base, 'target': 'HEAD'}):
        response = client.post('/api/change-review', json=body)
        assert response.status_code == 200
        assert response.json()['counts']['new'] == 3
        assert response.json()['read_only']
    assert client.get('/api/report').json() == before
    assert client.get('/api/history').json()['events'] == []
    assert graph_path.read_bytes() == raw
    assert client.post('/api/change-review', json={'demo': 'yes'}).status_code == 400
    assert client.post('/api/change-review', json={'base': '--help'}).status_code == 400


def test_demo_works_without_git_repository(tmp_path):
    path = tmp_path / 'ledger.json'
    DecisionGraph().save(path)
    client = TestClient(create_app(str(path)))
    assert client.get('/api/change-review/options').json()['git_available'] is False
    result = client.post('/api/change-review', json={'demo': True}).json()
    assert result['demo'] and result['execution']['mode'] == 'rules'
    assert result['counts']['new'] == 3
    assert client.post('/api/change-review', json={'base': 'HEAD'}).status_code == 400


def test_uncertainty_becoming_contradiction_is_new_failure():
    assert change_review.category('needs_review', 'contradicted') == 'new'
    assert change_review.category('contradicted', 'stale') == 'existing'
    assert change_review.category('needs_review', 'needs_review') == 'existing'
    assert change_review.category('needs_review', 'valid') == 'resolved'


def test_worktree_excludes_application_state(migration):
    repo, base = migration
    ledger = repo / 'ledger.json'
    graph = DecisionGraph.load(change_review.DEMO / 'ledger.json')
    graph.save(ledger)
    result = change_review.review(graph, repo, base, 'WORKTREE', exclude=(ledger,))
    assert [c['path'] for c in result['changes']] == ['compose.yml']
