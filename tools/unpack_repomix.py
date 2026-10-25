#!/usr/bin/env python3
"""Rebuild a working tree from a repomix XML export (so an AI session can run the tests).

Usage: python3 tools/unpack_repomix.py repomix-output.xml /tmp/repo
Stdlib only. Refuses paths that would escape the destination directory.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FILE_BLOCK = re.compile(r'<file path="([^"]+)">\n(.*?)\n</file>', re.DOTALL)


def unpack(source: Path, dest: Path) -> int:
    text = source.read_text(encoding="utf-8")
    root = dest.resolve()
    count = 0
    for match in FILE_BLOCK.finditer(text):
        target = (root / match.group(1)).resolve()
        if root not in target.parents:
            raise SystemExit(f"refusing to write outside {root}: {match.group(1)}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(match.group(2) + "\n", encoding="utf-8")
        count += 1
    return count


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    count = unpack(Path(argv[1]), Path(argv[2]))
    print(f"unpacked {count} files into {argv[2]}")
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
