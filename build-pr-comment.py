#!/usr/bin/env python3
"""Builds the PR comment body (JSON on stdout) from gate-results.json, which ci-gate.py fills in
as each stage runs. Edits the comment start-pr-comment.py posted - same UX as cloud.config's
terraform-ci/build-pr-comment.py. Never fails the build itself.

Env: COMMIT_SHA, CI_MODE ("gate" on PR builds, "delivery" on the merged PR after a master build),
BUILD_RESULT (currentBuild.currentResult). A row missing from gate-results.json is "not run": the
pipeline stopped at an earlier failing stage, or the stage was skipped.

Same file in trading.ai.backend and trading.ai.frontend - keep them in sync."""
import json
import os

GATES = [
    ("secrets", "Secret scan (gitleaks)"),
    ("lint", "Lint"),
    ("tests", "Unit tests"),
    ("coverage", "Coverage threshold"),
    ("semgrep", "SAST (Semgrep)"),
    ("sca-fs", "SCA dependencies (Trivy fs)"),
    ("sca-image", "Image scan (Trivy image)"),
]
DELIVERY = [
    ("push", "Push image (by digest)"),
    ("sbom", "SBOM (CycloneDX)"),
    ("sign", "Signature (cosign sign + verify)"),
    ("deploy", "Deploy (cloud.config bump, ArgoCD)"),
    ("rollout", "Rollout + smoke test"),
    ("egress", "External egress (pods -> internet APIs)"),
    ("dast", "DAST (ZAP baseline)"),
]
# Rows only some pipelines record (the frontend's nginx needs no internet egress): shown when
# present, never counted as missing.
OPTIONAL = {"egress"}

mode = os.environ.get("CI_MODE", "gate")
build_result = os.environ.get("BUILD_RESULT", "")
commit = os.environ.get("COMMIT_SHA", "")[:8]
build_number = os.environ.get("BUILD_NUMBER", "?")
build_url = os.environ.get("BUILD_URL", "")

try:
    results = json.load(open("gate-results.json"))
except Exception:
    results = {}


def rows(checks):
    out = []
    for key, label in checks:
        gate = results.get(key)
        if gate is None and key in OPTIONAL:
            continue
        if gate is None:
            out.append(f"| {label} | ⏭️ _not run_ | |")
        else:
            icon = "✅ pass" if gate["passed"] else "❌ **FAIL**"
            out.append(f"| {label} | {icon} | {gate['detail']} |")
    return out


checks = GATES + (DELIVERY if mode == "delivery" else [])
failed = any(not results[k]["passed"] for k, _ in checks if k in results) or build_result in ("FAILURE", "ABORTED")
complete = all(k in results for k, _ in checks if k not in OPTIONAL)
what = "Delivery" if mode == "delivery" else "PRE-MERGE gate"
if failed:
    verdict = f"❌ {what} failed" + (" - do not merge" if mode == "gate" else "")
elif complete:
    verdict = "✅ Delivered to production" if mode == "delivery" else "✅ PRE-MERGE gate passed"
else:
    verdict = f"⚠️ {what} incomplete - see build log"

lines = [f"### {verdict} for `{commit}`", "", "| Check | Result | Details |", "|---|---|---|", *rows(GATES)]
if mode == "delivery":
    lines += ["", "**Post-merge / release**", "", "| Step | Result | Details |", "|---|---|---|", *rows(DELIVERY)]
    rollback = results.get("rollback")
    if rollback:
        lines += ["", f"↩️ **Rolled back:** {rollback['detail']}"]
lines += ["", f"[Build #{build_number}]({build_url})"]

print(json.dumps({"body": "\n".join(lines)}))
