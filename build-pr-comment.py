#!/usr/bin/env python3
"""Builds the PR comment body (as JSON on stdout) from gate-results.json, which ci-gate.py fills
in as each PRE-MERGE gate runs. A gate missing from the file is shown as "not run" - the pipeline
stopped at an earlier failing gate, or the stage was skipped. Never fails the build itself.

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

try:
    results = json.load(open("gate-results.json"))
except Exception:
    results = {}

rows = []
for key, label in GATES:
    gate = results.get(key)
    if gate is None:
        rows.append(f"| {label} | ⏭️ not run | |")
    else:
        icon = "✅ pass" if gate["passed"] else "❌ **FAIL**"
        rows.append(f"| {label} | {icon} | {gate['detail']} |")

ran = [results[k] for k, _ in GATES if k in results]
failed = any(not g["passed"] for g in ran)
complete = len(ran) == len(GATES)
if failed:
    verdict = "❌ PRE-MERGE gate failed - do not merge"
elif complete:
    verdict = "✅ PRE-MERGE gate passed"
else:
    verdict = "⚠️ PRE-MERGE gate incomplete - see build log"

commit = (os.environ.get("BUILD_SHA") or os.environ.get("GIT_COMMIT", ""))[:8]
build_url = os.environ.get("BUILD_URL", "")

lines = [
    f"### {verdict} for `{commit}`",
    "",
    "| Gate | Result | Details |",
    "|---|---|---|",
    *rows,
    "",
    f"[Full build log]({build_url})",
]

print(json.dumps({"body": "\n".join(lines)}))
