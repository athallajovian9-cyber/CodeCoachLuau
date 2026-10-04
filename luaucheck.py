#!/usr/bin/env python3
"""CodeCoach Luau - tell a parent what is wrong with their kid's Roblox script.

    python luaucheck.py script.luau          check one script
    python luaucheck.py --folder .           every .luau underneath
    python luaucheck.py --watch --folder .   stay open, report on every save
    python luaucheck.py --run script.luau    also execute it (pure Luau only)

Static analysis by default, and that is deliberate rather than a limitation: a
Roblox script cannot run outside Roblox. Standalone `luau.exe` has no `game`,
no `workspace`, no `Instance` - so running a normal Studio script produces
"attempt to index nil with 'Players'", which is the tool inventing an error
about correct code. A parent told that would go looking for a bug that is not
there.

The silent failures - the ones a kid cannot google - need no execution to find.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import coach as C
import report as RP

HERE = Path(__file__).resolve().parent
TOOLS = HERE / "tools"

SKIP_DIRS = {"__pycache__", ".git", "node_modules", "build", "dist", "tools"}


def find_scripts(folder: Path) -> list[Path]:
    out = []
    for ext in ("*.luau", "*.lua"):
        for p in sorted(folder.rglob(ext)):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            out.append(p)
    return sorted(set(out))


def main() -> int:
    ap = argparse.ArgumentParser(description="CodeCoach - help for parents, for Luau")
    ap.add_argument("target", help="a .luau file, or a folder")
    ap.add_argument("--folder", action="store_true", help="treat target as a folder")
    ap.add_argument("--watch", action="store_true", help="report again on every save")
    ap.add_argument("--run", action="store_true",
                    help="also execute it. Refused for scripts that use Roblox APIs")
    ap.add_argument("--kid", action="store_true", default=True,
                    help="use kid-friendly language (default: True)")
    ap.add_argument("--parent", dest="kid", action="store_false",
                    help="use parent mode language")
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"  no such path: {target}")
        return 2

    if not (TOOLS / "luau-ast.exe").is_file():
        print("  tools/luau-ast.exe is missing.")
        print("  Download the Luau release and put luau.exe and luau-ast.exe in tools/.")
        return 3

    engine = C.Coach(tools=TOOLS, state_dir=HERE)

    def one_pass() -> int:
        now = time.time()
        if target.is_dir():
            checks = [engine.examine(p, now=now, run=args.run)
                      for p in find_scripts(target)]
            print(RP.summary(checks, now, kid_mode=args.kid))
            worst = 0
            for check, rec in checks:
                if not check.clean:
                    print(RP.render(check, rec, now, kid_mode=args.kid))
                    worst = 1
            return worst

        check, rec = engine.examine(target, now=now, run=args.run)
        print(RP.render(check, rec, now, kid_mode=args.kid))
        return 0 if check.clean else 1

    if args.watch:
        print(f"  watching {target}")
        print("  reports on every save · Ctrl-C to stop")
        seen: dict[str, float] = {}
        try:
            while True:
                current = {}
                files = [target] if target.is_file() else find_scripts(target)
                for p in files:
                    try:
                        current[str(p)] = p.stat().st_mtime
                    except OSError:
                        continue
                if current != seen:
                    seen = current
                    one_pass()
                    engine.save()
                time.sleep(max(0.2, args.interval))
        except KeyboardInterrupt:
            print()
            print("  stopped. The stuck timer is saved, so it continues next time.")
            engine.save()
            return 0

    rc = one_pass()
    engine.save()
    return rc


if __name__ == "__main__":
    sys.exit(main())