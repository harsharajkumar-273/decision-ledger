# Three-minute demo recording script

Use the synthetic Git migration fixture. Record the functioning app with real Nebius access. Keep the total video below three minutes, including the title and ending. Never show the .env file, API key, account billing details or private repository contents.

## 0:00–0:20 — Problem and audience

Show the workspace and the original Postgres decision.

“Code changes faster than the reasoning behind it. An engineering lead approves a database migration, but reporting still assumes PostgreSQL. Decision Ledger catches the assumptions the migration forgot to update.”

## 0:20–0:45 — Recorded decisions and evidence

Show the original reasoning, the dependency map, and a baseline full check on the fresh fixture.

“Each decision has an owner, source and reasoning. Dependencies connect the database choice to the ORM and reporting assumptions. Decisions can be recorded directly or extracted with NVIDIA Nemotron through Nebius Token Factory, then reviewed before saving.”

If the recorded baseline does not show model calls, correct the configuration and rerecord. Do not narrate a rules run as a model demonstration.

## 0:45–1:25 — Actual migration and automatic check

Enable Watch repository and run the migration helper in another terminal. Show the automatic verification, changed file and model execution summary.

“This local Git change switches deployment configuration to MongoDB. Decision Ledger checks the current repository evidence and uses Nemotron to assess the recorded decision. The old choice no longer matches. The evidence cites the configuration; it does not claim to have tested production behavior.”

## 1:25–2:00 — Dependency impact and resolution

Show the affected reporting and ORM decisions, owners and follow-up draft. Record the replacement of the old database decision with the migration decision.

“The graph traces the assumptions that still depend on the old choice and identifies the owners. A reviewer records the replacement and explains why. Retiring the old decision does not clear unresolved downstream work. Those owners still need to review their reasoning.”

## 2:00–2:30 — Recheck and audit

Recheck and show the persistent history. Show a reviewed result from RESULTS.md, if time permits.

“Rechecking preserves the replacement and pending reviews. The history keeps the evidence and human explanation. We use the same available Nemotron model for the three routing roles; the interface reports actual model calls and any fallback.”

If showing evaluation figures, use only the completed results in RESULTS.md. Do not claim model superiority when the comparison does not establish it.

## 2:30–2:50 — Close

“Decision Ledger is for engineers reviewing consequential changes. Our current build verifies local checkouts and tracks dependency impact. The change-review interface compares local revisions or working files without changing the ledger. GitHub PR integration is future work. The code is open source, and the demo uses a synthetic team fixture.”

End on the app with the project name and verified repository/demo URLs, added after publication.

## Recording checklist

- Fresh fixture; baseline check before migration; migration actually changes Compose.
- Actual live model calls and exact model ID visible, without exposing the key.
- Affected owners and cited evidence readable at recording resolution.
- Human replacement recorded; dependent reviews remain pending.
- Video below three minutes; public YouTube visibility; correct link in Devpost.
- Speak naturally; shorten the script rather than speed-reading.

## Alternative opening for the new change review

Open **Review this change** → **Try the migration example**. Show category counts and before/after database evidence, then the reporting dependency path and owner. Call it a packaged synthetic example. Turn on live Nemotron only when recording actual calls, and use the resulting counts rather than assuming they equal the rules-only run. For a real local Git comparison, use the prepared .local/change-review-demo repository with HEAD^ → HEAD. Close the comparison to return to the unchanged ledger before demonstrating human resolution.
