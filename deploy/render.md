# Publish the judge demo on Render

A `render.yaml` Blueprint is included. This is a prepared deployment configuration, not a confirmed deployment.

1. Create a Render account at https://dashboard.render.com/ and connect the GitHub account containing the project.
2. Select **New > Blueprint**, connect the `decision-ledger` repository and select branch `main`. Render reads `render.yaml` from the repository root.
3. Supply `NEBIUS_API_KEY` privately in Render. Replace the key posted in chat before using it for the hosted demo.
4. Supply `DLEDGER_DEMO_PASSWORD`: choose a separate strong password for judge access. The username is `judge`. Do not use the Nebius key as the demo password.
5. Review that the service uses the Free plan, Docker runtime and `/healthz` health check. The three model roles are prefilled with the verified NVIDIA model ID. Deploy the Blueprint.
6. After the build completes, open the assigned HTTPS URL in another browser. Sign in as `judge` using your demo password. Run a full check and verify the execution summary reports real model calls.
7. Put the URL and demo username/password in the private testing instructions for judges. Do not put the API key there. The demo sign-in protects the UI and API; only the health endpoint is public.

Free instances sleep after 15 minutes idle and take about a minute to wake. Their local state is disposable. This Blueprint uses in-memory state (`DLEDGER_PERSIST=0`) and synthetic sample data: a restart restores the fixture, not prior edits. Do not claim durable hosted history for this deployment. The local persistent mode remains available separately. A scale-to-zero demo cannot watch while asleep.

The fixture already represents a migrated repository. Use it to demonstrate checks and resolution in the hosted app. Use the local fresh Git demo for the baseline → migration → watcher video sequence. The hosted fixture is not a live GitHub PR integration.

Shared sign-in is a small-demo access gate, not multi-user authorization. Do not host private company data with it. Protect your model budget by sharing the demo credentials only with intended testers/judges. `/healthz` verifies the process is running; it does not probe model access.

No local Docker engine is required for this path: Render builds the repository's Dockerfile.

Official documentation verified October 28, 2026:
- https://render.com/docs/infrastructure-as-code
- https://render.com/docs/configure-environment-variables
- https://render.com/docs/free
