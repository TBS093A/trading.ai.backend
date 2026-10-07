#!/usr/bin/env python3
"""Builds the "build started" PR comment body (JSON on stdout), posted right after checkout so
there's fast feedback with a link to the running build - edited in place with the results table
once the pipeline finishes (build-pr-comment.py). Same shape as cloud.config's
terraform-ci/start-pr-comment.py. Same file in trading.ai.backend and trading.ai.frontend.

Env: COMMIT_SHA, CI_TITLE ("CI running" on PRs, "Delivery running" on the merged PR)."""
import json
import os

commit = os.environ.get("COMMIT_SHA", "")[:8]
build_number = os.environ.get("BUILD_NUMBER", "?")
build_url = os.environ.get("BUILD_URL", "")
title = os.environ.get("CI_TITLE", "CI running")

body = f"### \U0001F504 {title} for `{commit}`\n\n[Build #{build_number}]({build_url}) started…"
print(json.dumps({"body": body}))
