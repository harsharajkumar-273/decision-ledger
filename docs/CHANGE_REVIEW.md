# Review this change

This feature compares the same current decision ledger against two repository snapshots without writing verdicts to the ledger, changing the checkout, or recording resolutions.

## Try the guided example

1. Open the app and select **Review this change**.
2. Select **Try the migration example**. It uses packaged synthetic decisions and configuration snapshots, so it works on the hosted container without Git.
3. Inspect the new, existing, resolved and unchanged groups. Expand a finding to see its original reasoning, owner, source, before/after evidence and dependency path.
4. Export the comparison if desired. The export is distinct from a normal persisted verification report.

With deterministic checks, the example produces three new findings (the database choice plus ORM/reporting dependencies), one resolved migration decision, and two unchanged decisions. Those are categories of decisions, not counts of distinct incidents or confirmed runtime defects.

The live model run in `results/live-change-review.json` used 12 NVIDIA model calls with zero fallback and produced two new, one existing, one resolved and two unchanged decisions. The model treated some baseline evidence as uncertain. The recorded category summary was computed from the saved assessments using the current grouping rules; the model assessments are retained unchanged. Do not present the deterministic category counts as model results.

## Compare your local Git repository

Start the app with `--repo` pointing at the repository root and the ledger path supplied separately. The repository must have a commit; comparing arbitrary nested folders in a parent repository is rejected.

- **Base revision:** a local commit or branch, for example `main`, `HEAD^`, or a commit SHA.
- **Proposed revision:** another local commit or branch, or `WORKTREE` for current working files.
- **Compare revisions:** snapshots both sides into temporary directories, verifies each side, and traces the dependency impact.
- **Use live Nemotron:** opt in to actual model calls for both snapshots; this consumes provider credits. Rules remain the default for a fast, repeatable review.

No fetch, checkout, hook, GitHub comment or repository code execution is performed. Current working files include relevant untracked/ignored files; Git revision snapshots include tracked regular files. The configured ledger and history file are excluded. Relevant symlinks/submodules in Git snapshots are rejected. Working-tree symlinks are skipped by the bounded file watcher. Large files/snapshots are rejected rather than silently truncated.

## How categories work

- **New:** a supported decision becomes uncertain/failing, or an uncertain decision becomes explicitly stale/contradicted.
- **Existing:** the decision still needs attention; a stale/contradicted distinction changing within an existing failure stays in this group.
- **Resolved:** a previously uncertain/failing decision is supported in the proposed snapshot.
- **Unchanged:** supported in both snapshots.

Retired decisions are not reverified. Both sides start from independent copies of the same ledger; historical decision versions are not reconstructed. Identical file snapshots reuse the same assessment, preventing artificial differences from repeated model sampling on unchanged files.

The report does not run application tests, prove production behavior or certify that merging is safe. It supplies reviewable evidence. Resolution remains a separate human action in the ledger.

## API

`GET /api/change-review/options` reports Git availability and suggested revisions.

`POST /api/change-review` accepts either:

```json
{"base":"HEAD^","target":"HEAD","use_llm":false}
```

or:

```json
{"demo":true,"use_llm":false}
```

The result contains commit identities (or explicit synthetic labels), changed-file hashes, before/after verdicts and redacted evidence, affected owners and dependency paths, category counts and actual model usage/fallback. It does not return raw file content. It is not stored in the normal verification timeline; download the export to retain it.

## Review brief

Comparisons now open with a brief listing changed files, challenged decisions, owners and cited evidence. Direct contradicted/stale findings are separated from uncertain or dependent concerns. Each item links to its full before/after evidence and dependency paths. Detailed categories stay collapsed until requested; JSON exports include the same grounded `brief` object. The brief uses existing assessments and makes no extra model calls.

## Bring existing ADRs

Select **Import ADRs → Choose existing ADR files** to load up to 20 `.md`, `.markdown` or `.txt` files (100 KB combined). Alternatively paste Markdown. Preview keeps each filename and line reference, extracts choices and owners, and lets you edit or deselect candidates before saving. Accepted ADRs and MADR Decision Outcome / Context and Problem Statement sections are supported by the rules parser. Unknown or ambiguous choices require manual completion or opt-in Nemotron extraction. Missing owners are never invented; supply a default or edit each candidate. Relationships are not automatically inferred by file import.

The preview is read-only. Saving is explicit, duplicate-safe and atomic; newly saved decisions remain unchecked. Use **Check imported decisions** afterward. Try the two files in `data/adr-demo/` to exercise the flow.

Batch preview API: `POST /api/import/preview` with `{"documents":[{"source":"0001-cache.md","text":"..."}],"owner":"Default reviewer","use_llm":false}`. At most 20 candidate decisions can be saved in one batch.
