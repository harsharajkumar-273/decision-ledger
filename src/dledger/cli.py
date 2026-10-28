from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .graph import DecisionGraph
from .pipeline import check


def _dotenv() -> None:
    p = Path(".env")
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def _print_verdicts(g: DecisionGraph, verdicts) -> None:
    for v in verdicts:
        c = g.claim(v.claim_id)
        print(f"[{v.status.value.upper():12}] {c.id}: {c.text}")
        print(f"    {v.rationale}")
        for e in v.evidence:
            print(f"    - {e.detail}" + (f"  ({e.ref})" if e.ref else ""))
        if v.impacted and v.status.value in ("contradicted", "stale"):
            print(f"    impacted: {', '.join(v.impacted)}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="dledger", description="Self-verifying graph of team decisions")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("connect", help="turn a source into messages.jsonl")
    p.add_argument("source", choices=["slack", "jira", "github", "notion"])
    p.add_argument("target", help="export dir/file, or owner/name for github")
    p.add_argument("--out", default="messages.jsonl")
    p.add_argument("--max", type=int, default=200, help="github: max items")
    p.add_argument("--comments", action="store_true", help="github: include comments")

    p = sub.add_parser("ingest", help="messages.jsonl -> graph.json (uses Nemotron)")
    p.add_argument("messages")
    p.add_argument("--out", default="graph.json")
    p.add_argument("--domain", default="engineering", choices=["engineering", "commitments"])

    p = sub.add_parser("check", help="verify candidate decisions against a repo")
    p.add_argument("graph")
    p.add_argument("--repo", required=True)
    p.add_argument("--no-llm", action="store_true", help="rule-based verdicts only")
    p.add_argument("--web", action="store_true", help="add Tavily web checks (needs TAVILY_API_KEY)")
    p.add_argument("--save", help="write updated graph here")

    p = sub.add_parser("sweep", help="verify EVERY decision (the nightly job)")
    p.add_argument("graph")
    p.add_argument("--repo", required=True)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--web", action="store_true")
    p.add_argument("--save", help="write updated graph here")
    p.add_argument("--report", help="write JSON report here")
    p.add_argument("--slack", action="store_true", help="post a summary to SLACK_WEBHOOK_URL")
    p.add_argument("--issues", metavar="OWNER/REPO", help="open a GitHub issue per failed decision")
    p.add_argument("--dry-run", action="store_true", help="print issues instead of creating them")
    p.add_argument("--fail-on-stale", action="store_true", help="exit 1 if any decision failed")

    p = sub.add_parser("ask", help="why did we decide X?")
    p.add_argument("graph")
    p.add_argument("question", nargs="+")
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--groups", help="comma-separated groups the asker belongs to (default: admin view)")

    p = sub.add_parser("impact", help="what depends on this decision?")
    p.add_argument("graph")
    p.add_argument("claim_id")

    p = sub.add_parser("why", help="show decisions about a subject")
    p.add_argument("graph")
    p.add_argument("subject")

    p = sub.add_parser("serve", help="web UI + API + Slack command")
    p.add_argument("graph")
    p.add_argument("--repo", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)

    p = sub.add_parser("eval-models", help="score Nemotron tiers on labeled extraction and verdict sets (needs API key)")
    p.add_argument("--tiers", default="nano,super,ultra")
    p.add_argument("--task", default="both", choices=["extraction", "judge", "linking", "both", "all"])
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", help="save JSON metrics, tokens and latency")

    p = sub.add_parser("doctor", help="credential-safe model readiness check")
    p.add_argument("--live", action="store_true", help="make one real probe per configured model")
    p.add_argument("--out", help="save readiness JSON")

    p = sub.add_parser("benchmark", help="adversarial repository evidence tests and ablations")
    p.add_argument("--models", action="store_true", help="also run live Nemotron graph and RAG judges")
    p.add_argument("--out", help="save all case predictions and evidence")

    p = sub.add_parser("resolve", help="record a reviewed or superseded decision with an audit trail")
    p.add_argument("graph")
    p.add_argument("claim_id")
    p.add_argument("--action", required=True, choices=["supersede", "review"])
    p.add_argument("--target", help="existing replacement decision")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--note", required=True)

    p = sub.add_parser("eval", help="run the synthetic evaluation (no API key needed)")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--json", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    _dotenv()
    a = build_parser().parse_args(argv)

    if a.cmd == "doctor":
        from .readiness import run
        result = run(a.live)
        if a.out:
            Path(a.out).write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 0 if result["live_verified" if a.live else "configured"] else 2

    if a.cmd == "benchmark":
        from . import benchmark, readiness
        if a.models and not readiness.run()["configured"]:
            print("Configure the Nebius key and model IDs before requesting live benchmarks.", file=sys.stderr)
            return 2
        result = benchmark.run(a.models)
        if a.out:
            Path(a.out).write_text(json.dumps(result, indent=2))
        print(json.dumps(result["summary"], indent=2))
        return 0

    if a.cmd == "eval":
        from . import evalkit

        res = evalkit.run(a.n, a.seed)
        print(json.dumps(res, indent=2) if a.json else evalkit.report(res))
        return 0

    if a.cmd == "eval-models":
        from . import modeleval
        from .llm import Tier

        if not os.getenv("NEBIUS_API_KEY"):
            print("eval-models calls the real models: set NEBIUS_API_KEY and DLEDGER_MODEL_NANO/SUPER/ULTRA "
                  "(see .env.example).", file=sys.stderr)
            return 2
        tasks = ("extraction", "judge", "linking") if a.task == "all" else ("extraction", "judge") if a.task == "both" else (a.task,)
        res = modeleval.run([Tier(t.strip()) for t in a.tiers.split(",")], tasks)
        if a.out:
            Path(a.out).write_text(json.dumps(res, indent=2))
        print(json.dumps(res, indent=2) if a.json else modeleval.report(res))
        return 0

    if a.cmd == "connect":
        from .connectors import write_jsonl

        if a.source == "slack":
            from .connectors import slack_export as mod
            msgs = mod.load(a.target)
        elif a.source == "jira":
            from .connectors import jira_export as mod
            msgs = mod.load(a.target)
        elif a.source == "notion":
            from .connectors import notion_md as mod
            msgs = mod.load(a.target)
        else:
            from .connectors import github as mod
            msgs = mod.load(a.target, max_items=a.max, with_comments=a.comments)
        print(f"{write_jsonl(msgs, a.out)} messages -> {a.out}")
        return 0

    if a.cmd == "ingest":
        from .extract import build_graph, load_messages

        g = build_graph(load_messages(a.messages), domain=a.domain)
        g.save(a.out)
        print(f"{len(g.claims())} claims -> {a.out}")
        return 0

    if a.cmd == "serve":
        import uvicorn

        from .server import create_app

        uvicorn.run(create_app(a.graph, a.repo), host=a.host, port=a.port)
        return 0

    g = DecisionGraph.load(a.graph)

    if a.cmd == "resolve":
        from .workflow import resolve
        try:
            event = resolve(g, a.claim_id, a.action, a.reviewer, a.note, a.target)
        except (ValueError, KeyError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        g.save(a.graph)
        print(json.dumps(event, indent=2))
        return 0

    if a.cmd == "check":
        verdicts = check(g, a.repo, use_llm=not a.no_llm, web=a.web)
        _print_verdicts(g, verdicts)
        if a.save:
            g.save(a.save)

    elif a.cmd == "sweep":
        from . import actions

        ids = [c.id for c in g.claims()]
        verdicts = check(g, a.repo, use_llm=not a.no_llm, web=a.web, ids=ids)
        _print_verdicts(g, verdicts)
        bad = actions.failed(verdicts)
        if a.save:
            g.save(a.save)
        if a.report:
            Path(a.report).write_text(json.dumps(
                {"checked": len(verdicts), "failed": [v.claim_id for v in bad],
                 "verdicts": [{"id": v.claim_id, "status": v.status.value, "rationale": v.rationale,
                               "impacted": v.impacted} for v in verdicts]}, indent=2))
        if a.slack:
            actions.notify_slack(g, verdicts)
        if a.issues:
            for it in actions.open_github_issues(g, verdicts, a.issues, dry_run=a.dry_run):
                print("ISSUE:", it.get("title") or it.get("html_url"))
        print(f"\n{len(verdicts)} checked, {len(bad)} failed")
        return 1 if (a.fail_on_stale and bad) else 0

    elif a.cmd == "ask":
        from . import ask as askmod

        groups = set(a.groups.split(",")) if a.groups else None
        out = askmod.answer(g, " ".join(a.question), use_llm=not a.no_llm, groups=groups)
        print(out["answer"])
        for w in out["warnings"]:
            print(f"  ! {w}")
        for c in out["citations"]:
            print(f"  - {c['id']} [{c['status']}] {c['date']} {c['owner']} ({c['source']})")

    elif a.cmd == "impact":
        for cid in g.impact(a.claim_id):
            print(f"{cid}: {g.claim(cid).text}")

    elif a.cmd == "why":
        for c in g.claims():
            if c.subject == a.subject.lower():
                print(f"{c.id} [{c.status.value}] {c.date} {c.owner}: {c.text}")
                if c.reason:
                    print(f"    why: {c.reason}")
                print(f"    source: {c.source}; current: {g.current(c.id)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
