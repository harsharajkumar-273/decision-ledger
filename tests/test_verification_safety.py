import json

from dledger import llm
from dledger.graph import DecisionGraph
from dledger.judge import judge, rule_verdict
from dledger.schema import Claim, Evidence, Status
from dledger.verify import verify_tech_choice


def decision():
    return Claim("db", "Use Postgres for the primary database", "database", "postgresql")


def test_missing_driver_is_uncertain_even_when_another_driver_exists(tmp_path):
    (tmp_path / "requirements.txt").write_text("pymongo==4.8\n")
    ev = verify_tech_choice(decision(), tmp_path)
    assert rule_verdict("db", ev)[0] == Status.NEEDS_REVIEW


def test_explicit_configuration_overrides_leftover_dependencies(tmp_path):
    (tmp_path / "requirements.txt").write_text("psycopg2-binary==2.9\npymongo==4.8\n")
    (tmp_path / "runtime.json").write_text(json.dumps({"technologies": {"database": "mongodb"}}))
    ev = verify_tech_choice(decision(), tmp_path)
    assert rule_verdict("db", ev)[0] == Status.CONTRADICTED
    assert ev[0].ref == "runtime.json:technologies.database"


def test_config_aliases_and_invalid_snapshots(tmp_path):
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps({"technologies": {"database": "postgres"}}))
    assert verify_tech_choice(decision(), tmp_path)[0].supports is True
    path.write_text("invalid json")
    assert verify_tech_choice(decision(), tmp_path)[0].supports is None


def test_configuration_does_not_leak_unrelated_secrets(tmp_path):
    (tmp_path / "runtime.json").write_text(json.dumps({
        "technologies": {"database": "mongodb"}, "password": "do-not-expose-me"}))
    assert "do-not-expose-me" not in str(verify_tech_choice(decision(), tmp_path))


def test_model_cannot_invent_failure_or_validity_from_missing_evidence():
    g = DecisionGraph()
    g.add_claim(decision())
    try:
        for status in ("contradicted", "stale", "valid"):
            llm.set_transport(lambda *args: json.dumps({"status": status, "rationale": "guess"}))
            verdict = judge(g, "db", [Evidence("repo", "No manifest files", None)])
            assert verdict.status == Status.NEEDS_REVIEW
    finally:
        llm.set_transport(None)
