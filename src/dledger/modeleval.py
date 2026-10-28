"""Per-tier model evaluation on hand-labeled seed sets.

  extraction: does the tier find the labeled decisions without inventing any?
  judge:      does the tier reach the labeled verdict from the same evidence?

Run with real Nemotron models (needs NEBIUS_API_KEY and the three model ids):
  dledger eval-models --tiers nano,super,ultra

Token counts and latency come from dledger.llm.USAGE, so the report shows the
cost/accuracy trade-off per tier. The seed sets are small on purpose: they are
meant to be extended, and the harness is the reusable part."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .extract import extract_claims
from .graph import DecisionGraph
from .judge import judge
from .llm import USAGE, Tier
from .llm import chat_json
from .extract import LINK_SYSTEM
from .schema import Claim, Evidence

DATA = Path(__file__).resolve().parents[2] / "data" / "eval"
VALUE_CANON = {"pg": "postgresql", "postgres": "postgresql", "mongo": "mongodb", "elastic": "elasticsearch",
               "rabbit": "rabbitmq", "rabbit mq": "rabbitmq", "open search": "opensearch"}


def _canon(v: str) -> str:
    v = v.lower().strip()
    return VALUE_CANON.get(v, v)


def _load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _usage_snapshot(tier: Tier) -> dict:
    return dict(USAGE[tier.value])


def _usage_delta(before: dict, tier: Tier) -> dict:
    now = USAGE[tier.value]
    return {k: round(now[k] - before[k], 2) for k in now}


def eval_extraction(tier: Tier, data_path: Path | None = None) -> dict:
    rows = _load(data_path or DATA / "extraction_labeled.jsonl")
    msgs = [{k: r[k] for k in ("id", "author", "date", "source", "text")} for r in rows]
    gold = {(r["source"], _canon(g["value"])) for r in rows for g in r["gold"]}
    before, t0 = _usage_snapshot(tier), time.time()
    try:
        claims = extract_claims(msgs, batch=8, tier=tier)
        err = None
    except Exception as exc:  # a tier that cannot produce parseable JSON scores zero, visibly
        claims, err = [], f"{type(exc).__name__}: {exc}"[:160]
    pred = {(c.source, _canon(c.value)) for c in claims}
    tagged = [(row['source'], g) for row in rows for g in row['gold'] if g.get('scope') or g.get('condition')]
    correct_tags = sum(any(c.source == source and _canon(c.value) == _canon(gold['value'])
                           and (not gold.get('scope') or (c.scope or '').lower() == gold['scope'].lower())
                           and (not gold.get('condition') or bool(c.condition)) for c in claims)
                       for source, gold in tagged)
    tp = len(pred & gold)
    p = tp / len(pred) if pred else (1.0 if not gold else 0.0)
    r = tp / len(gold) if gold else 1.0
    return {"precision": round(p, 3), "recall": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "false_positives": sorted(pred - gold), "missed": sorted(gold - pred), "error": err,
            "scope_condition_cases": len(tagged), "scope_condition_recall": round(correct_tags / len(tagged), 3) if tagged else None,
            "usage": _usage_delta(before, tier), "wall_seconds": round(time.time() - t0, 2)}


def _case_graph(case: dict) -> DecisionGraph:
    g = DecisionGraph()
    base = {"owner": None, "source": None, "kind": "tech_choice"}
    g.add_claim(Claim(**{**base, **case["claim"]}))
    for r in case["rivals"]:
        g.add_claim(Claim(**{**base, **r}))
    for i, dep in enumerate(case["dependents"]):
        from .schema import EdgeType

        cid = f"dep{i}"
        g.add_claim(Claim(id=cid, text=dep, subject="dep", value="x"))
        g.add_edge(cid, case["claim"]["id"], EdgeType.DEPENDS_ON)
    return g


def eval_judge(tier: Tier, data_path: Path | None = None) -> dict:
    cases = _load(data_path or DATA / "judge_cases.jsonl")
    before, t0 = _usage_snapshot(tier), time.time()
    right, misses, errors = 0, [], 0
    for c in cases:
        g = _case_graph(c)
        ev = [Evidence(**e) for e in c["evidence"]]
        try:
            got = judge(g, c["claim"]["id"], ev, use_llm=True, tier=tier, strict=True).status.value
        except Exception:
            got, errors = "error", errors + 1
        if got == c["gold"]:
            right += 1
        else:
            misses.append({"id": c["id"], "gold": c["gold"], "got": got})
    return {"accuracy": round(right / len(cases), 3), "n": len(cases), "misses": misses, "errors": errors,
            "usage": _usage_delta(before, tier), "wall_seconds": round(time.time() - t0, 2)}


def run(tiers: list[Tier], tasks: tuple[str, ...] = ("extraction", "judge")) -> dict:
    out: dict = {}
    for t in tiers:
        out[t.value] = {}
        if "extraction" in tasks:
            out[t.value]["extraction"] = eval_extraction(t)
        if "judge" in tasks:
            out[t.value]["judge"] = eval_judge(t)
        if "linking" in tasks:
            out[t.value]["linking"] = eval_linking(t)
    return out


def report(res: dict) -> str:
    rows = ["tier    task        score                 calls  tokens(in/out)   seconds"]
    for tier, tasks in res.items():
        for task, m in tasks.items():
            score = (f"P {m['precision']:.2f} R {m['recall']:.2f} F1 {m['f1']:.2f}" if task in ("extraction", "linking")
                     else f"acc {m['accuracy']:.2f} ({m['n']} cases)")
            u = m["usage"]
            rows.append(f"{tier:<7} {task:<11} {score:<21} {int(u['calls']):>5}  "
                        f"{int(u['prompt_tokens'])}/{int(u['completion_tokens'])}".ljust(52) + f"{m['wall_seconds']:>6}")
    return "\n".join(rows)


def eval_linking(tier: Tier) -> dict:
    cases = _load(DATA / 'linking_labeled.jsonl')
    before, started = _usage_snapshot(tier), time.time()
    tp = predicted = expected = errors = 0
    misses = []
    for case in cases:
        def signature(edge):
            a, b = edge['src'], edge['dst']
            if edge['type'] == 'contradicts':
                a, b = sorted((a, b))
            return a, b, edge['type']
        gold = {signature(e) for e in case['edges']}
        expected += len(gold)
        try:
            out = chat_json(tier, LINK_SYSTEM, json.dumps(case['claims']))
            pred = {signature(e) for e in out}
        except Exception:
            pred = set()
            errors += 1
        tp += len(pred & gold)
        predicted += len(pred)
        if pred != gold:
            misses.append({'id': case['id'], 'missed': sorted(gold - pred), 'invented': sorted(pred - gold)})
    precision = tp / predicted if predicted else 0.0
    recall = tp / expected if expected else 1.0
    return {'precision': round(precision, 3), 'recall': round(recall, 3),
            'f1': round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0,
            'errors': errors, 'n': len(cases), 'misses': misses,
            'usage': _usage_delta(before, tier), 'wall_seconds': round(time.time() - started, 2)}
