# Architecture

```
 Slack export   GitHub API   Jira export   Notion/Drive md
        \            |            |             /
         +-----------+-----+------+------------+
                           v
                  messages.jsonl  {id, author, date, source, text, acl?}
                           |
                           v
         Extraction   (Nemotron Nano)   domain prompt -> claims
         Linking      (Nemotron Super)  depends_on / supersedes / contradicts
                           |
                           v
        +----------- Decision graph (networkx, graph.json) -----------+
        |  nodes: claims {subject, value, kind, owner, date, source,   |
        |         reason, confidence, status, acl}                     |
        |  edges: depends_on, supersedes, contradicts, justified_by    |
        +---------+----------------------------------------+-----------+
                  |                                        |
      candidates (cheap, no LLM)                     ask / retrieve
      conflicts + load-bearing claims            lexical (+ NVIDIA embeddings)
                  |                              + graph warnings + ACL filter
                  v                                        |
   Verifier (read-only, optional sandbox)                  v
     tech_choice -> manifests in repo                 answer + citations
     commitment  -> roadmap.json                      (Nemotron Super)
     web         -> Tavily (parent process only)
                  |
                  v
        Judge (Nemotron Ultra, rule fallback)
        verdict: valid | stale | contradicted | needs_review
                  |
                  v
        Propagation along depends_on  ->  status written back to graph
                  |
        +---------+-----------+------------------+
        v                     v                  v
     Web UI / API        Slack /why        Nightly sweep (Serverless Job)
     (Serverless         slash command     Slack summary, GitHub issues
      Endpoint)
```

## Why the pieces are shaped this way

**Generic claim schema.** `subject` (what it is about), `value` (what was chosen or promised), `kind` (which verifier applies), plus provenance and status. Engineering decisions and customer commitments use the same schema, graph, judge and UI. A new domain means a prompt in `domains.py` and a verifier in `verify.VERIFIERS`.

**Cheap structure before expensive reasoning.** Conflict detection, supersession chains and impact are graph operations. Nemotron Ultra only sees candidates that survive them. `dledger eval` measures the saving (57% of the verifications of a full sweep) and the cost (silent drift is missed, so the nightly sweep verifies everything).

**Verification is evidence, not opinion.** Verifiers return structured evidence with a reference (`requirements.txt:3`, `roadmap.json:sso`, a URL). The judge reasons over that evidence. If the model call fails or returns invalid JSON, the deterministic rule verdict is used and the failure is recorded in the rationale. The model-eval harness runs in strict mode so failures are never hidden by the fallback.

**Web evidence is conservative.** A deprecation signal near a mention of the technology adds contradicting evidence, which turns a clean repo verdict into `needs_review`. Finding nothing is neutral and never counts as support.

**Isolation.** Verifiers only read. With `DLEDGER_SANDBOX_CMD` set, each runs in a child process (for example under OpenShell/NemoClaw with a read-only mount) with a scrubbed environment, so API keys are not visible to it. Network access (Tavily) happens in the trusted parent.

**Permissions.** Messages carry an `acl`; private Slack channels become `channel:<name>`. Retrieval filters on the asker's groups, and warnings never name a claim the asker cannot see. The Slack slash command answers with public decisions only.

**Verdict status machine.** `active` (unchecked) to `valid`, `contradicted`/`stale`, or `needs_review`. Failure propagates to dependents as `needs_review`, including ones that were previously `valid`.
