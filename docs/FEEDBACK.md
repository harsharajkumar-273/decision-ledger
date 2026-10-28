# Feedback from actual tool usage

## Nebius Token Factory and NVIDIA Nemotron

We used `nvidia/Nemotron-3.5-Super-VL` through the public Nebius Token Factory endpoint for decision extraction, relationship linking and evidence-based judgments. All three routing roles used this same model. The advertised Nano/Super/Ultra role names in our code are configurable responsibilities, not three model-size comparisons.

What worked: the API was compatible with the existing client; model-list discovery provided the exact available ID; connectivity probes and a synthetic extraction/judgment workflow succeeded. The completed evaluation harness recorded 95 successful API responses across the extraction, linking, judging and graph/retrieval comparison runs. Tokens and wall times are retained in `docs/results/models.json` and `docs/results/model-comparison.json`.

What needs work: one graph-context benchmark response could not be parsed as JSON and is recorded as JSONDecodeError. In another seed evaluation, a conditional scenario produced an invented supersession edge, and one uncertain judgment was marked valid. Our application therefore retains review of model import suggestions, evidence guardrails and explicit fallback disclosure. More dependable structured output and conservative handling of conditional decisions would improve this workflow.

Concrete developer-experience request: keep exact model IDs and account availability easy to discover alongside schema/structured-output support, and provide examples of reliable machine-readable output with reasoning models. We do not infer unavailable capabilities from the observed parse failure.

The local machine's initial CLI configuration was incomplete. We configured the account key locally, listed available models, and ran probes before the evaluation. Signup-to-first-call time, credit-claim delay, account billing cost and rate-limit behavior were not systematically measured. Do not add invented figures for them.

## Hosting and other tools

Nebius AI Cloud, Serverless Endpoints/Jobs, NVIDIA embeddings, OpenShell/NemoClaw, Tavily and partner evaluation services were not exercised in this measured run. The repository includes optional integrations and deployment notes; those are not evidence of actual service usage. A Render deployment Blueprint has been prepared but not yet deployed.

These are technical observations from the recorded build. Add the project author's own onboarding and product feedback only if it reflects their actual experience.
