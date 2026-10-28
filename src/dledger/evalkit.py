"""Evaluation harness.

Generates labeled scenarios (claims + graph + a repo snapshot with known ground
truth) and compares three verification strategies at different cost:

  full_sweep    verify every claim (upper bound on recall, highest cost)
  graph_guided  verify only graph-selected candidates (our approach)
  random_budget verify a random subset the same size as graph_guided (ablation)

Scored with the deterministic rule verifier, so differences reflect the
strategy, not LLM noise. The same harness takes real labeled data later and
can swap in Nemotron verdicts per tier.
"""
from __future__ import annotations

import json
import random
import tempfile
from collections import defaultdict
from pathlib import Path

from .graph import DecisionGraph
from .pipeline import candidates, check
from .schema import Claim, EdgeType, Status

# subject -> {value: line written into requirements.txt}
POOL: dict[str, dict[str, str]] = {
    "database": {"postgresql": "psycopg2-binary==2.9", "mongodb": "pymongo==4.8", "mysql": "pymysql==1.1"},
    "queue": {"celery": "celery==5.4", "kafka": "kafka-python==2.0", "rabbitmq": "pika==1.3"},
    "cache": {"redis": "redis==5.0", "memcached": "memcached==1.59"},
    "search": {"elasticsearch": "elasticsearch==8.14", "opensearch": "opensearch-py==2.6", "meilisearch": "meilisearch==0.31"},
}
STABLE_LIBS = ["fastapi", "pydantic", "uvicorn", "httpx", "orjson"]  # always present in the repo


class Scenario:
    def __init__(self, graph: DecisionGraph, repo_lines: list[str], gold: dict, scored: set[str], dependents: set[str]):
        self.graph, self.repo_lines, self.gold, self.scored, self.dependents = graph, repo_lines, gold, scored, dependents


def make_scenario(rng: random.Random) -> Scenario:
    g = DecisionGraph()
    repo = [f"{lib}==1.0" for lib in STABLE_LIBS]
    present: set[str] = set()
    excluded: set[str] = set()       # superseded-old claims are not scored
    n = 0
    subj_claims: list[tuple[str, str]] = []  # (claim id of the older claim, subject)

    def new(subject: str, value: str, date: str, kind: str = "tech_choice") -> str:
        nonlocal n
        n += 1
        cid = f"c{n}"
        g.add_claim(Claim(id=cid, text=f"Use {value} for {subject}", subject=subject, value=value, kind=kind, date=date))
        return cid

    for subject in rng.sample(list(POOL), k=rng.randint(3, 4)):
        values = list(POOL[subject])
        a, b = rng.sample(values, 2)
        mode = rng.choices(["ok", "silent_drift", "conflict_open", "superseded"], [0.4, 0.2, 0.2, 0.2])[0]
        old = new(subject, a, "2026-01-10")
        subj_claims.append((old, subject))
        if mode == "ok":
            present.add(a)
        elif mode == "silent_drift":
            present.add(b)                      # repo moved, nobody wrote it down
        elif mode == "conflict_open":
            new(subject, b, "2026-06-10")
            present.add(b if rng.random() > 0.3 else a)
        else:  # superseded
            nxt = new(subject, b, "2026-06-10")
            g.add_edge(nxt, old, EdgeType.SUPERSEDES)
            excluded.add(old)
            present.add(b)

    dependents: set[str] = set()
    for old, subject in subj_claims:
        if rng.random() < 0.5:
            for _ in range(rng.randint(1, 2)):
                lib = rng.choice(STABLE_LIBS)
                dep = new(f"uses-{subject}", lib, "2026-02-01")
                g.add_edge(dep, old, EdgeType.DEPENDS_ON)
                dependents.add(dep)

    repo += [POOL[s][v] for s in POOL for v in POOL[s] if v in present]

    # gold labels
    gold_contra = {
        c.id for c in g.claims()
        if c.id not in excluded and c.subject in POOL and c.value not in present
    }
    gold_review = {d for d in dependents if any(g.claim(a).id in gold_contra for a in _deps_of(g, d))}
    scored = {c.id for c in g.claims()} - excluded
    return Scenario(g, repo, {"contradicted": gold_contra, "needs_review": gold_review}, scored, dependents)


