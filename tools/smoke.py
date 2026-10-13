#!/usr/bin/env python3
"""Smoke test of a deployed AIP stack (OPS-11). Standard library only.

    python3 tools/smoke.py https://<demo-host> [--timeout 10] [--banner "Demo, synthetic data only"]

Checks, in order, and exits 1 with one readable line per failure:

1. ``GET /api/v1/health/ready`` answers 200 (Postgres, Valkey, migrations at head);
2. the web root answers 200 with HTML that carries the demo banner;
3. ``GET /api/v1/me`` without a cookie answers 401 (nobody is signed in by default);
4. with ``--expect-commit SHA``: ``GET /api/v1/platform/version`` reports that commit (the deploy
   has rolled out).

Exit code 0 when every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_BANNER = "Demo, synthetic data only"
USER_AGENT = "aip-smoke/1"


@dataclass(frozen=True)
class Reply:
    status: int
    body: str


def fetch(url: str, timeout: float) -> Reply:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Reply(response.status, response.read(200_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return Reply(exc.code, exc.read(20_000).decode("utf-8", "replace"))


def run(
    base_url: str,
    *,
    timeout: float = 10.0,
    banner: str = DEFAULT_BANNER,
    expect_commit: str | None = None,
) -> list[str]:
    """Every failed check as a message; an empty list means the stack is healthy."""
    base = base_url.rstrip("/")
    if not base.startswith(("http://", "https://")):
        return [f"base URL must start with http:// or https://, got {base_url!r}"]
    failures: list[str] = []

    def check(path: str, expect: int, what: str) -> Reply | None:
        try:
            reply = fetch(base + path, timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            failures.append(f"{what}: GET {path} failed: {exc}")
            return None
        if reply.status != expect:
            snippet = " ".join(reply.body.split())[:160]
            failures.append(
                f"{what}: GET {path} answered {reply.status}, expected {expect}: {snippet}"
            )
            return None
        return reply

    check("/api/v1/health/ready", 200, "readiness")
    root = check("/", 200, "web root")
    if root is not None:
        if "<html" not in root.body.lower():
            failures.append("web root: the response is not HTML")
        elif banner and banner not in root.body:
            failures.append(f"web root: the demo banner {banner!r} is missing")
    check("/api/v1/me", 401, "anonymous /me")
    if expect_commit:
        version = check("/api/v1/platform/version", 200, "version")
        if version is not None:
            try:
                commit = json.loads(version.body).get("commit")
            except (ValueError, AttributeError):
                commit = None
            if commit != expect_commit:
                failures.append(
                    f"version: the API runs commit {commit!r}, expected {expect_commit!r}"
                )
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base_url", help="e.g. https://aip-demo.example.test")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--banner", default=DEFAULT_BANNER, help="text the web root must contain ('' to skip)"
    )
    parser.add_argument("--expect-commit", default=None, help="git SHA the API must report")
    args = parser.parse_args(argv)
    failures = run(
        args.base_url, timeout=args.timeout, banner=args.banner, expect_commit=args.expect_commit
    )
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    if failures:
        return 1
    print(f"OK {args.base_url}: ready, web with banner, anonymous /me is 401")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
