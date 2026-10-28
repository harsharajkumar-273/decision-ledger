import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest

from dledger import actions, ask, cli, llm
from dledger.connectors import github, jira_export, notion_md, slack_export
from dledger.extract import build_graph
from dledger.graph import DecisionGraph
from dledger.pipeline import check
from dledger.schema import Status

ROOT = Path(__file__).parent.parent / "data"


# ---- connectors -----------------------------------------------------------
def test_slack_export_with_private_channel_acl(tmp_path):
    (tmp_path / "users.json").write_text(json.dumps([{"id": "U1", "real_name": "Maya"}]))
    (tmp_path / "channels.json").write_text(json.dumps([{"name": "eng"}, {"name": "exec", "is_private": True}]))
    for ch, text in (("eng", "We decided to use <@U1>'s plan: Postgres for billing <https://x.io|link>"), ("exec", "Decision: acquire Acme, keep it quiet for now please")):
        d = tmp_path / ch
        d.mkdir()
        (d / "2026-03-04.json").write_text(json.dumps([
            {"user": "U1", "text": text, "ts": "1772600000.000100"},
            {"user": "U1", "text": "joined", "subtype": "channel_join", "ts": "1772600001.0"},
            {"user": "U1", "text": "ok", "ts": "1772600002.0"},
        ]))
    msgs = {m["source"].split("/")[0]: m for m in slack_export.load(tmp_path)}
    assert len(msgs) == 2
    assert msgs["slack:#eng"]["acl"] is None and "@Maya" in msgs["slack:#eng"]["text"]
    assert msgs["slack:#exec"]["acl"] == ["channel:exec"]


def test_jira_json_and_csv(tmp_path):
    (tmp_path / "j.json").write_text(json.dumps({"issues": [{"key": "PLAT-1", "fields": {
        "summary": "Move to MongoDB", "created": "2026-07-19T10:00:00.000+0000", "reporter": {"displayName": "Raj"},
        "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Flexible schema."}]}]}}}]}))
    (tmp_path / "j.csv").write_text("Issue key,Summary,Description,Created,Reporter\nDATA-8,Use window functions,For cohorts,2026-04-02,Li\n")
    a = jira_export.load(tmp_path / "j.json")[0]
    b = jira_export.load(tmp_path / "j.csv")[0]
    assert a["id"] == "jira:PLAT-1" and "Flexible schema" in a["text"] and a["date"] == "2026-07-19"
    assert b["author"] == "Li" and b["source"] == "jira:DATA-8"


def test_github_connector_paginates_and_labels_prs():
    def fake(url):
        if "page=1" in url:
            return [{"number": 1, "title": "Switch to Postgres", "body": "We decided to move billing to Postgres for integrity.",
                     "user": {"login": "maya"}, "created_at": "2026-03-04T00:00:00Z", "html_url": "https://gh/1"},
                    {"number": 2, "title": "tiny", "body": "", "user": {"login": "x"}, "created_at": "2026-03-05T00:00:00Z"}]
        return []
    github.set_getter(fake)
    try:
        out = github.load("acme/app")
    finally:
        github.set_getter(None)
    assert [m["id"] for m in out] == ["github:acme/app#1"] and out[0]["author"] == "maya"


def test_notion_markdown_frontmatter(tmp_path):
    (tmp_path / "adr.md").write_text("---\ndate: 2026-05-01\nauthor: Sam\n---\nWe will use Celery for background jobs because retries matter a lot.")
    m = notion_md.load(tmp_path)[0]
    assert m["date"] == "2026-05-01" and m["author"] == "Sam" and m["text"].startswith("We will use Celery")


# ---- domains / ingest -----------------------------------------------------
def test_ingest_commitments_domain_uses_commitment_prompt():
    seen = {}

    def fake(tier, system, user):
        if tier == llm.Tier.NANO:
            seen["system"] = system
            return json.dumps([{"message_id": "k_m1", "text": "Told Acme SSO by June 30", "subject": "SSO",
                                "value": "2026-06-30", "reason": "security review", "confidence": 0.9}])
        return "[]"

    msgs = [json.loads(l) for l in (ROOT / "commitments" / "messages.jsonl").read_text().splitlines()][:1]
    llm.set_transport(fake)
    try:
        g = build_graph(msgs, domain="commitments")
    finally:
        llm.set_transport(None)
    assert "CUSTOMER COMMITMENTS" in seen["system"]
    assert g.claim("c1").kind == "commitment" and g.claim("c1").subject == "sso"


# ---- permissions ----------------------------------------------------------
def test_private_decisions_never_leak_into_answers_or_warnings():
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    g.claim("d5").acl = ["channel:platform-leads"]          # the MongoDB decision is private
    public = ask.answer(g, "which database do we use", use_llm=False, groups=set())
    blob = json.dumps(public)
    assert "MongoDB" not in blob and "d5" not in blob       # not cited, not named in conflict warnings
    member = ask.answer(g, "which database do we use", use_llm=False, groups={"channel:platform-leads"})
    assert "d5" in json.dumps(member)


