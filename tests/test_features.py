import json
from pathlib import Path

from dledger import ask, llm, webcheck
from dledger.graph import DecisionGraph
from dledger.pipeline import check
from dledger.schema import Status

ROOT = Path(__file__).parent.parent / "data"


def test_commitments_domain_same_engine(monkeypatch):
    monkeypatch.setenv("DLEDGER_AS_OF", "2026-10-08")
    g = DecisionGraph.load(ROOT / "commitments" / "graph.json")
    v = {x.claim_id: x for x in check(g, ROOT / "commitments", use_llm=False, ids=["k1", "k2", "k3", "k4"])}
    assert v["k1"].status == Status.CONTRADICTED          # eta after the promised date
    assert v["k2"].status == Status.VALID                  # shipped on time
    assert v["k4"].status == Status.VALID
    assert g.claim("k3").status == Status.NEEDS_REVIEW     # depends on SSO, not on roadmap


def test_graph_guided_flags_dependent_commitment(monkeypatch):
    monkeypatch.setenv("DLEDGER_AS_OF", "2026-10-08")
    g = DecisionGraph.load(ROOT / "commitments" / "graph.json")
    check(g, ROOT / "commitments", use_llm=False)
    assert g.claim("k1").status == Status.CONTRADICTED
    assert g.claim("k3").status == Status.NEEDS_REVIEW


def test_web_signal_turns_clean_repo_into_needs_review():
    webcheck.set_fetcher(lambda q: [{"title": "Celery 5 end of life announced", "url": "https://example.com/x",
                                     "content": "The celery project says celery 4 is end of life and unmaintained."}])
    try:
        g = DecisionGraph.load(ROOT / "sample" / "graph.json")
        v = {x.claim_id: x for x in check(g, ROOT / "sample" / "repo", use_llm=False, ids=["d6"], web=True)}
    finally:
        webcheck.set_fetcher(None)
    assert v["d6"].status == Status.NEEDS_REVIEW           # repo says yes, web says maybe not
    assert any(e.kind == "web" and e.supports is False for e in v["d6"].evidence)


def test_web_check_is_neutral_when_nothing_found():
    webcheck.set_fetcher(lambda q: [{"title": "Celery docs", "content": "Celery is a task queue.", "url": "u"}])
    try:
        g = DecisionGraph.load(ROOT / "sample" / "graph.json")
        v = check(g, ROOT / "sample" / "repo", use_llm=False, ids=["d6"], web=True)[0]
    finally:
        webcheck.set_fetcher(None)
    assert v.status == Status.VALID


def test_sandbox_subprocess_protocol(monkeypatch):
    monkeypatch.setenv("DLEDGER_SANDBOX_CMD", "{python} -m dledger.sandbox_worker {repo}")
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parent.parent / "src"))
    monkeypatch.setenv("NEBIUS_API_KEY", "secret-should-not-leak")
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    v = {x.claim_id: x for x in check(g, ROOT / "sample" / "repo", use_llm=False)}
    assert v["d1"].status == Status.CONTRADICTED and v["d5"].status == Status.VALID


def test_sandbox_failure_degrades_to_needs_review(monkeypatch):
    monkeypatch.setenv("DLEDGER_SANDBOX_CMD", "{python} -c 'import sys; sys.exit(3)' {repo}")
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    v = check(g, ROOT / "sample" / "repo", use_llm=False, ids=["d1"])[0]
    assert v.status == Status.NEEDS_REVIEW


def test_ask_warns_about_conflict_and_cites_sources():
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    out = ask.answer(g, "why do we use postgres as our database?", use_llm=False)
    assert out["citations"][0]["id"] in {"d1", "d5"}
    assert any("conflicts with" in w for w in out["warnings"])


def test_ask_after_check_says_contradicted():
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    check(g, ROOT / "sample" / "repo", use_llm=False)
    out = ask.answer(g, "why did we pick postgres?", use_llm=False)
    assert any("contradicted" in w for w in out["warnings"])
    assert any("depend on d1" in w for w in out["warnings"])


def test_review_overview_uses_status_and_respects_permissions():
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    check(g, ROOT / "sample" / "repo", use_llm=False)
    g.claim("d4").acl = ["channel:reporting"]
    public = ask.answer(g, "Which decisions need review?", use_llm=False, groups=set())
    assert {c["id"] for c in public["citations"]} == {"d3"}
    assert "1 visible decision" in public["answer"]
    assert "d4" not in json.dumps(public)
    admin = ask.answer(g, "What needs review?", use_llm=False)
    assert {c["id"] for c in admin["citations"]} == {"d3", "d4"}


def test_review_overview_does_not_claim_unchecked_decisions_are_safe():
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    out = ask.answer(g, "What needs review?", use_llm=False)
    assert not out["citations"]
    assert "Unchecked decisions have not been verified" in out["answer"]


def test_ask_llm_answer_used_and_fallback(monkeypatch):
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    llm.set_transport(lambda t, s, u: "Postgres was chosen for billing integrity [d1].")
    try:
        assert "integrity" in ask.answer(g, "why postgres", use_llm=True)["answer"]
    finally:
        llm.set_transport(None)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    assert ask.answer(g, "why postgres", use_llm=True)["answer"].startswith("[")  # falls back, no crash


def test_semantic_retrieval_blends_with_lexical():
    g = DecisionGraph.load(ROOT / "sample" / "graph.json")
    # fake embedder: puts the query closest to the cache decision
    def fake(texts):
        return [[1.0, 0.0] if ("session" in t or t == texts[0]) else [0.0, 1.0] for t in texts]

    ask.set_embedder(fake)
    try:
        hits = ask.retrieve(g, "where do user sessions live", k=2)
    finally:
        ask.set_embedder(None)
    assert hits and hits[0].id == "d2"
