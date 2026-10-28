import json
from pathlib import Path

from dledger import llm
from dledger.extract import build_graph, load_messages
from dledger.graph import DecisionGraph
from dledger.pipeline import check
from dledger.schema import Status

SAMPLE = Path(__file__).parent.parent / "data" / "sample"


def sample_graph() -> DecisionGraph:
    return DecisionGraph.load(SAMPLE / "graph.json")


def test_conflict_detected():
    g = sample_graph()
    assert ("d1", "d5") in g.find_conflicts() or ("d5", "d1") in g.find_conflicts()


def test_impact_propagates_through_depends_on():
    g = sample_graph()
    assert g.impact("d1") == ["d3", "d4"]
    assert g.impact("d2") == []


def test_load_bearing_ranks_database_decision_first():
    assert sample_graph().load_bearing(1)[0] == ("d1", 2)


def test_check_flags_stale_decision_and_its_dependents():
    g = sample_graph()
    verdicts = check(g, SAMPLE / "repo", use_llm=False)
    by_id = {v.claim_id: v for v in verdicts}
    assert by_id["d1"].status == Status.CONTRADICTED   # repo moved off Postgres
    assert by_id["d5"].status == Status.VALID          # repo uses MongoDB
    assert g.claim("d3").status == Status.NEEDS_REVIEW  # depended on d1
    assert g.claim("d4").status == Status.NEEDS_REVIEW
    assert g.claim("d2").status == Status.ACTIVE        # untouched


def test_extraction_and_linking_with_fake_model():
    def fake(tier, system, user):
        if tier == llm.Tier.NANO:
            return "```json\n" + json.dumps([
                {"message_id": "m1", "text": "Use PostgreSQL", "subject": "Database",
                 "value": "PostgreSQL", "kind": "tech_choice", "reason": "integrity", "confidence": 0.9},
                {"message_id": "m2", "text": "Use SQLAlchemy", "subject": "ORM",
                 "value": "SQLAlchemy", "kind": "tech_choice", "reason": None, "confidence": 0.8},
            ]) + "\n```"
        return json.dumps([{"src": "c2", "dst": "c1", "type": "depends_on", "confidence": 0.9}])

    llm.set_transport(fake)
    try:
        g = build_graph(load_messages(SAMPLE / "messages.jsonl")[:2])
    finally:
        llm.set_transport(None)
    assert [c.subject for c in g.claims()] == ["database", "orm"]
    assert g.impact("c1") == ["c2"]
    assert g.claim("c1").owner == "maya"


def test_judge_falls_back_when_llm_output_is_garbage():
    g = sample_graph()
    llm.set_transport(lambda t, s, u: "not json at all")
    try:
        verdicts = check(g, SAMPLE / "repo", use_llm=True)
    finally:
        llm.set_transport(None)
    assert {v.claim_id: v.status for v in verdicts}["d1"] == Status.CONTRADICTED
