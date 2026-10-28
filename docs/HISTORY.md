# History, evidence and pending reviews

A check records its complete graph snapshot, direct verdicts, accumulated evidence,
local drafts, trigger, changed paths, model usage and status transitions. A resolution
records the reviewer and explanation with a new snapshot. Earlier snapshots remain
unchanged. The timeline shows the 30 most recent events; the API supports up to 100
per listing and retrieves any known event ID separately.

A selective check only reports its newly checked decisions in `verdicts`; evidence
for other decisions is retained in `known_verdicts` with its original timestamp.
Retained evidence is not proof that an unchecked decision was reverified today.

The review queue uses current graph status. Failed prerequisites and superseded
assumptions are named explicitly. Recording a replacement closes the old decision,
but does not remove its dependents from the queue. Confirming a human review records
that person's judgment; later contradictory evidence can still reopen the decision.

## Persistence

`DLEDGER_PERSIST=1` enables graph saves and a local SQLite history database. The default
path is `<graph path>.history.sqlite3`; `DLEDGER_STATE` can override it. Keep both files
in the same durable workspace and back them up together. Graph writes use a temporary
file and atomic replacement, so a failed replacement leaves the previous file readable.

At startup, the latest report is restored if its graph matches the saved graph. If
someone edited the ledger externally, its current content is respected and the old
report is available only in history. Reset clears the current report and records a
reset event; it does not erase history or recorded resolutions. With persistence,
Reset reloads the saved graph rather than undoing prior saved decisions.

Without persistence, report history lives in memory and is lost when the server stops.
The watcher is intentionally disabled at startup and can be enabled from the UI.

The graph file and SQLite database are two separate stores, not a distributed atomic
transaction. Do not run multiple writers against one ledger. The interface remains
an administrative local workspace; historical content has the same access scope as
the existing graph and report endpoints.

## API

- `GET /api/history?limit=30`: event summaries and whether storage is durable.
- `GET /api/history/{event_id}`: complete read-only event snapshot.
- `GET /api/reviews?owner=maya`: current pending work, optionally filtered by owner.
- `GET /api/report`: current report with retained evidence and the current review queue.
