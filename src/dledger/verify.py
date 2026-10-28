"""Verifiers check a claim against reality. v0 is read-only and runs locally;
the production path runs the same code inside an OpenShell/NemoClaw sandbox
with a read-only mount of the repo."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .schema import Claim, Evidence

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
MANIFESTS = (
    "requirements", "pyproject.toml", "package.json", "poetry.lock", "pipfile",
    "docker-compose", "dockerfile", "go.mod", "cargo.toml", "pom.xml", "build.gradle", ".tf",
)
MAX_BYTES = 400_000

# value -> tokens that indicate it in manifests/config. Extend freely.
ALIASES: dict[str, list[str]] = {
    "postgresql": ["postgres", "psycopg", "asyncpg", "pg8000"],
    "postgres": ["postgres", "psycopg", "asyncpg", "pg8000"],
    "mongodb": ["mongo", "pymongo", "motor", "mongoose"],
    "mysql": ["mysql", "pymysql", "mysqlclient"],
    "redis": ["redis"],
    "celery": ["celery"],
    "kafka": ["kafka"],
    "rabbitmq": ["rabbitmq", "pika", "amqp"],
}


def _tokens(value: str) -> list[str]:
    v = value.lower().strip()
    return ALIASES.get(v, [v])


def _manifest_files(repo: Path):
    for p in repo.rglob("*"):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.parts):
            continue
        name = p.name.lower()
        if any(name.startswith(m) or name.endswith(m) for m in MANIFESTS):
            yield p


def verify_tech_choice(claim: Claim, repo: str | Path) -> list[Evidence]:
    """Is the chosen technology present in the repo's dependency/config files?"""
    repo = Path(repo)
    from .configcheck import database_configuration

    configured = database_configuration(claim, repo)
    if configured:
        return configured
    # Explicit application settings outrank installed libraries: both old and
    # new drivers can remain installed after a migration. Never infer a migration
    # solely from a missing dependency.
    runtime = repo / "runtime.json"
    if runtime.is_file():
        try:
            if runtime.stat().st_size > MAX_BYTES:
                raise ValueError("runtime snapshot too large")
            settings = json.loads(runtime.read_text())["technologies"]
            if not isinstance(settings, dict):
                raise ValueError("technologies must be an object")
            actual = settings.get(claim.subject.lower().strip())
            if actual is not None:
                if not isinstance(actual, str) or not actual.strip():
                    raise ValueError("technology must be a nonempty string")
                actual = actual.lower().strip()
                chosen = claim.value.lower().strip()
                ok = actual == chosen or _tokens(actual) == _tokens(chosen)
                return [Evidence("repo", f"Application configuration selects '{actual}' for '{claim.subject}', "
                                 f"decision selects '{claim.value}'", ok, f"runtime.json:technologies.{claim.subject}")]
        except (OSError, ValueError, KeyError, TypeError):
            return [Evidence("repo", "runtime.json is unreadable or invalid; configuration needs review", None,
                             "runtime.json")]
    toks = _tokens(claim.value)
    pat = re.compile(r"\b(?:" + "|".join(re.escape(t) + r"[a-z0-9_-]*" for t in toks) + r")\b", re.I)
    scanned, hits = 0, []
    for f in _manifest_files(repo):
        if f.stat().st_size > MAX_BYTES:
            continue
        scanned += 1
        try:
            for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                if pat.search(line) and not line.strip().startswith("#"):
                    hits.append((f.relative_to(repo).as_posix(), n, pat.search(line).group(0)))
        except OSError:
            continue
    if hits:
        return [Evidence("repo", f"'{claim.value}' dependency/config token found: {token}; installation is not runtime proof",
                         True, f"{p}:{n}") for p, n, token in hits[:3]]
    return [Evidence("repo", f"'{claim.value}' not found in {scanned} manifest/config files; "
                     "absence does not prove the decision is wrong", None, None)]


def verify_commitment(claim: Claim, source: str | Path, as_of: str | None = None) -> list[Evidence]:
    """Customer commitments: subject = feature slug, value = promised ISO date.
    `source` is a directory containing roadmap.json:
      [{"feature": "sso", "status": "shipped|in_progress|planned", "eta": "2026-11-15", "shipped_on": "..."}]
    """
    import datetime as dt
    import json
    import os

    path = Path(source) / "roadmap.json"
    if not path.exists():
        return [Evidence("repo", "no roadmap.json to verify against", None)]
    try:
        promised = dt.date.fromisoformat(claim.value)
    except ValueError:
        return [Evidence("repo", f"commitment date '{claim.value}' is not ISO (YYYY-MM-DD)", None)]
    today = dt.date.fromisoformat(as_of or os.getenv("DLEDGER_AS_OF") or dt.date.today().isoformat())
    item = next((r for r in json.loads(path.read_text()) if r["feature"].lower() == claim.subject.lower()), None)
    if item is None:
        return [Evidence("repo", f"'{claim.subject}' is not on the roadmap", None)]
    ref = f"roadmap.json:{item['feature']}"
    if item["status"] == "shipped":
        shipped = dt.date.fromisoformat(item["shipped_on"])
        ok = shipped <= promised
        verb = "on time" if ok else f"late by {(shipped - promised).days} days"
        return [Evidence("repo", f"shipped {item['shipped_on']}, promised {claim.value}: {verb}", ok, ref)]
    eta = item.get("eta")
    if eta and dt.date.fromisoformat(eta) > promised:
        return [Evidence("repo", f"status {item['status']}, eta {eta} is after the promised {claim.value}", False, ref)]
    if today > promised:
        return [Evidence("repo", f"status {item['status']} and the promised date {claim.value} has passed", False, ref)]
    return [Evidence("repo", f"status {item['status']}, eta {eta}, still within the promised {claim.value}", True, ref)]


VERIFIERS = {"tech_choice": verify_tech_choice, "commitment": verify_commitment}


def verify(claim: Claim, repo: str | Path | None, web: bool = False) -> list[Evidence]:
    if claim.condition:
        return [Evidence("repo", "Conditional decision requires confirmation of its prerequisite; "
                         "the current verifiers cannot establish that it was satisfied", None, claim.source)]
    fn = VERIFIERS.get(claim.kind)
    if fn is None or repo is None:
        ev = [Evidence("repo", f"no verifier for kind '{claim.kind}'", None)]
    else:
        ev = fn(claim, repo)
    if web and claim.kind == "tech_choice":
        from .webcheck import web_evidence

        ev = ev + web_evidence(claim)
    return ev