# ---- actions --------------------------------------------------------------
def test_slack_summary_and_issue_bodies(monkeypatch):
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    verdicts = check(g, ROOT / "sample" / "repo", use_llm=False)
    sent = []
    actions.set_poster(lambda url, body, headers: sent.append((url, body, headers)) or {"ok": True})
    try:
        actions.notify_slack(g, verdicts, webhook="https://hooks.slack.test/x")
        monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
        actions.open_github_issues(g, verdicts, "acme/app")
    finally:
        actions.set_poster(None)
    assert "no longer hold" in sent[0][1]["text"] and "d1" in sent[0][1]["text"]
    url, body, headers = sent[1]
    assert url.endswith("/repos/acme/app/issues") and "Stale decision" in body["title"]
    assert "pymongo" not in body["body"] and "Decisions that depend on this" in body["body"]
    assert headers["Authorization"] == "Bearer t0ken"


def test_issues_dry_run_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    out = actions.open_github_issues(g, check(g, ROOT / "sample" / "repo", use_llm=False), "acme/app")
    assert out and all(o["dry_run"] for o in out)


# ---- CLI ------------------------------------------------------------------
def test_sweep_cli_fails_on_stale_and_writes_report(tmp_path, capsys):
    rep = tmp_path / "r.json"
    rc = cli.main(["sweep", str(ROOT / "sample" / "graph.json"), "--repo", str(ROOT / "sample" / "repo"),
                   "--no-llm", "--report", str(rep), "--fail-on-stale"])
    assert rc == 1
    r = json.loads(rep.read_text())
    assert r["checked"] == 6 and "d1" in r["failed"]
    assert "6 checked" in capsys.readouterr().out


def test_ask_cli_prints_warning(capsys):
    cli.main(["ask", str(ROOT / "sample" / "graph.json"), "why", "postgres", "--no-llm"])
    assert "conflicts with" in capsys.readouterr().out


# ---- server ---------------------------------------------------------------
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from dledger.server import create_app  # noqa: E402


def client(monkeypatch=None):
    return TestClient(create_app(str(ROOT / "sample" / "graph.json"), str(ROOT / "sample" / "repo")))


def test_server_graph_check_reset_roundtrip(monkeypatch):
    monkeypatch.setenv("DLEDGER_USE_LLM", "0")
    c = client()
    g = c.get("/api/graph").json()
    assert len(g["nodes"]) == 6 and g["conflicts"]
    r = c.post("/api/check", json={}).json()
    assert r["execution"]["mode"] == "rules"
    assert r["execution"]["model_calls"] == 0
    st = {n["id"]: n["status"] for n in r["graph"]["nodes"]}
    assert st["d1"] == "contradicted" and st["d3"] == "needs_review" and st["d2"] == "active"
    assert {v["id"] for v in r["verdicts"]} == {"d1", "d5"}
    full = c.post("/api/check", json={"full": True}).json()
    assert len(full["verdicts"]) == 6
    c.post("/api/reset")
    assert {n["status"] for n in c.get("/api/graph").json()["nodes"]} == {"active"}


def test_server_discloses_model_fallback(monkeypatch):
    monkeypatch.setenv("DLEDGER_USE_LLM", "1")
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    r = client().post("/api/check", json={}).json()
    assert r["execution"]["mode"] == "fallback"
    assert r["execution"]["fallbacks"] == 2


def test_latest_report_keeps_evidence_and_clears_on_reset(monkeypatch):
    monkeypatch.setenv("DLEDGER_USE_LLM", "0")
    c = client()
    initial = c.get("/api/report").json()
    assert initial["checked_at"] is None and initial["verdicts"] == []
    checked = c.post("/api/check", json={}).json()
    restored = c.get("/api/report").json()
    assert restored == checked
    assert restored["checked_at"].endswith("+00:00")
    assert any(e["ref"] == "runtime.json:technologies.database"
               for v in restored["verdicts"] for e in v["evidence"])
    c.post("/api/reset")
    assert c.get("/api/report").json()["execution"] is None


@pytest.mark.parametrize("body", [[], "full", {"full": "false"}, {"web": 1}, {"use_llm": None}])
def test_check_rejects_invalid_options(body):
    assert client().post("/api/check", json=body).status_code == 400


def test_server_ask_impact_ui_health(monkeypatch):
    monkeypatch.setenv("DLEDGER_USE_LLM", "0")
    c = client()
    assert c.get("/healthz").json()["ok"]
    assert "Decision Ledger" in c.get("/").text
    out = c.get("/api/ask", params={"q": "why postgres"}).json()
    assert out["citations"] and out["warnings"]
    assert c.get("/api/impact/d1").json()["impacted"] == ["d3", "d4"]
    assert c.get("/api/impact/nope").status_code == 404


def test_slack_command_signature(monkeypatch):
    monkeypatch.setenv("DLEDGER_USE_LLM", "0")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "shh")
    c = client()
    body = "text=why+postgres&user_id=U1"
    ts = str(int(time.time()))
    sig = "v0=" + hmac.new(b"shh", f"v0:{ts}:{body}".encode(), hashlib.sha256).hexdigest()
    ok = c.post("/slack/command", content=body, headers={"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig,
                                                         "Content-Type": "application/x-www-form-urlencoded"})
    assert ok.status_code == 200 and "Sources" in ok.json()["text"]
    bad = c.post("/slack/command", content=body, headers={"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": "v0=nope"})
    assert bad.status_code == 401
    stale = c.post("/slack/command", content=body, headers={"X-Slack-Request-Timestamp": "1", "X-Slack-Signature": sig})
    assert stale.status_code == 401
