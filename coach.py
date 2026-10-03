"""The check loop for Luau, and the reason it defaults to static analysis.

**A Roblox script cannot run outside Roblox.** Standalone `luau.exe` has no
`game`, no `workspace`, no `Instance`. Running a normal Studio script under it
gives "attempt to index nil with 'Players'" - an error that is entirely the
tool's fault, about code that is perfectly correct. Reporting that to a parent
would be worse than useless.

So the default here is STATIC: parse the file with `luau-ast`, find the silent
failures, never execute. That is also where the value is - the silent class is
the one a kid cannot google, and it needs no execution to find.

`--run` is available for pure-Luau scripts with no Roblox API calls, and it says
plainly what it is doing.

The stuck tracker and the report rendering are shared with the Python version of
this tool; they are language-agnostic and take a `Check`.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import luau_errors as E
import luau_silent as S

STUCK_AFTER = 15 * 60
RUN_TIMEOUT = 5.0

# Calls that only exist inside Roblox. A file using any of these cannot be run
# under the standalone interpreter, and attempting it invents errors.
_ROBLOX_CALL = re.compile(
    r"\b(Instance\.new|game\s*\.|workspace\s*\.|script\s*\.|Vector3\.new|"
    r"CFrame\.new|Color3\.|UDim2\.|TweenInfo\.|Ray\.new|Enum\.|"
    r"game:GetService|:WaitForChild|:FindFirstChild|:GetChildren)\b")


@dataclass
class Check:
    path: str
    ran: bool
    output: str
    error: E.Explanation | None
    silent: list[S.Finding] = field(default_factory=list)
    timed_out: bool = False
    used_roblox_api: bool = False

    @property
    def clean(self) -> bool:
        return not self.error and not self.silent and not self.timed_out


# ------------------------------------------------------------- stuck tracking

@dataclass
class StuckRecord:
    signature: str = ""
    first_seen: float = 0.0
    last_seen: float = 0.0
    checks: int = 0


def signature(check: Check) -> str:
    """A stable id for "the same problem".

    Based on WHAT is wrong, not on line numbers, so editing whitespace to "try
    something" does not read as progress. If it changed on every edit the stuck
    clock would reset constantly and never fire.
    """
    parts: list[str] = []
    if check.error:
        parts.append("err:" + check.error.title)
    for f in check.silent:
        parts.append("silent:" + f.kind + ":" + f.name)
    if check.timed_out:
        parts.append("timeout")
    if not parts:
        return ""
    return hashlib.sha256("|".join(sorted(parts)).encode("utf-8")).hexdigest()[:16]


def update_record(prev: StuckRecord | None, sig: str, now: float) -> StuckRecord:
    if not sig:
        return StuckRecord()
    if prev is None or prev.signature != sig:
        return StuckRecord(signature=sig, first_seen=now, last_seen=now, checks=1)
    return StuckRecord(signature=sig, first_seen=prev.first_seen,
                       last_seen=now, checks=prev.checks + 1)


def stuck_for(rec: StuckRecord, now: float) -> float:
    if not rec.signature or rec.first_seen <= 0:
        return 0.0
    return max(0.0, now - rec.first_seen)


def is_stuck(rec: StuckRecord, now: float, threshold: float = STUCK_AFTER) -> bool:
    return stuck_for(rec, now) >= threshold


def human_duration(seconds: float) -> str:
    s = int(max(0, seconds))
    if s < 60:
        return f"{s} second{'s' if s != 1 else ''}"
    m = s // 60
    if m < 60:
        return f"{m} minute{'s' if m != 1 else ''}"
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if m else f"{h} hour{'s' if h != 1 else ''}"


# ------------------------------------------------------------------- running

def uses_roblox_api(source: str) -> bool:
    return bool(_ROBLOX_CALL.search(source))


def run_program(lua_exe: Path, path: Path, timeout: float = RUN_TIMEOUT):
    try:
        p = subprocess.run([str(lua_exe), str(path)], capture_output=True,
                           text=True, timeout=timeout, input="")
        return True, p.stdout or "", p.stderr or "", False
    except subprocess.TimeoutExpired:
        return False, "", "", True
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "", str(exc), False


def check_file(path: str | Path, tools: Path, run: bool = False) -> Check:
    p = Path(path)
    try:
        source = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return Check(str(p), False, "", E.Explanation(
            exc="FileNotFoundError", title="That file could not be opened",
            plain=str(exc), concept="", hint="",
            parent_says="Is the path right?", search=""))

    silent_findings = S.Checker(tools / "luau-ast.exe").analyse(p)
    roblox = uses_roblox_api(source)

    # Never run a file that talks to Roblox: the interpreter has none of those
    # globals, so every one of them becomes a fabricated error.
    if not run or roblox:
        return Check(str(p), False, "", None, silent_findings, used_roblox_api=roblox)

    ran, out, err, timed_out = run_program(tools / "luau.exe", p)
    return Check(
        path=str(p), ran=ran, output=out,
        error=E.explain(err) if err.strip() else None,
        silent=silent_findings, timed_out=timed_out, used_roblox_api=False,
    )


# ------------------------------------------------------------ the coach loop

class Coach:
    def __init__(self, tools: Path, state_dir: str | Path | None = None):
        self.tools = Path(tools)
        self.state_path = Path(state_dir or ".") / "codecoach_luau_state.json"
        self.records: dict[str, StuckRecord] = self._load()

    def _load(self) -> dict[str, StuckRecord]:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        out: dict[str, StuckRecord] = {}
        for k, v in (raw.get("files") or {}).items():
            try:
                out[k] = StuckRecord(**v)
            except TypeError:
                continue
        return out

    def save(self) -> None:
        try:
            self.state_path.write_text(
                json.dumps({"version": 1,
                            "files": {k: asdict(v) for k, v in self.records.items()}},
                           indent=2), encoding="utf-8")
        except OSError:
            pass

    def examine(self, path: str | Path, now: float | None = None,
                run: bool = False) -> tuple[Check, StuckRecord]:
        t = time.time() if now is None else now
        check = check_file(path, self.tools, run=run)
        sig = signature(check)
        rec = update_record(self.records.get(str(path)), sig, t)
        if sig:
            self.records[str(path)] = rec
        else:
            self.records.pop(str(path), None)
        return check, rec