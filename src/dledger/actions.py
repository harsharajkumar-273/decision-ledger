"""Outbound actions: Slack summary and GitHub issues for decisions that failed."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable, Optional

from .graph import DecisionGraph
from .schema import Status, Verdict

Poster = Callable[[str, dict, dict], object]
_poster: Optional[Poster] = None


def set_poster(fn: Optional[Poster]) -> None:
    global _poster
    _poster = fn


def _post(url: str, body: dict, headers: dict | None = None):
    headers = {"Content-Type": "application/json", "User-Agent": "decision-ledger", **(headers or {})}
    if _poster is not None:
        return _poster(url, body, headers)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        return json.loads(raw) if raw and raw[:1] in b"[{" else raw


def failed(verdicts: list[Verdict]) -> list[Verdict]:
    return [v for v in verdicts if v.status in (Status.CONTRADICTED, Status.STALE)]


def summary_text(graph: DecisionGraph, verdicts: list[Verdict]) -> str:
    bad = failed(verdicts)
    if not bad:
        return f"Decision Ledger: {len(verdicts)} decisions checked, none stale."
    lines = [f"Decision Ledger: {len(bad)} of {len(verdicts)} checked decisions no longer hold."]
    for v in bad:
        c = graph.claim(v.claim_id)
        dep = f" ({len(v.impacted)} depend on it)" if v.impacted else ""
        lines.append(f"- {c.id} {c.text}{dep}: {v.rationale}")
    return "\n".join(lines)


def notify_slack(graph: DecisionGraph, verdicts: list[Verdict], webhook: str | None = None):
    url = webhook or os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        return None
    return _post(url, {"text": summary_text(graph, verdicts)})


def open_github_issues(graph: DecisionGraph, verdicts: list[Verdict], repo: str, dry_run: bool = False) -> list[dict]:
    """One issue per failed decision. Needs GITHUB_TOKEN with issues:write."""
    token = os.getenv("GITHUB_TOKEN")
    created = []
    for v in failed(verdicts):
        c = graph.claim(v.claim_id)
        title = f"[decision-ledger] Stale decision: {c.text}"[:240]
        body = (
            f"**Decision** ({c.id}, {c.date}, {c.owner}): {c.text}\n"
            f"**Source:** {c.source}\n**Why it was made:** {c.reason or 'not recorded'}\n\n"
            f"**Verdict:** {v.status.value}. {v.rationale}\n\n**Evidence**\n"
            + "\n".join(f"- {e.detail}" + (f" (`{e.ref}`)" if e.ref else "") for e in v.evidence)
            + (f"\n\n**Decisions that depend on this:** {', '.join(v.impacted)}" if v.impacted else "")
        )
        if dry_run or not token:
            created.append({"title": title, "body": body, "dry_run": True})
            continue
        created.append(
            _post(f"https://api.github.com/repos/{repo}/issues", {"title": title, "body": body},
                  {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        )
    return created


def issue_drafts(graph: DecisionGraph, verdicts: list[Verdict]) -> list[dict]:
    """Local, evidence-based follow-up drafts. Nothing is posted."""
    drafts = []
    for v in failed(verdicts):
        c = graph.claim(v.claim_id)
        if c.status not in (Status.CONTRADICTED, Status.STALE):
            continue
        affected = [graph.claim(i) for i in v.impacted]
        owners = sorted({x.owner for x in [c] + affected if x.owner})
        drafts.append({'decision_id': c.id, 'title': f'Review changed decision: {c.text}', 'owners': owners,
                       'body': f'## Decision\n{c.text}\nSource: {c.source}\n\n## Evidence\n' +
                       '\n'.join(f'- {e.detail} ({e.ref or "no reference"})' for e in v.evidence) +
                       '\n\n## Affected work\n' + '\n'.join(f'- {x.text} — owner: {x.owner or "unassigned"}' for x in affected) +
                       '\n\n## Next steps\n- Confirm which configuration applies.\n- Record a replacement decision if appropriate.' +
                       '\n- Review each dependent decision with its owner.\n- Recheck after updating the code.',
                       'published': False})
    return drafts
