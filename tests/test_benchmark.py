import json

from dledger import benchmark, cli, llm, modeleval, readiness
from dledger.graph import DecisionGraph
from dledger.schema import Claim
from dledger.verify import verify


def test_adversarial_benchmark_includes_uncertainty_and_no_model_claims():
    report = benchmark.run()
    assert report['n'] == 16
    assert report['models_requested'] is False
    assert report['summary']['evidence_rules']['false_contradictions'] == 0
    assert any(c['gold'] == 'needs_review' for c in report['cases'])
    assert 'nemotron_rag_baseline' not in report['summary']


def test_readiness_does_not_expose_credentials(monkeypatch):
    monkeypatch.setenv('NEBIUS_API_KEY', 'private-key-do-not-print')
    for tier in llm.Tier:
        monkeypatch.setenv('DLEDGER_MODEL_' + tier.value.upper(), 'model-' + tier.value)
    llm.set_transport(lambda *args: '{"ok":true}')
    try:
        result = readiness.run(live=True)
    finally:
        llm.set_transport(None)
    assert result['live_verified']
    assert 'private-key-do-not-print' not in json.dumps(result)


def test_linking_metrics_penalize_invented_edges():
    llm.set_transport(lambda *args: '[{"src":"fiction","dst":"invented","type":"supersedes"}]')
    try:
        result = modeleval.eval_linking(llm.Tier.SUPER)
    finally:
        llm.set_transport(None)
    assert result['precision'] == 0 and result['recall'] == 0
    assert result['misses']


def test_environment_scopes_do_not_create_false_conflicts():
    g = DecisionGraph()
    g.add_claim(Claim('local', 'Use SQLite locally', 'database', 'sqlite', scope='development'))
    g.add_claim(Claim('prod', 'Use Postgres in production', 'database', 'postgresql', scope='production'))
    assert not g.find_conflicts()


def test_conditions_are_not_silently_treated_as_met(tmp_path):
    c = Claim('conditional', 'Use MongoDB after approval', 'database', 'mongodb', condition='security approval')
    (tmp_path / '.env.example').write_text('DATABASE_URL=mongodb://db/app')
    assert verify(c, tmp_path)[0].supports is None


def test_extraction_rejects_unattributed_model_claims():
    import pytest
    from dledger.extract import extract_claims
    llm.set_transport(lambda *args: '[{"message_id":"unknown","text":"Invented decision","subject":"database","value":"oracle"}]')
    try:
        with pytest.raises(ValueError):
            extract_claims([{'id':'real','text':'We have not decided.'}])
    finally:
        llm.set_transport(None)