def _deps_of(g: DecisionGraph, cid: str) -> list[str]:
    return [v for u, v, d in g.g.edges(data=True) if u == cid and d["etype"] == EdgeType.DEPENDS_ON.value]


def _prf(pred: set[str], gold: set[str]) -> tuple[float, float, float]:
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 1.0
    r = tp / len(gold) if gold else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def run(n: int = 200, seed: int = 0) -> dict:
    rng = random.Random(seed)
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for _ in range(n):
        sc = make_scenario(rng)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "requirements.txt").write_text("\n".join(sc.repo_lines))
            # Synthetic application settings provide explicit contrary evidence;
            # absence from requirements alone is deliberately inconclusive.
            technologies = {s: v for s, choices in POOL.items() for v, line in choices.items()
                            if line in sc.repo_lines}
            (Path(tmp) / "runtime.json").write_text(json.dumps({"technologies": technologies}))
            guided_ids = candidates(sc.graph)
            budget = len(guided_ids)
            strategies = {
                "full_sweep": [c.id for c in sc.graph.claims()],
                "graph_guided": guided_ids,
                "random_budget": rng.sample([c.id for c in sc.graph.claims()], min(budget, len(sc.graph.claims()))),
            }
            for name, ids in strategies.items():
                g = DecisionGraph()
                for c in sc.graph.claims():
                    g.add_claim(Claim.from_dict(c.to_dict()))
                for u, v, d in sc.graph.g.edges(data=True):
                    g.add_edge(u, v, EdgeType(d["etype"]))
                check(g, tmp, use_llm=False, ids=ids)
                pred_c = {c.id for c in g.claims() if c.status == Status.CONTRADICTED and c.id in sc.scored}
                pred_r = {c.id for c in g.claims() if c.status == Status.NEEDS_REVIEW and c.id in sc.dependents}
                t = totals[name]
                t["verifications"] += len(ids)
                t["stale_tp"] += len(pred_c & sc.gold["contradicted"])
                t["stale_pred"] += len(pred_c)
                t["stale_gold"] += len(sc.gold["contradicted"])
                t["dep_tp"] += len(pred_r & sc.gold["needs_review"])
                t["dep_pred"] += len(pred_r)
                t["dep_gold"] += len(sc.gold["needs_review"])
    out = {}
    for name, t in totals.items():
        p = t["stale_tp"] / t["stale_pred"] if t["stale_pred"] else 1.0
        r = t["stale_tp"] / t["stale_gold"] if t["stale_gold"] else 1.0
        dp = t["dep_tp"] / t["dep_pred"] if t["dep_pred"] else 1.0
        dr = t["dep_tp"] / t["dep_gold"] if t["dep_gold"] else 1.0
        out[name] = {
            "verifications": int(t["verifications"]),
            "stale_precision": round(p, 3), "stale_recall": round(r, 3),
            "stale_f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "dependent_recall": round(dr, 3), "dependent_precision": round(dp, 3),
        }
    return out


def report(res: dict) -> str:
    full = res["full_sweep"]["verifications"] or 1
    rows = ["strategy        verifs  cost  stale_P stale_R stale_F1  dep_R"]
    for name, m in res.items():
        rows.append(
            f"{name:<15} {m['verifications']:>6} {m['verifications']/full:>5.0%} "
            f"{m['stale_precision']:>7.2f} {m['stale_recall']:>7.2f} {m['stale_f1']:>8.2f} {m['dependent_recall']:>6.2f}"
        )
    return "\n".join(rows)


if __name__ == "__main__":
    print(report(run()))
