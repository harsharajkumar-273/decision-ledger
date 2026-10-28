# Usage guide

Detailed workflows for the Decision Ledger workspace. See the [README](../README.md) for an overview.

## Repository changes and audited resolutions

Use **Watch repository** to monitor relevant source, manifest and configuration files
and Git HEAD every five seconds. A change triggers a full verification sweep, including
silent drift. The report records changed paths and the commit; file contents and
credentials are not included in watch notifications. Watched files are limited to
5,000 files of at most 1 MB each. The ledger itself is excluded to avoid feedback loops.

Database verification now reads native `.env` database URLs, Compose images and
literal Python engine/client calls. It never executes repository code. Conflicting
or unresolved environments produce review rather than a guessed production state.
Explicit scope and conditional decisions are preserved by ingestion; unmet or
unverifiable conditions stay uncertain. Native configuration takes precedence over
the legacy `runtime.json` snapshot. Static settings do not prove production behavior.

Failed decisions generate local issue drafts with evidence, affected work and owners.
The inspector can record an existing decision as a replacement or a human confirmation
of a decision needing review. Each action records the reviewer, explanation and time.
Superseding an old assumption does not clear dependent work automatically. Rechecks
cannot revive superseded decisions. Set `DLEDGER_PERSIST=1` to save status and audit
history to the graph file; otherwise they remain in this server process.

```bash
python scripts/demo.py init /tmp/dledger-demo
DLEDGER_PERSIST=1 dledger serve /tmp/dledger-demo/ledger.json --repo /tmp/dledger-demo
# Enable Watch repository in the UI, then in another terminal:
python scripts/demo.py migrate /tmp/dledger-demo
```

Read [the three-minute demo](WINNING_DEMO.md), [collected results](RESULTS.md),
and [the real user-study protocol](USER_VALIDATION.md).

```bash
dledger doctor --live --out docs/results/model-readiness.json
dledger eval-models --task all --out docs/results/models.json
dledger benchmark --out docs/results/adversarial.json
dledger benchmark --models --out docs/results/model-comparison.json
```

Live evaluation never silently substitutes rules for unavailable models. Extraction,
linking and judging have separate labeled sets. The live RAG and graph judges use the
same configured model so tier differences do not confound that comparison. Their
prompts, context and guardrails differ, so this is a system comparison rather than a
pure graph ablation. The published local results are synthetic; live-model results,
external user feedback and Nebius deployment remain unverified until actually run.

## Verification history and review ownership

The **Review queue** keeps failed decisions and unresolved dependent work visible,
even after their original prerequisite is superseded. Filter by owner and select
a task to inspect its evidence and changed prerequisites.

The **Verification timeline** records checks, resolutions and resets with before/after
statuses. Select an event to inspect its read-only evidence snapshot or export it.
Historical views never replace the current graph or enable actions on old state.
Selective checks retain earlier evidence for decisions they do not reverify.

With `DLEDGER_PERSIST=1`, history is saved in `<graph path>.history.sqlite3`. Set
`DLEDGER_STATE` to choose another database path. Without persistence, history stays
in memory for that server session. The same graph and database must be retained
for restart recovery; if the graph was edited externally, the previous report is
kept in history but is not presented as the current state. Watch mode must be
enabled again after a server restart.

For a demo stored in the project rather than a temporary directory:

```bash
python scripts/demo.py init .local/demo
DLEDGER_PERSIST=1 dledger serve .local/demo/ledger.json --repo .local/demo
python scripts/demo.py migrate .local/demo
```

See [history and recovery](HISTORY.md) for the data lifecycle.

### Record decisions in the workspace

Use **Record decision** to capture a choice, subject, value, owner and reasoning. Optional prerequisites connect it to the existing graph; flagged prerequisites immediately put the new entry in the review queue. Superseded prerequisites cannot be selected. New entries are unchecked, never automatically supported.

Choose **Verify this decision** in the inspector to collect evidence for a single entry. Creation and verification have separate timeline snapshots. With `DLEDGER_PERSIST=1`, decisions and history survive server restarts; without it they last for the server session. The owner is a supplied attribution, not an authenticated identity.

API: `POST /api/decisions` accepts `text`, `subject`, `value`, `owner`, `reason`, optional `kind` (`tech_choice`, `commitment`, `policy`), `scope`, `source`, `condition`, ISO `date`, and `dependencies` (existing decision IDs). `POST /api/check` accepts `ids` for a targeted check, mutually exclusive with `full: true`.

### Import existing architecture decision records

Choose **Import ADRs**, paste Markdown and select **Preview decisions**. Each top-level `#` heading starts a record; `## Decision` supplies the choice and `## Context` or `## Rationale` supplies its reasoning. `Owner:`, `Subject:`, `Value:`, `Scope:` and `Condition:` metadata are optional; provide a default owner or fill missing fields in the preview. The built-in example demonstrates two records.

The parser uses local Markdown rules with no model calls. It suggests a subject and value only when the Decision section names one recognized technology. Ambiguous or incomplete records and non-accepted document statuses start unselected. Review the fields and select the records you want to save. These suggestions are not semantic validation: wording such as negation, alternatives or dependencies still needs human review. No relationships are inferred.

Imports preserve the supplied source label and starting line, save one timeline snapshot per batch, and leave entries unchecked. Identical text, subject, value and scope (ignoring case and surrounding whitespace) are skipped, including duplicates within the same batch. An invalid entry rejects the whole batch. Limits: 100,000 pasted characters, 20 records per preview/save. Imported claims can then be verified individually in the inspector.

API: `POST /api/import/preview` accepts `{text, source, owner}` and returns editable candidates without changing the ledger. `POST /api/import` accepts `{decisions: [...]}` using the same fields as decision creation, and returns `created_decision_ids` and `skipped_duplicates` alongside the report.


The workspace now shows evidence coverage and a list of decisions without recorded assessments. **Check unchecked decisions** checks those entries without rechecking previously assessed decisions. After saving an import, **Check imported decisions** checks the newly created entries as a batch. **What needs to change** summarizes failed/retired assumptions, unresolved dependents, owners and evidence. Coverage records whether a decision has been assessed, not whether it is supported.

In **Import ADRs**, opt into **Use Nemotron extraction through Nebius** to preview actual model suggestions. They remain unselected until reviewed. The preview reports its model and token count; unavailable model access fails explicitly without silently using Markdown rules. Configure all routing roles and use the CLI ingestion workflow for model-based dependency linking. Live extraction, linking and judging evaluations are recorded in RESULTS.md; a public hosted deployment and actual user study remain outstanding.
