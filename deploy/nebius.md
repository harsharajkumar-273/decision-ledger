# Deploying on Nebius

Everything below runs the same container image. Check command names against the
current Nebius docs for Serverless Endpoints and Serverless Jobs; the console and
CLI change faster than this file.

## 1. Build and push the image

```bash
docker build -t <registry>/decision-ledger:0.2 .
docker push <registry>/decision-ledger:0.2
```

## 2. Endpoint: web UI, API, Slack command

Create a Serverless Endpoint from the image.

| Setting | Value |
|---|---|
| Port | 8000 |
| Env | `NEBIUS_API_KEY`, `NEBIUS_BASE_URL`, `DLEDGER_MODEL_NANO/SUPER/ULTRA`, optional `DLEDGER_MODEL_EMBED`, `TAVILY_API_KEY`, `SLACK_SIGNING_SECRET` |
| Data | mount your graph and repo snapshot; set `DLEDGER_GRAPH`, `DLEDGER_REPO`, `DLEDGER_PERSIST=1` |
| Health check | `GET /healthz` |

Point a Slack slash command (for example `/why`) at `https://<endpoint>/slack/command`.

## 3. Job: nightly full sweep

Create a Serverless Job from the same image with the command:

```bash
dledger sweep $DLEDGER_GRAPH --repo $DLEDGER_REPO --web --save $DLEDGER_GRAPH \
  --report /out/report.json --slack --issues <owner>/<repo>
```

Schedule it nightly. It verifies every decision (closing the silent-drift gap that
the graph-guided check can miss), writes verdicts back, posts a Slack summary, and
opens one GitHub issue per failed decision (`GITHUB_TOKEN` needs issues:write).
`--fail-on-stale` makes the job exit non-zero if you want the run marked failed.

## 4. Sandboxed verifiers

Verifiers only read. To run each one in an isolated child process with a scrubbed
environment (no API keys), set `DLEDGER_SANDBOX_CMD`, for example under an
OpenShell/NemoClaw sandbox with a read-only mount of the repo:

```bash
DLEDGER_SANDBOX_CMD='openshell run -- {python} -m dledger.sandbox_worker {repo}'
```

The worker protocol is: claim JSON on stdin, repo path as the argument, evidence JSON
on stdout. Any wrapper that keeps that contract works. Check the OpenShell/NemoClaw
docs for the exact wrapper syntax on your install.

## Current verification status

No Nebius deployment has been performed. Use the real console and available model
catalog to configure IDs; Nano/Super/Ultra are routing roles, not a guarantee that
three identically named models are available in your account. Run `dledger doctor
--live` and save measured evaluation results before recording a model demo.

The watcher is designed for a single continuously running server with the repository
and graph mounted on durable storage. It monitors local files and Git HEAD; it does
not pull new commits, receive GitHub webhooks, or merge changes. Update the mounted
checkout through your existing deployment process. Stateless or scale-to-zero endpoints
need an external scheduled job instead. Do not expose the administrative UI and
resolution endpoints to a private company ledger without an authenticated access layer.

The UI's follow-up issues are local drafts. Existing CLI Slack/GitHub publishing is
separate and should only be used with explicit authorization to publish to that target.
