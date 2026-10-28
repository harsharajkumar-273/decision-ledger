# Demo video script (3:00 max)

Record the UI (`dledger serve ...`) and one terminal. Keep the voiceover plain. The Nebius/Nemotron usage must be visible, so run the real-model version of the demo, not `--no-llm`.

Setup before recording: `.env` filled in, `dledger ingest data/sample/messages.jsonl --out /tmp/g.json`, `dledger serve /tmp/g.json --repo data/sample/repo`.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Graph in the UI, all grey | "Every team makes decisions in Slack, tickets and PRs. Months later the code has moved on and nobody notices. This is Decision Ledger: a graph of decisions that checks itself against reality." |
| 0:20 | Terminal: `dledger ingest` with the Token Factory model ids visible | "Messages from Slack, Jira and GitHub go through Nemotron Nano on Nebius Token Factory. It extracts decisions; Nemotron Super links them into a dependency graph." |
| 0:45 | Ask box: "why do we use postgres?" | "A new engineer asks why we use Postgres. Plain search would answer with a March message. Here the answer also warns that a July decision conflicts with it and nothing records which one won." |
| 1:10 | Click **Run check**, watch the spread | "Now it verifies. A sandboxed agent reads the repo and finds the team moved to MongoDB. Nemotron Ultra judges the conflict and marks Postgres contradicted. Watch what else is at risk: the ORM and the reporting queries depended on it, and they light up automatically." |
| 1:50 | Verdict cards with evidence refs | "Every verdict cites its evidence: the file and line, or the roadmap entry. If the model is unsure, it says needs review instead of guessing." |
| 2:05 | Second tab: a second server on port 8001 (`DLEDGER_AS_OF=2026-10-08 dledger serve data/commitments/graph.json --repo data/commitments --port 8001`) | "Same engine, different domain. Sales promised Acme SSO by June. The roadmap says November. And Initech's SCIM promise depended on it." |
| 2:30 | Terminal: `dledger eval` and `dledger eval-models` output | "Using the graph to pick candidates checks 57% as many items as a full sweep and finds more stale decisions than random picking. Nano handles the bulk, Ultra only the hard cases, so cost stays low. A nightly Serverless Job sweeps everything." |
| 2:50 | Repo page showing license and README | "It is open source under MIT. Built on Nemotron and Nebius Token Factory." |

Rules from the hackathon: public YouTube video, 3 minutes or less, must show Token Factory and Nemotron in use.

For an evidence-driven before/after demo, copy `data/sample/repo` to `/tmp/ledger-demo-repo`.
Start with `runtime.json` selecting `postgresql` for `database`, then switch that setting to
`mongodb` during the recording and run the check again. Keep both drivers installed to show
why installed packages alone cannot establish the active database. The graph should mark the
old decision contradicted and its dependents for review. State clearly that this is a sample
configuration snapshot; it does not discover production settings. The execution line must show
real Nemotron calls. If it says rules fallback, resolve credentials/model configuration first.
