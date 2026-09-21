#!/usr/bin/env python3
"""Sync the deployable code from the repo into server-bundle/ (FTP source).

The repo's vmimporter/ is the single source of truth. server-bundle/vmimporter/
is ONLY a staging area for FTP upload to the server — it is not tracked in git
and must never be edited directly.

Usage:
  python3 tools/sync-bundle.py            # copy repo -> bundle, then verify
  python3 tools/sync-bundle.py --check    # verify only, copy nothing (exit 1 on diff)

After running, FTP the files it lists to /home/manouka/web/libertidance.com/import-bundle/
— preserving the exact sub-paths shown (vmimporter/ files go INTO vmimporter/).
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_PKG = ROOT / "vmimporter"
SRC_CLI = ROOT / "importer.py"
DST = ROOT / "server-bundle"

#: files that must be identical between repo and bundle
TRACKED = [(SRC_CLI, DST / "importer.py")]
TRACKED += [(p, DST / "vmimporter" / p.name)
            for p in sorted(SRC_PKG.glob("*.py"))]
TRACKED += [(ROOT / "requirements.txt", DST / "requirements.txt")]

#: engine files found at the bundle ROOT mean somebody uploaded to the wrong
#: FTP folder (this exact mistake happened once — the launcher got overwritten)
STRAY_AT_ROOT = ["config.py", "db.py", "slug.py", "cli.py", "images.py",
                 "repos.py", "products_csv.py", "reporting.py"]


def compare() -> list[tuple[Path, Path]]:
    """Return (src, dst) pairs that differ or are missing at dst."""
    bad = []
    for src, dst in TRACKED:
        if not dst.is_file() or not filecmp.cmp(src, dst, shallow=False):
            bad.append((src, dst))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify only; do not copy (exit 1 on any difference)")
    args = ap.parse_args()

    if not DST.is_dir():
        print(f"ERROR: {DST} does not exist", file=sys.stderr)
        return 2

    problems = []

    stray = [p for p in STRAY_AT_ROOT if (DST / p).is_file()]
    if stray:
        problems.append(
            "stray engine files at bundle ROOT (uploaded to the wrong FTP "
            f"folder) — delete them on the server and locally: {', '.join(stray)}")

    bad = compare()
    if args.check:
        if bad:
            for src, dst in bad:
                rel = dst.relative_to(ROOT)
                state = "MISSING" if not dst.is_file() else "DIFFERS"
                print(f"  {state:8} {rel}")
            print(f"{len(bad)} file(s) differ. Run tools/sync-bundle.py (no --check) to fix.")
            rc = 1
        else:
            print("bundle code is identical to the repo")
            rc = 0
    else:
        for src, dst in bad:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            rel = dst.relative_to(ROOT)
            state = "NEW" if not dst.is_file() else "UPDATED"
            print(f"  copied   {rel}")
        print(f"synced {len(bad)} file(s)")

    # after a sync, the bundle must be byte-identical
    still_bad = compare()
    if still_bad and not args.check:
        for src, dst in still_bad:
            problems.append(f"copy failed: {dst.relative_to(ROOT)}")
        rc = 1
    elif not args.check:
        rc = 0

    if bad and not args.check:
        print("\nFTP upload list (server: /home/manouka/web/libertidance.com/import-bundle/):")
        for src, dst in bad:
            print(f"  {dst.relative_to(ROOT)}")
        print("REMEMBER: vmimporter/* files go into import-bundle/vmimporter/, "
              "importer.py goes to the bundle ROOT.")

    for p in problems:
        print(f"PROBLEM: {p}", file=sys.stderr)
    return 1 if problems else rc


if __name__ == "__main__":
    sys.exit(main())
