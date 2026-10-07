#!/usr/bin/env python3
"""Minimal Gitea API client for Jenkinsfile.build - same file as cloud.config's
jenkins/scripts/maintenance/terraform-ci/gitea.py (the terraform pipelines), keep them in sync.
Env: GITEA_API (e.g. https://git.00x097.com/api/v1), GITEA_REPO (owner/name), GITEA_TOKEN.

  gitea.py status <sha> <state> <context> <description>   set a commit status (target = BUILD_URL)
  gitea.py comment-post <pr> <body.json>                   post a PR comment, print its id
  gitea.py comment-patch <comment-id> <body.json>          edit a PR comment in place
  gitea.py label <pr> <name>                               add a label to a PR (created if missing)
  gitea.py pr-for-merge <sha>                              print {"number","head_sha"} of the PR
                                                           whose merge produced <sha>; exit 1 if none
  gitea.py context-state <sha> <context>                   print the latest state of a status context
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ["GITEA_API"].rstrip("/")
REPO = os.environ["GITEA_REPO"]
TOKEN = os.environ["GITEA_TOKEN"]


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Authorization", f"token {TOKEN}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        return json.loads(body) if body else None


def main(argv):
    cmd = argv[1]
    if cmd == "status":
        sha, state, context, description = argv[2:6]
        call("POST", f"/repos/{REPO}/statuses/{sha}", {
            "state": state,
            "context": context,
            "description": description[:140],
            "target_url": os.environ.get("BUILD_URL", ""),
        })
    elif cmd == "comment-post":
        with open(argv[3]) as f:
            body = json.load(f)
        print(call("POST", f"/repos/{REPO}/issues/{argv[2]}/comments", body)["id"])
    elif cmd == "comment-patch":
        with open(argv[3]) as f:
            body = json.load(f)
        call("PATCH", f"/repos/{REPO}/issues/comments/{argv[2]}", body)
    elif cmd == "label":
        pr, name = argv[2], argv[3]
        labels = call("GET", f"/repos/{REPO}/labels?limit=100") or []
        match = next((l for l in labels if l["name"] == name), None)
        if match is None:
            match = call("POST", f"/repos/{REPO}/labels", {
                "name": name, "color": "#1f6feb",
                "description": "Added by Jenkins CI",
            })
        call("POST", f"/repos/{REPO}/issues/{pr}/labels", {"labels": [match["id"]]})
    elif cmd == "pr-for-merge":
        sha = argv[2]
        for page in range(1, 6):
            prs = call("GET", f"/repos/{REPO}/pulls?state=closed&sort=recentupdate&limit=50&page={page}") or []
            for pr in prs:
                if pr.get("merged") and pr.get("merge_commit_sha") == sha:
                    print(json.dumps({"number": pr["number"], "head_sha": pr["head"]["sha"]}))
                    return 0
            if len(prs) < 50:
                break
        return 1
    elif cmd == "context-state":
        sha, context = argv[2], argv[3]
        statuses = call("GET", f"/repos/{REPO}/commits/{sha}/statuses?limit=50") or []
        latest = max((s for s in statuses if s.get("context") == context),
                     key=lambda s: s.get("id", 0), default=None)
        print(latest["status"] if latest else "missing")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except urllib.error.HTTPError as e:
        print(f"Gitea API error {e.code}: {e.read()[:300]!r}", file=sys.stderr)
        sys.exit(3)
