# Decision Ledger — submission draft

**Track:** Best Apps and Agents

**Public code:** https://github.com/harsharajkumar-273/decision-ledger

**Demo URL:** pending deployment

**Public YouTube URL:** pending recording and upload

**Pitch:** Decision Ledger catches the assumptions your migration forgot to update.
It checks recorded engineering decisions against repository evidence, traces affected
work and owners, and keeps the resolution history.

**Primary audience:** engineering leads reviewing database migrations and dependency changes.

**Change review:** compare local Git revisions or working files against the same ledger,
with before/after evidence, new/existing/resolved findings, affected owners and read-only exports.
A packaged migration example works without Git. Automatic GitHub PR integration is not implemented.
See `CHANGE_REVIEW.md` for behavior, limits and measured live execution.

## Demonstrated locally

- Read-only before-and-after Git comparison and a guided migration example.

- A Git/configuration change automatically triggers verification.
- Native deployment files provide redacted, file-referenced database evidence.
- Failed decisions propagate review flags to their downstream work.
- Local issue drafts list affected owners and cite the evidence.
- Human resolutions record replacement decisions, explanations and audit history.
- Rechecks preserve supersession and do not silently clear unresolved dependencies.
- Search and answers include conflict/staleness warnings and permission filtering.
- Reviewed ADR imports, one-click batch verification and evidence coverage support onboarding.
- Impact summaries identify changed assumptions, unresolved dependent work and review owners.
- Model extraction is wired into the import preview with explicit failure handling; live extraction has passed a small synthetic smoke test.

The engine routes extraction, linking and judging to configurable Nemotron models
through the Nebius-compatible API. **Live connectivity and a small synthetic extraction/judging smoke test are now verified**
with `nvidia/Nemotron-3.5-Super-VL` on Nebius. All three routing roles currently use
that same model. Live evaluations are now recorded: on 16 synthetic repository cases, the graph-aware
model path scored 14/16 versus 11/16 for the model retrieval baseline, while
deterministic evidence rules scored 16/16. The graph path had one error. These
small, non-held-out results do not establish general superiority. See `results/live-readiness.json` and `results/live-smoke.json`.

## Evidence

See `RESULTS.md` and `results/` for the synthetic strategy comparison, adversarial
repository cases, readiness status and a pinned read-only FastAPI repository trial.
The public-repository trial returns uncertainty for unresolved application settings;
it does not establish what that project's production deployment uses.

The retrieval-only latest-message heuristic and package-only checks are weak
ablations. The same-model RAG-vs-graph comparison has been run; prompts and guardrails differ, so it is not a pure graph ablation.
The adversarial set is hand-authored and small, not held out.

See `FINISH_AND_SUBMIT.md` for the step-by-step runbook and `scripts/prepare_submission.py` for reproducible local checks and optional live evaluations.

## Before submitting

- Completed: configured model access and live readiness probes.
- Completed: saved extraction/linking/judging measurements and the live comparison; review RESULTS.md.
- Complete actual user sessions from `USER_VALIDATION.md`; use only real quotes.
- Deploy the demo if needed, verify access, and record the final three-minute video.
- Completed: recorded technical feedback from actual Nebius/NVIDIA usage in `FEEDBACK.md`; add your personal onboarding observations if applicable.
- State precisely what existed before the submission window and what was added during it.

Demo URL, video URL and user observations are still required; the public code repository is linked above. Real model metrics are recorded in RESULTS.md. Nothing in this draft claims a Nebius deployment or a completed user study.
