"""Bounded, read-only repo snapshots. Watch configuration and source changes."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from .configcheck import SKIP

EXTENSIONS = {'.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.toml', '.yml', '.yaml', '.tf', '.ini', '.cfg', '.sql'}
MAX_FILES = 5000
MAX_BYTES = 1_000_000


def snapshot(repo: str | Path, exclude: tuple[str, ...] = ()) -> dict:
    repo = Path(repo)
    if not repo.is_dir():
        raise ValueError('watched repository does not exist')
    result = {}
    excluded = {Path(p).resolve() for p in exclude}
    count = 0
    for root, dirs, names in os.walk(repo, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not (Path(root) / d).is_symlink())
        for name in sorted(names):
            path = Path(root) / name
            if path.resolve() in excluded:
                continue
            if path.is_symlink() or not (path.suffix in EXTENSIONS or name.startswith(('.env', 'requirements', 'Dockerfile'))):
                continue
            count += 1
            if count > MAX_FILES:
                raise ValueError(f'repository exceeds watch limit ({MAX_FILES} relevant files)')
            try:
                size = path.stat().st_size
                if size > MAX_BYTES:
                    raise ValueError(f'relevant file exceeds watch size limit: {path.relative_to(repo)}')
                result[path.relative_to(repo).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            except FileNotFoundError:
                continue  # a file being renamed will appear in the next snapshot
    try:
        head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=3)
        commit = head.stdout.strip() if head.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        commit = None
    return {'files': result, 'commit': commit}


def changes(before: dict, after: dict) -> list[dict]:
    old, new = before['files'], after['files']
    return [{'path': p, 'change': 'added' if p not in old else 'deleted' if p not in new else 'modified'}
            for p in sorted(set(old) | set(new)) if old.get(p) != new.get(p)]
