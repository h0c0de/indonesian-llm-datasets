#!/usr/bin/env python3
"""Check every URL in the markdown files of this repository.

Reports dead links grouped by file, writes optional JSON/markdown reports,
and can push a summary to Telegram.

Exit status is 1 when at least one link is dead, so CI can fail on it.
Bot-walled responses (403/429) and 5xx are reported separately: a 403 from
Cloudflare says nothing about whether the page exists.

No third-party dependencies.

Usage:
    python3 scripts/check_links.py
    python3 scripts/check_links.py --json-out report.json --markdown-out report.md
    python3 scripts/check_links.py --telegram          # needs env vars, see below
    python3 scripts/check_links.py --telegram --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
TRAILING = ".,;:"
CLOSERS = ")}]"
PAIRS = {")": "(", "}": "{", "]": "["}
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 awesome-links/1.0"
)
BLOCKED_STATUS = {403, 429}
# A host that does not resolve is gone. A refused/unroutable connection only
# proves this machine could not reach it, so it must not fail the run.
DNS_MARKERS = ("no address associated", "name or service not known", "nodename nor servname")


def clean(url: str) -> str:
    """Drop punctuation that markdown/BibTeX glued onto the URL.

    Trailing closers are only removed while they are unbalanced, so
    https://en.wikipedia.org/wiki/A_(b) survives intact.
    """
    url = url.rstrip(TRAILING)
    while url and url[-1] in CLOSERS:
        closer = url[-1]
        if url.count(closer) <= url.count(PAIRS[closer]):
            break
        url = url[:-1]
    return url


def collect(root: str) -> dict[str, set[str]]:
    """Map url -> set of relative file paths mentioning it."""
    found: dict[str, set[str]] = defaultdict(set)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules"}]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for raw in URL_RE.findall(text):
                found[clean(raw)].add(rel)
    return found


def check(url: str, timeout: float, attempts: int) -> tuple[str, int | None, str | None]:
    context = ssl.create_default_context()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last: tuple[int | None, str | None] = (None, None)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                return "ok", response.status, None
        except urllib.error.HTTPError as exc:
            if exc.code in BLOCKED_STATUS and attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
                last = (exc.code, None)
                continue
            if exc.code >= 500 and attempt + 1 < attempts:
                time.sleep(1 + attempt)
                last = (exc.code, None)
                continue
            if exc.code in BLOCKED_STATUS:
                return "blocked", exc.code, None
            if exc.code >= 500:
                return "error", exc.code, "server error"
            return "dead", exc.code, None
        except Exception as exc:  # URLError, socket.timeout, ssl errors
            detail = f"{type(exc).__name__}: {exc}"
            if attempt + 1 < attempts:
                time.sleep(1 + attempt)
                last = (None, detail)
                continue
            if any(marker in detail.lower() for marker in DNS_MARKERS):
                return "dead", None, detail
            return "unreachable", None, detail
    return "dead", last[0], last[1]


def render_markdown(results, counts, dead) -> str:
    lines = [
        "# Link check",
        "",
        f"Checked {len(results)} unique URLs across markdown files.",
        "",
        "| result | count |",
        "| --- | --- |",
    ]
    for key in ("ok", "blocked", "unreachable", "dead", "error"):
        lines.append(f"| {key} | {counts.get(key, 0)} |")
    if not dead:
        lines += ["", "No dead links."]
        return "\n".join(lines) + "\n"
    lines += ["", f"## Dead links ({len(dead)})", ""]
    by_file: dict[str, list[str]] = defaultdict(list)
    for url, status, detail, files in dead:
        suffix = f"HTTP {status}" if status else (detail or "no response")
        for path in files:
            by_file[path].append(f"- `{url}` — {suffix}")
    for path in sorted(by_file):
        lines += [f"### `{path}`", ""] + sorted(by_file[path]) + [""]
    return "\n".join(lines).rstrip() + "\n"


def telegram_send(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")
    if len(text) > 4000:
        text = text[:3990] + "\n…"
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    ).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root (default: .)")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--json-out")
    parser.add_argument("--markdown-out")
    parser.add_argument("--telegram", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="print the Telegram message instead of sending it")
    args = parser.parse_args()

    urls = collect(args.root)
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        outcomes = list(
            pool.map(lambda u: (u,) + check(u, args.timeout, args.attempts), sorted(urls))
        )

    results = []
    dead = []
    for url, state, status, detail in outcomes:
        results.append(
            {"url": url, "state": state, "status": status, "detail": detail, "files": sorted(urls[url])}
        )
        if state == "dead":
            dead.append((url, status, detail, sorted(urls[url])))

    counts = Counter(r["state"] for r in results)
    report = render_markdown(results, counts, dead)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump({"counts": dict(counts), "results": results}, handle, indent=1)
    if args.markdown_out:
        with open(args.markdown_out, "w", encoding="utf-8") as handle:
            handle.write(report)

    print(report, end="")
    print(f"\nTook {time.time() - started:.1f}s", file=sys.stderr)

    if args.telegram:
        summary = [
            f"Link check: {counts.get('dead', 0)} dead / {len(results)} URLs",
            f"blocked (403/429): {counts.get('blocked', 0)}",
            f"unreachable from the runner: {counts.get('unreachable', 0)}",
        ]
        if dead:
            summary += ["", "Worst offenders:"] + [f"- {u}" for u, _, _, _ in dead[:15]]
        message = "\n".join(summary)
        if args.dry_run:
            print("--- telegram message ---\n" + message)
        else:
            telegram_send(message)

    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
