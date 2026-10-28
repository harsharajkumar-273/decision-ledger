"""Read declared database configuration without executing application code.

Evidence describes checked-in configuration, not a running deployment. URL
credentials, hosts and raw configuration lines never enter model prompts.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import yaml

from .schema import Claim, Evidence

SKIP = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'dist', 'build', '.aws', '.codex'}
MAX_BYTES = 400_000
URL_KEYS = {'DATABASE_URL', 'SQLALCHEMY_DATABASE_URI', 'SQLALCHEMY_DATABASE_URL', 'MONGO_URI', 'MONGODB_URI'}
SCHEMES = {'postgres': 'postgresql', 'postgresql': 'postgresql', 'mongodb': 'mongodb', 'mongo': 'mongodb',
           'mysql': 'mysql', 'mariadb': 'mysql', 'sqlite': 'sqlite'}


def canonical(value: str) -> str:
    v = value.lower().strip()
    return SCHEMES.get(v, v)


def files(repo: Path):
    for root, dirs, names in os.walk(repo, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP | {'tests', 'test', 'docs', 'examples'}
                   and not (Path(root) / d).is_symlink()]
        for name in sorted(names):
            p = Path(root) / name
            if p.is_symlink():
                continue
            if name.endswith('.py') or name.startswith('.env') or (
                name.startswith(('compose', 'docker-compose')) and name.endswith(('.yml', '.yaml'))
            ):
                yield p


def database_configuration(claim: Claim, repo: Path) -> list[Evidence]:
    if claim.subject.lower().strip() not in {'database', 'primary database', 'primary-database'}:
        return []
    evidence: list[Evidence] = []
    chosen = canonical(claim.value)

    def add_url(value, source, line, label):
        if not isinstance(value, str):
            return
        value = value.strip().strip('"\'')
        match = re.match(r'^([a-z][a-z0-9+.-]*)://', value, re.I)
        if not match:
            evidence.append(Evidence('repo', f'{label} is dynamic or unresolved; deployment settings need review',
                                     None, f'{source}:{line}'))
            return
        scheme = match.group(1).lower().split('+', 1)[0]
        actual = SCHEMES.get(scheme)
        if actual:
            evidence.append(Evidence('repo', f'{label} configures {actual}; decision selects {chosen}. '
                                     'Credentials and host omitted.', actual == chosen, f'{source}:{line}'))

    for path in files(repo):
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(errors='replace')
        except OSError:
            continue
        source = path.relative_to(repo).as_posix()
        if claim.scope and claim.scope.lower() not in source.lower():
            continue
        lines = text.splitlines()
        if path.name.startswith('.env'):
            # An actual local env file takes precedence over its example.
            if path.name != '.env' and (path.parent / '.env').is_file():
                continue
            for i, line in enumerate(lines, 1):
                m = re.match(r'^\s*(?:export\s+)?([A-Z_]+)\s*=\s*(.*)', line)
                if m and m.group(1) in URL_KEYS:
                    add_url(m.group(2), source, i, m.group(1))
        elif path.suffix == '.py':
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for call in ast.walk(tree):
                if not isinstance(call, ast.Call) or not call.args:
                    continue
                func = call.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ''
                if name in {'create_engine', 'create_async_engine', 'MongoClient', 'AsyncIOMotorClient'}:
                    if isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                        add_url(call.args[0].value, source, call.lineno, name)
        else:
            try:
                doc = yaml.safe_load(text)
                services = doc.get('services', {}) if isinstance(doc, dict) else {}
                if not isinstance(services, dict):
                    continue
            except yaml.YAMLError:
                evidence.append(Evidence('repo', 'Deployment YAML could not be parsed', None, source))
                continue
            for name, service in services.items():
                if not isinstance(service, dict):
                    continue
                env = service.get('environment', {})
                if isinstance(env, list):
                    env = dict(v.split('=', 1) for v in env if isinstance(v, str) and '=' in v)
                if isinstance(env, dict):
                    for key, value in env.items():
                        if key in URL_KEYS:
                            line = next((i for i, s in enumerate(lines, 1) if str(key) in s), 1)
                            add_url(value, source, line, f'{name}.{key}')
                image = service.get('image')
                if isinstance(image, str):
                    basename = image.rsplit('/', 1)[-1].split(':', 1)[0].split('@', 1)[0]
                    actual = SCHEMES.get(basename)
                    if actual and actual != 'sqlite':
                        line = next((i for i, s in enumerate(lines, 1) if image in s), 1)
                        evidence.append(Evidence('repo', f'Deployment service {name} uses a {actual} image; '
                                                 f'decision selects {chosen}. Runtime availability is not checked.',
                                                 actual == chosen, f'{source}:{line}'))
    if any(e.supports is None for e in evidence):
        # Unresolved settings may override the visible service image. Avoid
        # claiming validity until the applicable environment is established.
        for e in evidence:
            e.supports = None
    if claim.scope and not evidence:
        return [Evidence('repo', 'No native configuration matches the explicit decision scope', None)]
    return evidence
