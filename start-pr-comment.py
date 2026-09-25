#!/usr/bin/env python3
"""Builds the "build started" PR comment body (JSON on stdout), posted immediately after checkout
so there's fast feedback with a link to the running build - edited in place with real results once
the pipeline finishes (see build-pr-comment.py + the PATCH call in the final stage)."""
import json
import os

commit = os.environ.get("GIT_COMMIT", "")[:8]
build_number = os.environ.get("BUILD_NUMBER", "?")
build_url = os.environ.get("BUILD_URL", "")

body = f"### \U0001F504 CI running for `{commit}`\n\n[Build #{build_number}]({build_url}) started…"
print(json.dumps({"body": body}))
