# Finish and submit Decision Ledger

The app implements decision recording, reviewed Markdown/model import, dependency impact, repository watching, batch and individual verification, audit history, and local follow-up drafts. This guide separates reproducible local work from steps that need your accounts, credentials or real participants.

## 1. Install and open the app

From the `decision-ledger` project folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,server]'
```

For an existing demo:

```sh
DLEDGER_USE_LLM=0 DLEDGER_PERSIST=1 .venv/bin/dledger serve .local/demo/ledger.json --repo .local/demo --port 8000
```

Visit http://127.0.0.1:8000/. Evidence coverage lists current decisions without an assessment. **Check unchecked decisions** checks those entries, including isolated imports. A completed assessment can be inconclusive; it is not automatically a supported decision.

For a fresh demonstration, choose a new directory so you preserve earlier work:

```sh
.venv/bin/python scripts/demo.py init .local/submission-demo
DLEDGER_USE_LLM=0 DLEDGER_PERSIST=1 .venv/bin/dledger serve .local/submission-demo/ledger.json --repo .local/submission-demo --port 8000
```

Stop the existing server first if port 8000 is in use. The UI's Reset reloads the saved ledger; it does not undo the migration or erase persisted decisions.

## 2. Connect real NVIDIA models through Nebius

Create or open your Nebius Token Factory account, obtain an API key, and find NVIDIA model IDs available to your account. Copy `.env.example` to `.env` only if `.env` does not already exist. Enter these values in that local file, never in chat or the repository:

```dotenv
NEBIUS_API_KEY=your_key_here
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
DLEDGER_MODEL_NANO=exact_available_model_id
DLEDGER_MODEL_SUPER=exact_available_model_id
DLEDGER_MODEL_ULTRA=exact_available_model_id
```

The roles may share the same actual available NVIDIA model while you establish a working baseline. Do not imply that three different model tiers were tested unless they were. Verify the current API base URL in the provider console.

```sh
.venv/bin/dledger doctor --live
```

All three probes must succeed. If they fail, check the key, credit balance, model access and exact IDs. Restart the app with `DLEDGER_USE_LLM=1` after updating the file; `dledger serve` loads `.env` from the working directory. The workspace's configuration indicator only detects settings; it does not certify a successful model call.

## 3. Demonstrate the complete model workflow

1. Open **Import ADRs**, paste a real ADR you have permission to use, set its source label and owner, and choose **Use Nemotron extraction through Nebius**.
2. Preview. Inspect the suggested choice, subject, value and reasoning against the original document. Model suggestions begin unselected and need your review.
3. Select the entries and save. Then choose **Check imported decisions**. The inspector shows the evidence and the execution summary discloses model calls, IDs, tokens, time or fallback.
4. Inspect **What needs to change** for changed prerequisites, affected work and review owners. Imported dependencies are not automatically inferred by this UI; use the CLI ingestion workflow below for model-generated linking, or record explicit prerequisites through Record decision.
5. For the migration story, run a baseline full check and enable Watch repository, then in another terminal:

```sh
.venv/bin/python scripts/demo.py migrate .local/submission-demo
```

Show the automatic check, cited Compose change, affected reporting assumptions, issue draft, human replacement and preserved history. Follow WINNING_DEMO.md for the narrative. This is a synthetic team's fixture, not a customer deployment.

Model-based extraction and linking from message JSONL are also available through the CLI. See `dledger ingest --help` for the exact inputs and output options. Previewed Markdown imports are not automatically connected into a dependency graph.

## 4. Collect evidence in one command

Local checks (no model API calls):

```sh
.venv/bin/python scripts/prepare_submission.py
```

After the live probes succeed, opt in to evaluations (uses provider credits):

```sh
.venv/bin/python scripts/prepare_submission.py --live
```

Each run writes a new directory under `.local/submission-runs/` with test logs, readiness, benchmark outputs and a manifest. Live mode stops if setup or a live probe fails. Review model accuracy, false alarms, misses, tokens and latency. Check for fallback or failed cases before presenting any metric. The small hand-authored datasets do not establish general real-world accuracy. Copy only reviewed, non-sensitive results into `docs/results/`; the local run directory is gitignored.

## 5. Get real user feedback

Ask two developers to use the synthetic demo. Ask each to find the changed assumption, identify the affected owner, and explain the cited evidence. Observe without coaching, record task completion and confusion, and obtain permission for any attributed quote. Use USER_VALIDATION.md. Fix observed failures; do not invent customer validation.

## 6. Publish a judge-accessible build

For a concrete hosting path, follow [the Render deployment guide](../deploy/render.md) and the included `render.yaml`. The app supports an optional demo sign-in via `DLEDGER_DEMO_USER` and `DLEDGER_DEMO_PASSWORD`. Both must be set together; `/healthz` stays public for host checks. Use HTTPS on the hosted service.

The Dockerfile packages the app with synthetic sample data. Test it locally:

```sh
docker build -t decision-ledger:submission .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -e DLEDGER_USE_LLM=1 decision-ledger:submission
```

On a hosting service that accepts Docker images, deploy that same build, set the secrets through its environment settings, expose container port 8000, and check `/healthz`. Use `deploy/nebius.md` as planning notes and verify the current deployment steps against the provider console; those example commands are not a verified deployment.

Use synthetic data for judging. Put the writable app behind your hosting platform's authenticated access layer and provide judges access instructions. A shared public writable workspace can be altered by other visitors and can consume your model credits. For persistence, use durable storage for the graph and adjacent history database and run a single server worker. For a disposable test build, leave persistence disabled. The watcher needs a continuously running process; it cannot monitor while a host is asleep.

Test the final URL from a signed-out browser using the supplied access instructions. The localhost URL is not accessible to judges. Hosting and external account setup have not been completed by the local build.

## 7. Record and submit

Record one focused video of three minutes or less. Lead with the developer problem, demonstrate the migration and impact, show actual NVIDIA/Nebius calls, and end with the evidence and limitation. Upload it publicly to YouTube. Publish the code with LICENSE and setup instructions; exclude `.env`, local state, credentials and private source material.

Update SUBMISSION.md with the demo URL, video URL, repository URL, real measurements, actual tool feedback, and an accurate statement of what was built during the eligible period. Review the current Devpost requirements and deadline before submitting:

https://nebiusglobalaihackathon.devpost.com/

Recommended track: Best Apps and Agents. Complete the Devpost form, verify the links and category, and submit from your account. No Devpost submission, public deployment, public repository creation or video upload has been performed by this code change.
