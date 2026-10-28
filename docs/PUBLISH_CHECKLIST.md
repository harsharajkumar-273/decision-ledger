# Publishing handoff

## Account action currently needed

Reconnect a working GitHub account with `gh auth login --hostname github.com --git-protocol https --web`. The GitHub connector returned an account-suspended error; the local CLI was subsequently reconnected through browser sign-in and authenticated as harsharajkumar-273. Use the CLI connection for publication.

## Public repository

Published: https://github.com/harsharajkumar-273/decision-ledger. The following commands describe the completed first-publication process; do not recreate the repository.

After signing in, run these commands from the project folder. Choose the intended account before creating the repository. The command creates a public repository, so review what will be included first.

```sh
git init -b main
git add README.md LICENSE pyproject.toml Dockerfile .dockerignore .gitignore .github src tests scripts data docs deploy
git status --short
# Confirm .env, .venv, .local and local history databases are absent.
git commit -m 'Prepare Decision Ledger hackathon submission'
gh repo create decision-ledger --public --source=. --remote=origin --push
```

If `decision-ledger` already exists, inspect it before choosing a different repository name or remote; do not overwrite an unrelated repository. The source archive under `.local/release/` is an alternative handoff artifact. Regenerate it with `python scripts/package_submission.py` after final edits.

## Demo access

Follow FINISH_AND_SUBMIT.md section 6 for the container and hosting settings. The Docker CLI is installed here, but the Docker engine was not running when checked. Start Docker Desktop before building. A ready-to-deploy Render Blueprint is included; follow deploy/render.md. Hosting account access and final deployment are still needed; no external deployment has been performed.

Use synthetic sample data and provide judges access instructions. Localhost is not a public demo. The writable app must be protected by the hosting platform's authenticated access layer. Test from a separate browser and keep the service available for judging.

## Real feedback

Personally invite two developers to try the demo. Ask them to find the changed assumption, identify the owner and explain the evidence. Write down mistakes and questions. Follow USER_VALIDATION.md. An AI-generated review is not a substitute for actual participant feedback.

## Final form

Use SUBMISSION.md and the actual results in RESULTS.md. Include a public repository URL, accessible demo/test build, public YouTube video, selected track, actual tool feedback and a truthful account of work completed. Complete any required legal acceptance and final submission in your own Devpost account.
