"""Read-only comparison of recorded decisions across bounded repository snapshots."""
from __future__ import annotations

import copy
import hashlib
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import networkx as nx

from . import watch, llm
from .graph import DecisionGraph
from .pipeline import check
from .schema import Status

MAX_FILES, MAX_TOTAL = 2000, 20_000_000
DEMO = Path(__file__).resolve().parents[2] / 'data' / 'change-demo'
RISK = {'contradicted', 'stale', 'needs_review'}


def git(repo, *args):
    try:
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('Git is unavailable or the repository operation timed out')
    if result.returncode:
        raise ValueError('Git could not read the repository or revision; use a local commit or branch')
    return result.stdout


def resolve(repo, ref):
    if not isinstance(ref, str) or not ref or len(ref) > 200 or ref.startswith('-') or any(ord(c) < 32 for c in ref):
        raise ValueError('provide a local Git revision of at most 200 characters')
    return git(repo, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()


def relevant(name, exclude=()):
    if name in exclude:
        return False
    p = PurePosixPath(name)
    return (not p.is_absolute() and '..' not in p.parts and not set(p.parts) &
            {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'dist', 'build', '.aws', '.codex', '.local'}
            and (p.suffix in watch.EXTENSIONS or p.name.startswith(('.env', 'requirements', 'Dockerfile'))))


def snapshot_commit(repo, sha, destination, exclude=()):
    tree = git(repo, 'ls-tree', '-r', '-z', '-l', '--full-tree', sha)
    entries = tree.split(b'\0')
    if len(entries) > 20001:
        raise ValueError('Git tree exceeds comparison limit (20,000 entries)')
    total, files = 0, {}
    for entry in entries:
        if not entry:
            continue
        meta, raw_name = entry.split(b'\t', 1)
        mode, kind, oid, size = meta.split()
        name = raw_name.decode('utf-8')
        if not relevant(name, exclude):
            continue
        if mode not in (b'100644', b'100755') or kind != b'blob':
            raise ValueError('comparison cannot verify relevant symlinks or submodules')
        size = int(size)
        total += size
        if size > watch.MAX_BYTES or total > MAX_TOTAL or len(files) >= MAX_FILES:
            raise ValueError('comparison exceeds file or snapshot size limits')
        data = git(repo, 'cat-file', 'blob', oid.decode())
        if len(data) != size:
            raise ValueError('Git blob size changed while reading')
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
    return {'commit': sha, 'files': files}


def snapshot_worktree(repo, destination, exclude=()):
    before = watch.snapshot(repo)
    files, total = {}, 0
    for name, digest in before['files'].items():
        if not relevant(name, exclude):
            continue
        path = repo / name
        if path.is_symlink() or not path.resolve().is_relative_to(repo.resolve()):
            raise ValueError('working tree contains a relevant symlink')
        data = path.read_bytes()
        total += len(data)
        if len(data) > watch.MAX_BYTES or total > MAX_TOTAL or len(files) >= MAX_FILES:
            raise ValueError('comparison exceeds file or snapshot size limits')
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('working tree changed during comparison; retry')
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files[name] = digest
    if before != watch.snapshot(repo):
        raise ValueError('working tree changed during comparison; retry')
    return {'commit': before['commit'], 'working_tree': True, 'files': files}


def assessed(graph, repo, use_llm):
    graph = copy.deepcopy(graph)
    for claim in graph.claims():
        if claim.status != Status.SUPERSEDED:
            claim.status = Status.ACTIVE
    verdicts = check(graph, str(repo), use_llm=use_llm, ids=[c.id for c in graph.claims()])
    return graph, {v.claim_id: {'status': v.status.value, 'rationale': v.rationale,
                              'evidence': [e.__dict__ for e in v.evidence]} for v in verdicts}


def category(before, after):
    failed = {'contradicted', 'stale'}
    if after in failed and before not in failed:
        return 'new'
    if after in RISK and before not in RISK:
        return 'new'
    if after in RISK:
        return 'existing'
    return 'resolved' if before in RISK else 'unchanged'


def compare(graph, before_dir, after_dir, before_snapshot, after_snapshot, use_llm=False):
    usage = {tier: dict(values) for tier, values in llm.USAGE.items()}
    before_graph, before = assessed(graph, before_dir, use_llm)
    if before_snapshot['files'] == after_snapshot['files']:
        after_graph, after = copy.deepcopy(before_graph), copy.deepcopy(before)
    else:
        after_graph, after = assessed(graph, after_dir, use_llm)
    edges = nx.DiGraph((u, v) for u, v, d in graph.g.edges(data=True) if d['etype'] == 'depends_on')
    rows = []
    for claim in after_graph.claims():
        if claim.id not in after:
            continue
        a, b = before[claim.id], after[claim.id]
        group = category(a['status'], b['status'])
        affected = []
        for cid in sorted(after_graph.impact(claim.id)):
            dependent = after_graph.claim(cid)
            if dependent.status == Status.NEEDS_REVIEW:
                path = list(reversed(nx.shortest_path(edges, cid, claim.id)))
                affected.append({'id': cid, 'text': dependent.text, 'owner': dependent.owner,
                                 'path': [{'id': i, 'text': graph.claim(i).text} for i in path]})
        rows.append({'id': claim.id, 'text': claim.text, 'owner': claim.owner, 'source': claim.source,
                     'reason': claim.reason, 'category': group, 'before': a, 'after': b, 'affected': affected})
    delta = {tier: {key: value - usage[tier][key] for key, value in values.items()} for tier, values in llm.USAGE.items()}
    calls = sum(v['calls'] for v in delta.values())
    fallbacks = sum('LLM judge unavailable:' in v['rationale'] for v in list(before.values()) + list(after.values()))
    return {'at': datetime.now(timezone.utc).isoformat(), 'read_only': True,
            'base': before_snapshot, 'target': after_snapshot,
            'changes': watch.changes(before_snapshot, after_snapshot), 'findings': rows,
            'brief': review_brief(rows, watch.changes(before_snapshot, after_snapshot)),
            'counts': {key: sum(row['category'] == key for row in rows) for key in ('new', 'existing', 'resolved', 'unchanged')},
            'execution': {'mode': 'rules' if not use_llm else 'fallback' if fallbacks else 'models' if calls else 'rules',
                          'calls': calls, 'fallbacks': fallbacks, 'usage': delta,
                          'model': os.getenv('DLEDGER_MODEL_ULTRA') if use_llm else None},
            'limitations': 'Compares the same current ledger against both snapshots. Does not reconstruct historical decisions, run application tests, or prove runtime breakage. Working-tree review includes relevant untracked/ignored files; no raw file content is returned.'}


def review(graph, repo, base, target='HEAD', use_llm=False, exclude=()):
    repo = Path(repo).resolve()
    root = Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    if root != repo:
        raise ValueError('configured repository must be a Git repository root')
    excluded = set()
    for path in exclude:
        try:
            excluded.add(Path(path).resolve().relative_to(repo).as_posix())
        except ValueError:
            pass
    base_sha = resolve(repo, base)
    target_sha = None if target == 'WORKTREE' else resolve(repo, target)
    with tempfile.TemporaryDirectory(prefix='dledger-review-') as temp:
        before_dir, after_dir = Path(temp) / 'base', Path(temp) / 'target'
        before_dir.mkdir(); after_dir.mkdir()
        before = snapshot_commit(repo, base_sha, before_dir, excluded)
        after = snapshot_worktree(repo, after_dir, excluded) if target == 'WORKTREE' else snapshot_commit(repo, target_sha, after_dir, excluded)
        return compare(graph, before_dir, after_dir, before, after, use_llm)


def demo(use_llm=False):
    graph = DecisionGraph.load(DEMO / 'ledger.json')
    result = compare(graph, DEMO / 'before', DEMO / 'after', watch.snapshot(DEMO / 'before'),
                     watch.snapshot(DEMO / 'after'), use_llm)
    result['demo'] = True
    result['base'] = {'label': 'Before: PostgreSQL', 'files': result['base']['files']}
    result['target'] = {'label': 'Proposed: MongoDB', 'files': result['target']['files']}
    return result


def review_brief(findings, changes):
    """A grounded summary; dependency concerns are distinct from direct conflicts."""
    attention = [f for f in findings if f['category'] in ('new', 'existing')]
    owners = sorted({f['owner'] for f in attention if f['owner']} |
                    {d['owner'] for f in attention for d in f['affected'] if d['owner']})
    direct = [f for f in attention if f['after']['status'] in ('contradicted', 'stale')]
    uncertain = [f for f in attention if f['after']['status'] == 'needs_review']
    return {'headline': f"{len(attention)} decisions need review" if attention else 'No decisions need review in this comparison',
            'changed_files': [c['path'] for c in changes], 'owners': owners,
            'unassigned': sum(not f['owner'] for f in attention),
            'direct_conflicts': [f['id'] for f in direct],
            'review_concerns': [f['id'] for f in uncertain],
            'items': [{'id': f['id'], 'text': f['text'], 'owner': f['owner'],
                       'category': f['category'], 'status': f['after']['status'],
                       'rationale': f['after']['rationale'],
                       'evidence': f['after']['evidence'][:2],
                       'affected': [{'id': d['id'], 'text': d['text'], 'owner': d['owner']} for d in f['affected']]} for f in attention]}
