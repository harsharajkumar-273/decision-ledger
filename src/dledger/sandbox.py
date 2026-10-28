"""Run verifiers in isolation.

Default is in-process (local). Set DLEDGER_SANDBOX_CMD to run each verification
as a separate, secret-free subprocess, for example under an OpenShell/NemoClaw
sandbox with a read-only mount of the repo:

  DLEDGER_SANDBOX_CMD='openshell run -- {python} -m dledger.sandbox_worker {repo}'

Placeholders: {python} the interpreter, {repo} the repo path. Check the
OpenShell/NemoClaw docs for the exact wrapper syntax on your install. The
worker reads one claim as JSON on stdin and prints a JSON list of evidence.
The child gets a scrubbed environment (no API keys)."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from .schema import Claim, Evidence
from .verify import verify

SAFE_ENV = ("PATH", "HOME", "LANG", "PYTHONPATH", "VIRTUAL_ENV", "DLEDGER_AS_OF")


def run_verifier(claim: Claim, repo: str | Path | None, web: bool = False, timeout: int = 60) -> list[Evidence]:
    template = os.getenv("DLEDGER_SANDBOX_CMD")
    if not template or repo is None:
        return verify(claim, repo, web=web)
    cmd = shlex.split(template.format(python=sys.executable, repo=str(repo)))
    env = {k: v for k, v in os.environ.items() if k in SAFE_ENV}
    try:
        out = subprocess.run(
            cmd, input=json.dumps(claim.to_dict()), capture_output=True, text=True, timeout=timeout, env=env
        )
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip()[:200] or f"exit {out.returncode}")
        ev = [Evidence(**e) for e in json.loads(out.stdout)]
    except Exception as exc:
        ev = [Evidence("repo", f"sandboxed verifier failed: {type(exc).__name__}: {exc}"[:240], None)]
    if web and claim.kind == "tech_choice":
        # web access happens in the trusted parent, never inside the sandbox
        from .webcheck import web_evidence

        ev += web_evidence(claim)
    return ev
