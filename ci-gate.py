#!/usr/bin/env python3
"""Hard quality/security gates for Jenkinsfile.build - each subcommand reads one report file,
prints a one-line verdict, appends it to gate-results.json (rendered in the PR comment by
build-pr-comment.py) and exits 1 when the gate fails, which fails the Jenkins stage.

Unlike build-pr-comment.py, a missing/unparseable report here is a FAIL, not "not run": the stage
that should have produced it ran (or the gate wouldn't be called), so no report means no evidence.

Same file in trading.ai.backend and trading.ai.frontend - keep them in sync.

  ci-gate.py coverage <coverage.xml | coverage-summary.json> --min 15
  ci-gate.py semgrep  semgrep-report.json --fail-on ERROR
  ci-gate.py trivy    trivy-fs-report.json --fail-on CRITICAL[,HIGH] [--ignore-unfixed]
  ci-gate.py zap      zap-out/zap-report.json --fail-on-risk 3
  ci-gate.py result   <gate> <exit code> "<detail>"   (record a tool's own pass/fail, e.g. lint)
"""
import argparse
import collections
import json
import re
import sys

RESULTS_FILE = "gate-results.json"


def record(gate, passed, detail):
    try:
        results = json.load(open(RESULTS_FILE))
    except Exception:
        results = {}
    results[gate] = {"passed": passed, "detail": detail}
    json.dump(results, open(RESULTS_FILE, "w"), indent=2)
    print(f"[gate:{gate}] {'PASS' if passed else 'FAIL'} - {detail}")
    return 0 if passed else 1


def coverage_percent(path):
    if path.endswith(".json"):
        pct = json.load(open(path))["total"]["lines"]["pct"]
        # Jest reports "Unknown" when there is nothing to instrument (zero test files).
        return 0.0 if isinstance(pct, str) else float(pct)
    # Cobertura XML: only the root element's line-rate is needed, a regex avoids pulling in an
    # XML parser (and Semgrep's use-defused-xml finding) for a file we generated ourselves.
    with open(path) as f:
        match = re.search(r'<coverage[^>]*\sline-rate="([0-9.]+)"', f.read())
    return float(match.group(1)) * 100


def gate_coverage(args):
    pct = round(coverage_percent(args.report), 1)
    return record("coverage", pct >= args.min, f"line coverage {pct}% (min {args.min}%)")


def gate_semgrep(args):
    fail_on = {s.strip().upper() for s in args.fail_on.split(",")}
    results = json.load(open(args.report)).get("results", [])
    blocking = [r for r in results if r["extra"]["severity"].upper() in fail_on]
    for r in blocking:
        print(f"  {r['extra']['severity']} {r['check_id']} {r['path']}:{r['start']['line']}")
    return record(
        "semgrep",
        not blocking,
        f"{len(blocking)} blocking ({'/'.join(sorted(fail_on))}) of {len(results)} findings",
    )


def gate_trivy(args):
    fail_on = {s.strip().upper() for s in args.fail_on.split(",")}
    report = json.load(open(args.report))
    vulns = [
        (result.get("Target", ""), v)
        for result in report.get("Results") or []
        for v in result.get("Vulnerabilities") or []
    ]
    blocking = [
        (target, v) for target, v in vulns
        if v["Severity"] in fail_on and (v.get("FixedVersion") or not args.ignore_unfixed)
    ]
    for target, v in blocking:
        fixed = v.get("FixedVersion") or "no fix"
        print(f"  {v['Severity']} {v['VulnerabilityID']} {v['PkgName']} {v.get('InstalledVersion', '')} -> {fixed} ({target})")
    counts = collections.Counter(v["Severity"] for _, v in vulns)
    summary = ", ".join(f"{counts[s]} {s}" for s in ("CRITICAL", "HIGH") if counts[s]) or "0 HIGH/CRITICAL"
    policy = "/".join(sorted(fail_on)) + (" with fix" if args.ignore_unfixed else "")
    return record(args.name, not blocking, f"{len(blocking)} blocking ({policy}); found {summary}")


def gate_zap(args):
    alerts = [
        a for site in json.load(open(args.report)).get("site", [])
        for a in site.get("alerts", [])
    ]
    blocking = [a for a in alerts if int(a.get("riskcode", 0)) >= args.fail_on_risk]
    for a in blocking:
        print(f"  risk={a.get('riskcode')} {a.get('alert')}")
    warnings = sum(1 for a in alerts if int(a.get("riskcode", 0)) > 0)
    return record("dast", not blocking, f"{len(blocking)} blocking (risk >= {args.fail_on_risk}); {warnings} warnings")


def gate_result(args):
    return record(args.name, args.exit_code == 0, args.detail)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="gate", required=True)

    p = sub.add_parser("coverage")
    p.add_argument("report")
    p.add_argument("--min", type=float, required=True)
    p.set_defaults(fn=gate_coverage)

    p = sub.add_parser("semgrep")
    p.add_argument("report")
    p.add_argument("--fail-on", default="ERROR")
    p.set_defaults(fn=gate_semgrep)

    p = sub.add_parser("trivy")
    p.add_argument("report")
    p.add_argument("--name", default="trivy")
    p.add_argument("--fail-on", default="CRITICAL")
    p.add_argument("--ignore-unfixed", action="store_true")
    p.set_defaults(fn=gate_trivy)

    p = sub.add_parser("zap")
    p.add_argument("report")
    p.add_argument("--fail-on-risk", type=int, default=3)
    p.set_defaults(fn=gate_zap)

    p = sub.add_parser("result")
    p.add_argument("name")
    p.add_argument("exit_code", type=int)
    p.add_argument("detail")
    p.set_defaults(fn=gate_result)

    args = parser.parse_args()
    try:
        return args.fn(args)
    except Exception as e:
        return record(getattr(args, "name", args.gate), False, f"report unreadable: {e}")


if __name__ == "__main__":
    sys.exit(main())
