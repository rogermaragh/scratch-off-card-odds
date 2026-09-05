#!/usr/bin/env python3
"""Point the app at the GitHub Pages URL this repo publishes to.

Derives the URL from `git remote get-url origin`, so there is nothing to look
up by hand and nothing to keep in sync. Pass a URL explicitly to override.

    python3 Scripts/set_data_url.py
    python3 Scripts/set_data_url.py https://cdn.example.com/lottery-data/
    python3 Scripts/set_data_url.py --clear
"""

import re
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "Sources" / "Data" / "Config.swift"


def pages_url_from_git():
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    # git@github.com:owner/repo.git or https://github.com/owner/repo(.git)
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote)
    if not match:
        return None
    owner, repo = match.groups()
    # A directory, not a file. The app appends "core.json" and
    # "scratchers/<CODE>.json" to whatever it is given, so a URL ending in a
    # filename produces ".../lottery.json/core.json" -- a 404 on every launch,
    # and a silent one, because automatic refreshes do not report failures.
    # lottery.json is also the wrong file: it is the raw scrape, and the app
    # ships the split files.
    return f"https://{owner.lower()}.github.io/{repo}/"


def main():
    args = [a for a in sys.argv[1:] if a]

    if args and args[0] == "--clear":
        url = ""
    elif args:
        url = args[0]
    else:
        url = pages_url_from_git() or ""
        if not url:
            print(
                "No GitHub remote found. Push this repo to GitHub first, or pass\n"
                "a URL explicitly: python3 Scripts/set_data_url.py <url>",
                file=sys.stderr,
            )
            return 1

    if url and re.search(r"\.(json|js|txt)$", url, re.I):
        print(
            f"That URL ends in a filename: {url}\n"
            "The app appends core.json and scratchers/<CODE>.json to whatever\n"
            "it is given, so this would request .../core.json twice over.\n"
            "Pass the directory that contains them instead.",
            file=sys.stderr,
        )
        return 1

    source = CONFIG.read_text()
    updated, count = re.subn(
        r'(static let defaultDataURL = ")[^"]*(")',
        lambda m: m.group(1) + url + m.group(2),
        source,
    )
    if count != 1:
        print(f"Could not find defaultDataURL in {CONFIG}", file=sys.stderr)
        return 1

    CONFIG.write_text(updated)
    print(f"defaultDataURL = {url or '(empty — remote refresh disabled)'}")
    if url:
        print("Enable Pages once: Settings > Pages > Source: GitHub Actions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
