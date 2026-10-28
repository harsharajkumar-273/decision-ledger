import json

from dledger import llm, modeleval
from dledger.llm import Tier


def _oracle(tier, system, user):
    """A perfect fake model: reads the labeled sets and answers from the gold."""
    if "extract" in system.lower() and "DECISIONS" in system:
        msgs = json.loads(user)
        gold = {r["text"][:30]: r for r in modeleval._load(modeleval.DATA / "extraction_labeled.jsonl")}
        out = []
        for m in msgs:
            row = gold[m["text"][:30]]
            out += [{"message_id": m["id"], "text": "d", "subject": g["subject"], "value": g["value"], "scope": g.get("scope"), "condition": g.get("condition"), "confidence": 0.9}
                    for g in row["gold"]]
        return json.dumps(out)
    payload = json.loads(user)
    def key(text, ev, rivals):
        return text + "|" + "|".join(e["detail"] for e in ev) + "|" + str(len(rivals))

    cases = {key(c["claim"]["text"], c["evidence"], c["rivals"]): c
             for c in modeleval._load(modeleval.DATA / "judge_cases.jsonl")}
    k = key(payload["decision"]["text"], payload["evidence"], payload["competing_decisions"])
    return json.dumps({"status": cases[k]["gold"], "rationale": "oracle"})


def test_datasets_are_well_formed():
    ext = modeleval._load(modeleval.DATA / "extraction_labeled.jsonl")
    assert len(ext) >= 16 and len({r["source"] for r in ext}) == len(ext)
    assert any(not r["gold"] for r in ext) and any(r["gold"] for r in ext)
    cases = modeleval._load(modeleval.DATA / "judge_cases.jsonl")
    assert {c["gold"] for c in cases} >= {"valid", "contradicted", "needs_review"}


def test_perfect_model_scores_perfectly():
    llm.set_transport(_oracle)
    try:
        res = modeleval.run([Tier.NANO])
    finally:
        llm.set_transport(None)
    assert res["nano"]["extraction"]["f1"] == 1.0 and res["nano"]["extraction"]["false_positives"] == []
    assert res["nano"]["judge"]["accuracy"] == 1.0
    assert "nano" in modeleval.report(res)


def test_hallucinating_and_broken_models_are_penalised():
    llm.set_transport(lambda t, s, u: json.dumps([{"message_id": "e6", "text": "x", "subject": "database", "value": "oracle"}])
                      if "DECISIONS" in s else "garbage")
    try:
        res = modeleval.run([Tier.SUPER])
    finally:
        llm.set_transport(None)
    ex, jd = res["super"]["extraction"], res["super"]["judge"]
    assert ex["precision"] < 1.0 and ex["recall"] < 1.0 and ex["false_positives"]
    assert jd["accuracy"] == 0.0 and jd["errors"] == jd["n"]    # strict mode: no silent rule fallback


def test_extraction_error_scores_zero_not_crash():
    llm.set_transport(lambda t, s, u: "not json")
    try:
        ex = modeleval.eval_extraction(Tier.NANO)
    finally:
        llm.set_transport(None)
    assert ex["recall"] == 0.0 and ex["error"]
