"""Render a check as one screen a parent can read.

Written for an adult who does not program. The order is deliberate:

  1. Do I need to do anything?        <- answered first, in one line
  2. Should I go over right now?      <- the stuck signal, before the detail
  3. What is actually wrong           <- plain language, no jargon
  4. What I could say to them         <- the whole point
  5. What to type into a search box   <- if they would rather look it up

Every field comes from the two analysis modules; nothing is invented here. This
module only decides what a parent sees first, which is most of whether they can
use it at all.
"""
from __future__ import annotations

from coach import Check, StuckRecord, human_duration, is_stuck, stuck_for

WIDTH = 64
RULE = "  " + "-" * WIDTH


def _wrap(text: str, indent: str = "    ", width: int = WIDTH - 4) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(indent + cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(indent + cur)
    return lines


def _headline(check: Check) -> tuple[str, str]:
    """(verdict word, one-line explanation). The parent reads only this if they
    read nothing else."""
    if check.timed_out:
        return "PROGRAM NEVER STOPS", "It is still running. Usually a loop that never ends."
    if check.clean:
        return "NOTHING WRONG", "The program runs and does what it says."
    problems = len(check.silent) + (1 if check.error else 0)
    if check.error and not check.silent:
        return "ONE ERROR TO FIX", "Python stopped and explained why."
    if check.silent and not check.error:
        word = "ONE THING TO FIX" if problems == 1 else f"{problems} THINGS TO FIX"
        return word, "It runs, but something below is not doing anything."
    return f"{problems} THINGS TO FIX", "There is an error, and something else is silent."


def render(check: Check, rec: StuckRecord, now: float) -> str:
    lines: list[str] = []
    name = check.path.replace("\\", "/").rsplit("/", 1)[-1]

    lines.append("")
    lines.append("  " + name)
    lines.append(RULE)

    verdict, why = _headline(check)
    lines.append(f"  {verdict}")
    lines.append(f"  {why}")

    # --- the stuck signal, deliberately above the detail -------------------
    if rec.signature and not check.clean:
        elapsed = stuck_for(rec, now)
        if is_stuck(rec, now):
            lines.append("")
            lines.append(f"  STUCK FOR {human_duration(elapsed).upper()}")
            lines.append("  This is not 'not trying'. Same problem, "
                         f"{rec.checks} checks in a row.")
            lines.append("  This is the moment to walk over and ask a question.")
        elif elapsed >= 60:
            lines.append("")
            lines.append(f"  (same problem for {human_duration(elapsed)} - leave them to it)")
    lines.append("")

    if getattr(check, "used_roblox_api", False):
        lines.append("  (this one talks to Roblox, so it was read but not run -")
        lines.append("   the Roblox parts only exist inside Studio)")
        lines.append("")

    if check.clean:
        if check.output.strip():
            out = check.output.strip().splitlines()
            lines.append("  It printed:")
            for o in out[:4]:
                lines.append("    " + o[:WIDTH])
            if len(out) > 4:
                lines.append(f"    ... and {len(out) - 4} more lines")
        lines.append("")
        return "\n".join(lines)

    # --- what is wrong ------------------------------------------------------
    if check.timed_out:
        lines.append("  WHAT IS WRONG")
        for l in _wrap("The program was still running after several seconds. That almost "
                       "always means a loop whose condition never becomes false. Nothing is "
                       "broken in a way Python can report - it is just waiting forever."):
            lines.append(l)
        lines.append("")
        lines.append("  WHAT YOU COULD SAY")
        for l in _wrap('"What is supposed to make that loop stop? Does that ever happen?"'):
            lines.append(l)
        lines.append("")

    if check.error:
        lines.append("  PYTHON SAID")
        lines.append("    " + (check.error.expert or check.error.exc)[:WIDTH])
        lines.append("")
        lines.append("  WHAT IS WRONG")
        lines.append("    " + check.error.title)
        for l in _wrap(check.error.plain):
            lines.append(l)
        lines.append("")
        lines.append("  WHAT YOU COULD SAY")
        for l in _wrap('"' + check.error.parent_says + '"'):
            lines.append(l)
        if check.error.hint:
            lines.append("")
            lines.append("  WHERE TO LOOK")
            for l in _wrap(check.error.hint):
                lines.append(l)
        if check.error.search:
            lines.append("")
            lines.append("  IF THEY WANT TO SEARCH")
            lines.append("    " + check.error.search[:WIDTH])
        lines.append("")

    for i, f in enumerate(check.silent):
        if i:
            lines.append(RULE)
            lines.append("")
        lines.append("  SILENT - no error, it just does nothing")
        lines.append("")
        lines.append(f"  Line {f.line}: {f.title}")
        for l in _wrap(f.plain):
            lines.append(l)
        lines.append("")
        lines.append("  WHAT YOU COULD SAY")
        for l in _wrap('"' + f.parent_says + '"'):
            lines.append(l)
        if f.search:
            lines.append("")
            lines.append("  IF THEY WANT TO SEARCH")
            lines.append("    " + f.search[:WIDTH])
        lines.append("")

    return "\n".join(lines)


def summary(checks: list[tuple[Check, StuckRecord]], now: float) -> str:
    """One line per file, for a parent glancing at a whole project."""
    lines = ["", "  " + "=" * WIDTH]
    if not checks:
        lines.append("  no Python files found")
        lines.append("  " + "=" * WIDTH)
        return "\n".join(lines)

    clean = sum(1 for c, _ in checks if c.clean)
    stuck = sum(1 for c, r in checks if r.signature and is_stuck(r, now))
    lines.append(f"  {len(checks)} file(s)  ·  {clean} clean  ·  {stuck} stuck")
    lines.append("  " + "=" * WIDTH)
    for c, r in checks:
        name = c.path.replace("\\", "/").rsplit("/", 1)[-1]
        if c.clean:
            mark = "ok"
        elif r.signature and is_stuck(r, now):
            mark = f"STUCK {human_duration(stuck_for(r, now))}"
        else:
            n = len(c.silent) + (1 if c.error else 0)
            mark = f"{n} to fix"
        lines.append(f"    {name:<28} {mark}")
    lines.append("")
    return "\n".join(lines)
