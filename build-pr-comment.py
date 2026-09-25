#!/usr/bin/env python3
"""Builds the PR comment body (as JSON on stdout) from this build's scan/test report files.
Missing/unparseable files are reported as "not run" rather than failing - a stage upstream may
have been skipped or genuinely produced nothing, and a broken comment shouldn't fail the build."""
import json
import os
import xml.etree.ElementTree as ET


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None


def coverage_percent(path):
    root = ET.parse(path).getroot()
    return round(float(root.attrib["line-rate"]) * 100, 1)


def semgrep_findings(path):
    d = json.load(open(path))
    return len(d.get("results", []))


def trivy_high_critical(path):
    d = json.load(open(path))
    return sum(len(r.get("Vulnerabilities") or []) for r in (d.get("Results") or []))


def zap_warnings(path):
    d = json.load(open(path))
    count = 0
    for site in d.get("site", []):
        for alert in site.get("alerts", []):
            if str(alert.get("riskcode", "0")) != "0":
                count += 1
    return count


def fmt(value, unit=""):
    return f"{value}{unit}" if value is not None else "_not run_"


coverage = safe(coverage_percent, "coverage.xml")
semgrep = safe(semgrep_findings, "semgrep-report.json")
trivy_fs = safe(trivy_high_critical, "trivy-fs-report.json")
trivy_image = safe(trivy_high_critical, "trivy-image-report.json")
zap = safe(zap_warnings, "zap-out/zap-report.json")

commit = os.environ.get("GIT_COMMIT", "")[:8]
build_url = os.environ.get("BUILD_URL", "")

lines = [
    f"### CI results for `{commit}`",
    "",
    "| Check | Result |",
    "|---|---|",
    f"| Tests + coverage | {fmt(coverage, '%')} |",
    f"| SAST (Semgrep) | {fmt(semgrep, ' findings')} |",
    f"| SCA source (Trivy fs) | {fmt(trivy_fs, ' HIGH/CRITICAL')} |",
    f"| SCA image (Trivy image) | {fmt(trivy_image, ' HIGH/CRITICAL')} |",
    f"| DAST (ZAP baseline) | {fmt(zap, ' warnings')} |",
    "",
    f"[Full build log]({build_url})",
]

print(json.dumps({"body": "\n".join(lines)}))
