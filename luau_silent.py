"""Silent failures in Luau: code that runs, throws nothing, and does nothing.

Two advantages over the Python version of this tool:

1.  **The parser resolves scopes for us.** `luau-ast` emits every local READ with
    a pointer back to the exact declaration it refers to. So "declared and never
    read" is exact rather than an approximation - the Python version had to
    ignore scoping and accept a wider net to avoid false positives.

2.  **Luau has silent failures Python does not.** Passing too many arguments to a
    function is silently accepted. Reading an undefined global gives nil instead
    of raising. Both are invisible at runtime and both are caught here.

Requires `luau-ast.exe` (from the Luau releases) to produce the tree. No
execution: parsing only, so this is safe on anything and cannot hang.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Finding:
    kind: str
    line: int
    name: str
    title: str
    plain: str
    parent_says: str
    fix_hint: str
    search: str = ""


def _line_of(loc: str) -> int:
    """Luau locations look like '3,6 - 3,11'. Line numbers are 0-based."""
    try:
        start = loc.split(" - ")[0]
        return int(start.split(",")[0]) + 1     # report 1-based, like an editor
    except (ValueError, IndexError, AttributeError):
        return 0


def _throwaway(name: str) -> bool:
    return name.startswith("_")


class _Tree:
    """Walk the JSON tree and collect what the checks need."""

    def __init__(self, root: dict):
        self.root = root
        self.declared: dict[str, dict] = {}      # location -> declaration node
        self.param_locations: set[str] = set()   # AstLocals that are function parameters
        self.read_locations: set[str] = set()    # every AstExprLocal target
        self.called_names: set[str] = set()
        self.call_nodes: list[dict] = []
        self.functions: list[tuple[str, dict]] = []   # (name, AstExprFunction)
        self.function_local_locations: set[str] = set()   # the AstLocal naming each function
        self.loops: list[dict] = []
        self.ifs: list[dict] = []
        self.globals_read: dict[str, int] = {}
        self.known_globals = {
            # Luau / Roblox standard library. A missing entry here would produce
            # a false positive, so this errs towards being generous.
            "print", "warn", "error", "assert", "pcall", "xpcall", "type", "typeof",
            "tostring", "tonumber", "ipairs", "pairs", "next", "select", "unpack",
            "rawget", "rawset", "rawequal", "rawlen", "setmetatable", "getmetatable",
            "require", "newproxy", "collectgarbage", "tick", "time", "os", "math",
            "string", "table", "coroutine", "bit32", "utf8", "debug", "task", "wait",
            "spawn", "delay", "game", "workspace", "script", "Instance", "Vector3",
            "Vector2", "CFrame", "Color3", "UDim", "UDim2", "BrickColor", "Enum",
            "TweenInfo", "Ray", "Region3", "NumberRange", "NumberSequence",
            "ColorSequence", "Random", "shared", "_G", "self",
        }
        self._walk(root)

    def _walk(self, node):
        if isinstance(node, list):
            for item in node:
                self._walk(item)
            return
        if not isinstance(node, dict):
            return

        t = node.get("type")

        if t == "AstLocal":
            loc = node.get("location", "")
            if loc:
                self.declared[loc] = node
            return

        # Function parameters live in `args`, not `params` - reading the wrong
        # key made every parameter count zero, so every call looked like it
        # passed too many values, and every parameter looked unused.
        if t == "AstExprFunction":
            for a in (node.get("args") or []):
                if isinstance(a, dict) and a.get("type") == "AstLocal":
                    loc = a.get("location", "")
                    if loc:
                        self.param_locations.add(loc)
                        self.declared[loc] = a

        if t == "AstExprLocal":
            inner = node.get("local") or {}
            loc = inner.get("location", "")
            if loc:
                self.read_locations.add(loc)
            return

        if t == "AstExprGlobal":
            name = node.get("global", "")
            if name and name not in self.known_globals:
                self.globals_read[name] = _line_of(node.get("location", ""))

        if t == "AstExprCall":
            self.call_nodes.append(node)
            fn = node.get("func") or {}
            if fn.get("type") == "AstExprGlobal":
                self.called_names.add(fn.get("global", ""))
            elif fn.get("type") == "AstExprLocal":
                self.called_names.add((fn.get("local") or {}).get("name", ""))
            elif fn.get("type") == "AstExprIndexName":
                self.called_names.add(fn.get("index", ""))
            elif fn.get("type") == "AstExprFunction":
                pass

        if t in ("AstStatLocalFunction", "AstStatFunction"):
            fn = node.get("func") or {}
            name = (node.get("name") or {})
            nm = name.get("name") if isinstance(name, dict) else str(name or "")
            if nm:
                self.functions.append((nm, fn))
                # Remember which AstLocal names this function, so the
                # declared-never-read check can leave it alone. Both checks
                # firing on the same line counted one problem twice and used the
                # wrong wording - "set and then never used" for something that is
                # a function.
                if isinstance(name, dict):
                    loc = name.get("location", "")
                    if loc:
                        self.function_local_locations.add(loc)

        if t == "AstStatLocal":
            for v in (node.get("vars") or []):
                if v.get("type") == "AstLocal":
                    loc = v.get("location", "")
                    if loc:
                        self.declared[loc] = v

        if t in ("AstStatFor", "AstStatForIn", "AstStatWhile", "AstStatRepeat"):
            self.loops.append(node)

        if t == "AstStatIf":
            self.ifs.append(node)

        for k, v in node.items():
            if k in ("location", "local", "luauType"):
                continue
            self._walk(v)


def _const_value(node) -> tuple[bool, object]:
    """(is_constant, value) for the literal expression types."""
    if not isinstance(node, dict):
        return False, None
    t = node.get("type")
    if t == "AstExprConstantNumber":
        return True, node.get("value")
    if t == "AstExprConstantBool":
        return True, node.get("value")
    if t == "AstExprConstantString":
        return True, node.get("value")
    if t == "AstExprConstantNil":
        return True, None
    return False, None


def analyse_ast(tree_json: str, source: str = "") -> list[Finding]:
    """All checks over one parsed file."""
    try:
        root = json.loads(tree_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(root, dict):
        return []

    try:
        t = _Tree(root)
    except Exception:                                            # noqa: BLE001
        # A tree shape we do not understand must produce nothing rather than a
        # wrong answer. A false positive here is worse than a miss.
        return []

    out: list[Finding] = []

    # --- declared and never read ------------------------------------------
    # Exact, because the parser told us which declaration every read refers to.
    for loc, node in t.declared.items():
        name = node.get("name", "")
        if not name or _throwaway(name):
            continue
        # A parameter is stored by the call, not by the code. Flagging unused
        # parameters would drown the signal - they are normal and constant.
        if loc in t.param_locations:
            continue
        # A function gets its own message, and only one of them.
        if loc in t.function_local_locations:
            continue
        if loc in t.read_locations:
            continue
        # A declared function that is never called is a separate, better message.
        if name in t.called_names:
            continue

        out.append(Finding(
            kind="assigned_never_used",
            line=_line_of(loc),
            name=name,
            title=f"'{name}' is set and then never used",
            plain=(f"The line creates '{name}', but nothing later reads it. The script "
                   "runs and says nothing - which usually means the value was meant to "
                   "go somewhere, or the name was spelled differently from the one "
                   "being used."),
            parent_says=(f"Can they find '{name}' again anywhere below that line? "
                         "Compare the spelling with the name they meant to change."),
            fix_hint=(f"Either '{name}' is a typo for a name used elsewhere, or the value "
                      "needs using. Nothing is broken at runtime - it is a silent no-op."),
            search="Luau local variable unused",
        ))

    # --- a function written and never called ------------------------------
    for name, fn in t.functions:
        if _throwaway(name) or name in t.called_names:
            continue
        out.append(Finding(
            kind="function_never_called",
            line=_line_of(fn.get("location", "")),
            name=name,
            title=f"'{name}' is written but never called",
            plain=(f"The function '{name}' is defined, and nothing ever runs it. It will "
                   "do nothing until something calls it."),
            parent_says=f"Is '{name}' supposed to be used? Where does the script call it?",
            fix_hint=f"Call it: {name}()  - and check the spelling matches exactly.",
            search="Luau function never called",
        ))

    # --- loops that cannot run -------------------------------------------
    for loop in t.loops:
        lt = loop.get("type")
        loc = loop.get("location", "")

        if lt == "AstStatFor":
            ok_from, frm = _const_value(loop.get("from"))
            ok_to, to = _const_value(loop.get("to"))
            ok_step, step = _const_value(loop.get("step"))
            if ok_from and ok_to:
                s = step if ok_step and step else 1
                try:
                    empty = (s > 0 and frm > to) or (s < 0 and frm < to)
                except TypeError:
                    empty = False
                if empty:
                    out.append(Finding(
                        kind="loop_never_runs",
                        line=_line_of(loc),
                        name="",
                        title="This loop can never run",
                        plain=(f"The loop counts from {frm} to {to}, which it can never "
                               "reach, so the lines inside never happen even once."),
                        parent_says="How many times is that loop meant to go round? Is that number ever reached?",
                        fix_hint="Check the start and end numbers - the end must be reachable from the start.",
                    ))

        elif lt == "AstStatWhile":
            ok, val = _const_value(loop.get("condition"))
            if ok and not val:
                out.append(Finding(
                    kind="loop_never_runs",
                    line=_line_of(loc),
                    name="",
                    title="This loop can never run",
                    plain="The condition is false to begin with, so the inside never happens.",
                    parent_says="What has to be true for this loop to start? Is it true at the start?",
                    fix_hint="Set the condition so it is true when the loop should begin.",
                ))

    # --- always-true or always-false if ----------------------------------
    for node in t.ifs:
        ok, val = _const_value(node.get("condition"))
        if ok and isinstance(val, bool):
            out.append(Finding(
                kind="constant_condition",
                line=_line_of(node.get("location", "")),
                name="",
                title=f"This if is always {'true' if val else 'false'}",
                plain=("The condition is a fixed value, so one of the two branches never "
                       "runs. Usually left over from testing, or a comparison replaced "
                       "by a plain true or false."),
                parent_says="Was that meant to be a test between two things, rather than just true or false?",
                fix_hint="Make it a real comparison, or delete the branch that can never run.",
            ))

    # --- too many arguments, which Luau silently allows -------------------
    # `f(1,2,3)` where f takes one parameter produces NO error at runtime - the
    # extra values are just discarded. Invisible, and a very common beginner
    # mistake when they expect it to be passed on.
    param_counts: dict[str, int] = {}
    for name, fn in t.functions:
        # Parameters are `args`; varargs are a `vararg` BOOLEAN, not a list
        # entry. Reading `params` gave null, so every function looked like it
        # took zero arguments and every call looked wrong.
        args = fn.get("args") or []
        varargs = bool(fn.get("vararg"))
        param_counts[name] = -1 if varargs else len(args) if isinstance(args, list) else 0

    for call in t.call_nodes:
        fn = call.get("func") or {}
        if fn.get("type") != "AstExprLocal":
            continue
        name = (fn.get("local") or {}).get("name", "")
        if not name or name not in param_counts:
            continue
        want = param_counts[name]
        if want < 0:
            continue
        args = call.get("args") or []
        if len(args) > want:
            out.append(Finding(
                kind="too_many_arguments",
                line=_line_of(call.get("location", "")),
                name=name,
                title=f"'{name}' is given {len(args)} values but takes {want}",
                plain=(f"The call passes {len(args)} values and the function only accepts "
                       f"{want}. Luau does not complain - the extra ones are quietly "
                       "thrown away, so the script runs and the values never arrive."),
                parent_says=f"How many values does {name} accept, and how many are being handed over?",
                fix_hint=f"Either remove the extra values, or add parameters to {name}.",
                search="Luau too many arguments silently ignored",
            ))

    # --- globals that do not exist ---------------------------------------
    # Reading an undefined global gives nil, not an error - so this only matters
    # when the result is used, which is the common case for a typo'd name.
    for name, line in t.globals_read.items():
        out.append(Finding(
            kind="undefined_global",
            line=line,
            name=name,
            title=f"'{name}' is not defined anywhere",
            plain=(f"The script uses the name '{name}', which Luau cannot find. Reading "
                   "an unknown name gives nil instead of an error, so the script "
                   "continues with nothing and fails somewhere later."),
            parent_says=f"Did they mean to write 'local {name} = ...' first, or is the spelling different?",
            fix_hint=f"If it should be theirs, add:  local {name} = ...  "
                     "If it is a Roblox thing, check the capital letters.",
            search="Luau unknown global nil",
        ))

    out.sort(key=lambda f: (f.line, f.kind))
    return out


class Checker:
    """Runs luau-ast and analyses the result. Parsing only, never execution."""

    def __init__(self, ast_exe: str | Path):
        self.ast_exe = str(ast_exe)

    def available(self) -> bool:
        return Path(self.ast_exe).is_file()

    def ast_for(self, path: str | Path) -> str:
        """The parse tree, or "" if Luau could not parse the file.

        The return code matters: luau-ast exits 1 on a syntax error but STILL
        writes a partial tree to stdout. Trusting stdout alone meant a broken
        file produced findings from a half-built tree - the tool reporting
        nonsense about code that does not even compile.
        """
        try:
            p = subprocess.run([self.ast_exe, str(path)], capture_output=True,
                               text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return ""
        if p.returncode != 0:
            return ""
        return p.stdout or ""

    def analyse(self, path: str | Path) -> list[Finding]:
        tree = self.ast_for(path)
        if not tree.strip():
            # No tree means a syntax error, which belongs to the error
            # translator. Reporting both at once is noise.
            return []
        return analyse_ast(tree)


def analyse_source(ast_exe: str | Path, path: str | Path) -> list[Finding]:
    return Checker(ast_exe).analyse(path)