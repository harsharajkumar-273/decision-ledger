# Evidence collected

## Current measured status — October 28, 2026

Local suite: **96 passing tests**. Live endpoint: `nvidia/Nemotron-3.5-Super-VL` through Nebius Token Factory. All three routing roles used that same model, so their differences below are repeat-run variation, not comparisons between model sizes. No user study or public deployment has been completed.

### Live extraction, judging and linking

> **The judge set has since grown from 12 to 47 cases** (14 valid, 13 contradicted, 20 needs_review; adds conflicting environments, leftover dependencies, conditional and scoped claims, policy claims, and evidence containing injected instructions). The judge accuracies in the table below were measured on the original 12 cases only and have **not yet been re-measured** on the 47. Rerun `dledger eval-models --task judge --out docs/results/models.json` with Nebius credentials before citing them. On the 47 cases the deterministic rule baseline scores 39/47 (0.830), which is the number a model judge has to beat.

Hand-authored sets: 22 messages for extraction, 12 judging cases, 6 linking scenarios. Scores use the harness definitions; extraction matches source/value pairs, not full semantic correctness.

| Routing role | Extraction precision / recall / F1 | Judge accuracy | Linking precision / recall / F1 |
|---|---|---|---|
| nano | 1.0 / 1.0 / 1.0 | 0.833 (12 cases) | 1.0 / 1.0 / 1.0 |
| super | 0.929 / 0.929 / 0.929 | 0.833 (12 cases) | 1.0 / 1.0 / 1.0 |
| ultra | 1.0 / 1.0 / 1.0 | 0.917 (12 cases) | 0.75 / 1.0 / 0.857 |

The ultra-role judge incorrectly marked one uncertain case valid. The ultra-role linking run invented a supersession edge in a conditional scenario. All misses are retained in `results/models.json`; the results justify keeping human review for model suggestions.

### Live graph-context versus retrieval baseline

On 16 synthetic adversarial repository cases, using the same model:

| Approach | Correct | False contradictions | Errors |
|---|---:|---:|---:|
| Deterministic evidence rules | 16/16 | 0 | 0 |
| Graph-aware model judge | 14/16 | 0 | 1 |
| Model retrieval baseline | 11/16 | 1 | 0 |

The graph path returned needs_review for a contradicted leftover-driver case and errored on a conditional case. An error counts as incorrect. This is a small hand-authored, non-held-out set. The graph and retrieval variants differ in prompts, context and guardrails; the result does not isolate the graph effect. Deterministic rules performed best on these cases. The latest-message and package-only heuristics are deliberately weak ablations. See `results/model-comparison.json`.

Combined evaluations recorded 95 successful API responses, 33441 input tokens and 77751 output tokens; unsuccessful calls may consume additional provider usage. Latency is per-run wall time in the raw JSON, not a production throughput benchmark. Monetary cost has not been independently reconciled against billing.

## Previously collected local evidence

`results/git-change.json` captures a local synthetic Git migration triggering a watcher check with changed files and evidence. `results/resolution-recheck.json` records supersession surviving a recheck with unresolved dependents still flagged.

`results/public-repository.json` records a pinned read-only FastAPI template trial. It returns uncertainty for unresolved application settings and does not establish production configuration or maintainer decisions. No code from the public repository was executed.

`results/live-smoke.json` records one synthetic extraction and two live judgments without fallback; `results/live-readiness.json` records successful probes.

## Still outstanding

A judge-accessible deployment, actual developer feedback, a public demonstration video and final Devpost submission. Before-and-after Git comparison remains future work.
