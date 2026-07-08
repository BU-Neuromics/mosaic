#!/usr/bin/env python3
"""Extract one release's section from CHANGELOG.md.

Usage: extract_release_notes.py X.Y.Z [changelog-path]

Prints the body of the ``## vX.Y.Z — …`` section (everything up to the next
``## `` heading). Exits non-zero when the version has no section, so the
release workflow fails loudly instead of publishing an empty release note —
retitle ``## [Unreleased]`` before tagging (see RELEASING.md).
"""

import re
import sys
from pathlib import Path


def extract(version: str, text: str) -> str | None:
    pattern = re.compile(
        rf"^## v{re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    version = sys.argv[1].lstrip("v")
    changelog = Path(sys.argv[2] if len(sys.argv) > 2 else "CHANGELOG.md")
    notes = extract(version, changelog.read_text(encoding="utf-8"))
    if notes is None:
        print(f"error: no '## v{version}' section in {changelog}", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
