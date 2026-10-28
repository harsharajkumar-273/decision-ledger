# Decision Ledger: a sharper product thesis

## Target positioning

**Before you merge, see which earlier decisions your change invalidates—and who needs to review the consequences.**

Decision Ledger helps engineering leads review migrations and dependency changes against the team's recorded reasoning. It connects a proposed code change to affected decisions, their dependents, the evidence, and the owners who need to respond.

This is the target positioning. The current app verifies a local checkout and reacts to local Git/configuration changes. Comparing an unmerged change with its base is the next product increment, not an existing capability.

## One audience, one expensive moment

Audience: an engineering lead reviewing a database migration or dependency change in an existing service.

Moment: the implementation has changed, but old assumptions still support reporting, integrations or downstream architecture. The reviewer must find those assumptions and decide which owners need to revisit them.

Hypothesis to validate: linking a change to recorded assumptions helps reviewers find consequential dependencies they miss with document search and code inspection alone. Do not claim prevented incidents or saved hours without measuring them.

## The core unit is a reviewable finding

A finding should answer five questions in this order:

1. What changed? Show a specific file and, for the proposed comparison feature, its base and changed version.
2. Which recorded decision does that evidence challenge? Link to its source and original reasoning.
3. What still depends on that decision? Show the dependency path and explain the limitation of the evidence.
4. Who should review it? Name affected owners or say that ownership is missing.
5. What action closes the finding? Record a replacement, review a dependent assumption, or acknowledge insufficient evidence.

Example narrative using the synthetic migration fixture:

> The deployment now selects MongoDB. The recorded PostgreSQL decision no longer matches that configuration. Reporting still depends on PostgreSQL window functions, and the ORM decision was justified by the old database choice. Li and Maya need to review those assumptions. Configuration evidence alone does not prove those application features fail at runtime.

Lead with this brief. Let the graph explain the dependency path when the reviewer asks for detail.

## The signature feature to build next

**Review this change**: compare a base Git revision with a proposed revision or working tree, then produce a decision-impact brief.

Required behavior:

- Verify both snapshots using the same recorded decisions and verification settings.
- Distinguish newly contradicted decisions from pre-existing findings and resolved findings.
- Show base/current evidence with file references and commit identities.
- Trace unresolved downstream assumptions and owners.
- Keep the review read-only until a human records a resolution.
- Do not run repository code or silently rewrite decisions.

Keep the first release to local Git comparison. A GitHub app, PR comments, automatic patching and enterprise integrations would add setup and failure modes before this core interaction is proved.

## Why a graph and why Nemotron

Use the models for the tasks that need interpretation: extracting an actual choice from prose, proposing relationships across decisions, and explaining whether repository evidence applies to the original reasoning. Have a person review imported model suggestions and inferred relationships.

Use deterministic operations for graph traversal, status propagation, source references, audit history and numeric summaries. The model must not invent owners, measured savings, relationships or verification results.

Demonstrate the extraction → reviewed graph → verification → impact → human resolution workflow with actual NVIDIA models through Nebius. Routing roles may share one available NVIDIA model at first. Report the exact IDs used and disclose fallback. Three role names are not evidence of three tested models.

## Evidence that could make the idea convincing

Compare three approaches on the same cases and same available model where applicable:

- Repository verification without recorded decision relationships.
- Retrieval-only reasoning over the same decision documents and repository evidence.
- Decision Ledger with the reviewed dependency graph.

Measure direct contradictions found, downstream affected assumptions found, false alarms, unsupported claims, latency and tokens. Include unchanged controls, old findings, missing configuration and ambiguous scope. Freeze labels before running the comparison. Retain unsuccessful cases.

The existing small synthetic/adversarial sets are a starting point. The live comparison has not been run. The public repository trial does not prove real customer adoption or runtime correctness.

Ask engineers to identify the changed assumption, its affected owner and its supporting evidence using the brief. Compare task completion with their usual search/read workflow. Collect actual observations, not hypothetical testimonials.

## Three-minute story

- 0:00–0:20: introduce an engineering lead reviewing a database migration and the forgotten reporting assumption.
- 0:20–0:45: show the original decision and its reasoning, with a reviewed dependency.
- 0:45–1:30: show the real local migration and the resulting evidence-backed impact brief. Use an unmerged comparison only after that feature exists.
- 1:30–2:05: inspect the reporting dependency and owner, record the replacement, and show unresolved dependent work remains flagged.
- 2:05–2:35: show actual Nemotron/Nebius execution and one measured comparison result, if available.
- 2:35–2:55: state the specific audience, limitations and next step.

Use the implemented local workflow if the comparison feature is not finished. Never label a synthetic fixture as a customer incident, or a local Git check as a deployed GitHub integration.

## Scope discipline

Prioritize live model proof, one coherent change-review interaction, a measured comparison, real user observations and a reliable judge-accessible demo. Keep general commitment tracking, policy management, extra connectors, autonomous code repair and broad assistant features out of the main pitch.

The submission should make the problem, required platform usage and working behavior apparent without asking judges to inspect the architecture first.

Official judging guidance checked October 24, 2026:
- https://nebiusglobalaihackathon.devpost.com/updates/46204-here-s-how-judging-works
- https://nebiusglobalaihackathon.devpost.com/updates/46205-how-to-build-a-winning-project
