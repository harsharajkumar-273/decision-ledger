# Evidence-to-resolution demo (three minutes)

This is a synthetic team's ledger in a real local Git repository. It does not
claim to represent decisions made by FastAPI maintainers.

```bash
python scripts/demo.py init /tmp/dledger-demo
DLEDGER_PERSIST=1 dledger serve /tmp/dledger-demo/ledger.json --repo /tmp/dledger-demo
```

1. Establish a baseline with **Run check**, then enable **Watch repository**.
   The old Postgres decision is supported; the newer migration decision has not been implemented.
2. In another terminal, run `python scripts/demo.py migrate /tmp/dledger-demo`.
   Show the Git commit and Compose diff. Both database drivers remain installed.
3. Within about five seconds, the watcher runs a full check. Show the automatic
   trigger, changed files, commit, and `compose.yml` evidence. Postgres is contradicted;
   MongoDB is supported; SQLAlchemy and Postgres reporting need review.
4. Open the locally generated issue draft. Show evidence, affected work and owners.
   Nothing is published to GitHub or Slack by this UI.
5. Select the old decision, record the MongoDB replacement with a reviewer and reason.
   The conflict closes; dependent work remains flagged. Select a dependent decision
   and record a human review only after reviewing its actual implementation.
6. Recheck. Superseded decisions remain superseded and unresolved dependent reasoning
   remains flagged. Export the JSON report containing evidence and audit history.

For the submitted video, configure `.env` with real Nebius credentials and available
Nemotron model IDs, then run `dledger doctor --live`. The UI must show actual model
calls and IDs, not rules fallback. Do not present a rules run as a model demonstration.

Suggested narration: "A migration PR changes our database. Our reporting still
assumes Postgres. Decision Ledger notices, cites the changed configuration, traces
what depends on that assumption, and helps the owners record what should replace it."

## What still needs real-world proof

- Real model accuracy, latency and token usage: run the commands below.
- User usefulness: carry out `USER_VALIDATION.md` with real participants.
- Nebius hosting: deployment instructions are provided, but no endpoint was deployed.

```bash
dledger doctor --live --out docs/results/model-readiness.json
dledger eval-models --task all --out docs/results/models.json
dledger benchmark --models --out docs/results/model-comparison.json
```
