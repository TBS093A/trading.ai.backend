# trading.ai backend

FastAPI REST API, sync controller and Celery workers of trading.ai - one image, the mode is picked by
`SERVICE_MODE` (`rest-api-controller`, `sync-controller`, `rest-api-celery-worker`, see `docker-entrypoint.sh`).

## CI/CD and supply chain

Every change goes through `Jenkinsfile.build` (Jenkins, same model as the terraform pipelines in `cloud.config`):

```
PR -> PRE-MERGE gate -> merge -> POST-MERGE -> RELEASE -> production
```

- **PRE-MERGE** (every PR, required status `jenkins/pre-merge` on `master`): gitleaks, lint, unit tests, coverage threshold,
  Semgrep, Trivy (dependencies, then the built image - scanned before it is ever pushed). The gate scripts come
  from `master`, not from the PR under test. Results land in a `jenkins-bot` comment on the PR.
- **POST-MERGE** (only for a `master` commit that is the merge of a PR with a passing gate): push by digest,
  CycloneDX SBOM, cosign signature verified against [`cosign.pub`](cosign.pub).
- **RELEASE**: image tag bumped in `cloud.config` (ArgoCD), rollout + smoke test, automatic rollback by reverting
  the bump, OWASP ZAP baseline. Progress goes to a comment on the merged PR.

Verify a deployed image yourself:

```bash
cosign verify --key cosign.pub --insecure-ignore-tlog=true registry.00x097.com/trading-ai-backend@sha256:<digest>
```

(`--insecure-ignore-tlog`: signatures are not uploaded to the public Rekor log - private registry.)
