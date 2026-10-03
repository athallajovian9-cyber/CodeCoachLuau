"""Turn a Luau error into something a parent can use.

Grounding: every pattern here was produced by actually running Luau and copying
the message out. None of it is from memory of what Luau "probably" says.

Luau's errors arrive as:

    C:/path/file.luau:2: attempt to index nil with 'x'
    stacktrace:
    ...

so the first job is finding the `path:line: message` line and stripping the path
- a parent does not need their own folder path, and a search engine certainly
does not.

Written for a non-programmer. Two fields carry the weight: `parent_says`, which
is the sentence an adult can say out loud, and `search`, which is the query that
actually finds the answer rather than the raw message.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# `path:line: message` - the only line that matters. Luau follows it with a
# stacktrace the parent will never need.
_ERR_LINE = re.compile(r"^[^\s:][^:]*:(\d+):\s*(?P<msg>.+)$", re.M)
_ANY_LINE = re.compile(r"^.*?:(\d+):\s*(?P<msg>.+)$", re.M)

# Anything that makes a query worse.
_PATH = re.compile(r"[A-Za-z]:\\[^\s\"']*|/[^\s\"']*")
_QUOTED_OWN = re.compile(r"'([A-Za-z_][A-Za-z0-9_]*)'")
_SITE = re.compile(r"\bsite:[^\s]+|\bRoblox\b", re.I)


@dataclass
class Explanation:
    exc: str
    title: str
    plain: str
    concept: str
    hint: str
    parent_says: str
    search: str
    raw: str = ""
    notes: list[str] = field(default_factory=list)


def _clean(msg: str) -> str:
    m = _PATH.sub("", msg)
    m = re.sub(r"\s+", " ", m).strip().strip("'\"")
    return m


class Translator:
    def __init__(self):
        # First match wins, so the specific patterns come before the general.
        self.rules = [
            (r"attempt to index nil with '(?P<k>[^']*)'", self._index_nil),
            (r"attempt to index nil", self._index_nil_generic),
            (r"attempt to index (?P<t>\w+) with", self._index_wrong_type),
            (r"attempt to call a nil value", self._call_nil),
            (r"attempt to call a (?P<t>\w+) value", self._call_wrong_type),
            (r"attempt to concatenate", self._concat),
            (r"attempt to perform arithmetic", self._arithmetic),
            (r"attempt to compare (?P<a>\w+) [<>]=? (?P<b>\w+)", self._compare),
            (r"attempt to iterate over a (?P<t>\w+) value", self._iterate),
            (r"attempt to get length of a nil value", self._length_nil),
            (r"Expected identifier when parsing expression, got '(?P<got>[^']*)'", self._expected),
            (r"Expected (?P<want>'[^']*'|\w+) .*got (?P<got>'[^']*'|\w+)", self._expected),
            (r"unexpected symbol near '(?P<got>[^']*)'", self._unexpected),
            (r"'end' expected", self._missing_end),
            (r"Malformed number", self._bad_number),
            (r"Unknown global", self._unknown_global),
            (r"Unknown require", self._unknown_require),
            (r"Type '(?P<got>[^']+)' could not be converted into '(?P<want>[^']+)'", self._type_convert),
            (r"Expected type '(?P<want>[^']+)', got '(?P<got>[^']+)'", self._type_mismatch),
        ]

    def explain(self, text: str) -> Explanation | None:
        """Explain an error. None if this is not an error at all.

        Luau errors carry a `path:line: message` line. Program OUTPUT does not.
        Without requiring that shape, a program that simply prints "1" gets
        translated into "Luau stopped: 1" - which is nonsense, and would tell a
        parent their working code is broken. Anything without the shape is not
        an error and gets no explanation.
        """
        if not text or not text.strip():
            return None

        m = _ERR_LINE.search(text) or _ANY_LINE.search(text)
        if not m:
            return None
        msg, line = m.group("msg").strip(), m.group(1)
        if not msg:
            return None

        for pattern, builder in self.rules:
            mm = re.search(pattern, msg)
            if mm:
                out = builder(msg, mm.groupdict())
                out.raw = f"{msg}  (line {line})" if line else msg
                return out

        return Explanation(
            exc="Luau error",
            title="Luau stopped",
            plain=f"Luau reported: {_clean(msg)}",
            concept="reading an error message",
            hint="The message names what it tried to do and what it found instead.",
            parent_says="Read it out loud - what did it try to do, and what did it find?",
            search="luau Roblox " + _clean(msg),
            raw=f"{msg}  (line {line})" if line else msg,
        )

    # ------------------------------------------------------------- builders

    def _index_nil(self, msg, g):
        k = g.get("k", "that")
        what = f"'{k}'" if k else "a value"
        return Explanation(
            exc="attempt to index nil",
            title=f"Asking for {what} on something that is empty",
            plain=(f"The code asks for {what} on a value, but that value is nil - meaning "
                   "nothing is there. In Roblox this is usually an object that has not "
                   "loaded yet, or a path like script.Parent that points at nothing."),
            concept="nil means 'nothing here', and calling into it stops the script",
            hint=("If it is a Roblox object, use :WaitForChild(\"Name\") instead of .Name. "
                  "If it is a table, check the key exists before reading it."),
            parent_says=f"Does {what} actually exist at that point, or might it not be there yet?",
            search="Roblox attempt to index nil with -script.Parent",
            notes=["The single most common Roblox error. Almost always a missing WaitForChild."],
        )

    def _index_nil_generic(self, msg, g):
        return Explanation(
            exc="attempt to index nil",
            title="Reading from something that is empty",
            plain=("The code reads from a value that is nil - nothing is there. "
                   "In Roblox this is usually an object that has not loaded yet."),
            concept="nil means 'nothing here'",
            hint='Use :WaitForChild("Name") when the object might not exist yet.',
            parent_says="Could that thing not exist yet when this line runs?",
            search="Roblox attempt to index nil",
        )

    def _index_wrong_type(self, msg, g):
        t = g.get("t", "a value")
        return Explanation(
            exc="attempt to index",
            title=f"Square brackets used on a {t}",
            plain=(f"The code uses [ ] or . on a {t}. Only a table can be looked into "
                   "that way. A number or a string is a single value, not a container."),
            concept="only tables hold other values",
            hint="If it should be a table, check what was actually assigned to it.",
            parent_says=f"Is that supposed to be a table? What was put into it?",
            search=f"Roblox attempt to index {t} with",
        )

    def _call_nil(self, msg, g):
        return Explanation(
            exc="attempt to call a nil value",
            title="Running something that is not a function",
            plain=("The code puts brackets after a name to run it, but that name holds "
                   "nil - nothing. Often a typo in the function name, or a function "
                   "that was never defined in this scope."),
            concept="calling a function means running the thing the name points at",
            hint="Check the spelling matches the definition exactly. Luau is case-sensitive.",
            parent_says="Does that name match the function they wrote? Compare the spelling.",
            search="Luau attempt to call a nil value",
        )

    def _call_wrong_type(self, msg, g):
        t = g.get("t", "a value")
        return Explanation(
            exc="attempt to call",
            title=f"Running a {t} as if it were a function",
            plain=f"The name holds a {t}, and brackets were put after it to run it.",
            concept="calling a function means running the thing the name points at",
            hint="If the value is a function, it was written without brackets to store it.",
            parent_says="Is that a function, or a value that happens to have that name?",
            search=f"Luau attempt to call a {t} value",
        )

    def _concat(self, msg, g):
        return Explanation(
            exc="attempt to concatenate",
            title="Joining text to something that is not text",
            plain=("The .. joins text together. It cannot join a number or nil directly "
                   "- Luau will not guess what you meant."),
            concept="joins need both sides to be text",
            hint="Use tostring(value) to convert it first: \"Score: \" .. tostring(score)",
            parent_says="Which of those two things is a number, and which is text?",
            search="Roblox attempt to concatenate -tostring",
        )

    def _arithmetic(self, msg, g):
        return Explanation(
            exc="attempt to perform arithmetic",
            title="Doing maths on something that is not a number",
            plain="A maths symbol was used on a value that is not a number - often nil or a string.",
            concept="maths needs numbers on both sides",
            hint="Check what is in the variable. A number typed by a player arrives as text and needs tonumber().",
            parent_says="Is that value actually a number, or could it be text or nothing?",
            search="Roblox attempt to perform arithmetic on",
        )

    def _compare(self, msg, g):
        a, b = g.get("a", "one thing"), g.get("b", "another")
        return Explanation(
            exc="attempt to compare",
            title=f"Comparing a {a} to a {b}",
            plain=(f"A comparison like < or > was used between a {a} and a {b}. "
                   "Luau will not decide an order between unlike things."),
            concept="comparisons need both sides to be the same kind of value",
            hint="Make sure both sides are numbers, or both are text.",
            parent_says="What are the two things being compared, and are they the same kind?",
            search="Roblox attempt to compare nil",
        )

    def _iterate(self, msg, g):
        t = g.get("t", "a value")
        return Explanation(
            exc="attempt to iterate",
            title=f"Looping over a {t} that is not a table",
            plain=f"A for loop was given a {t}. Loops can only go through a table.",
            concept="loops walk through containers",
            hint="Use a counted loop for numbers: for i = 1, 10 do",
            parent_says="Is that a table, or a single value? What did they want to loop through?",
            search="Roblox attempt to iterate over a number value",
        )

    def _length_nil(self, msg, g):
        return Explanation(
            exc="attempt to get length of a nil value",
            title="Asking the length of something empty",
            plain="The # symbol asks how long something is, and the value is nil.",
            concept="length only works on tables and text",
            hint="Check the table exists before using # on it.",
            parent_says="Does that table exist yet at that point?",
            search="Roblox attempt to get length of a nil value",
        )

    def _expected(self, msg, g):
        got = _clean(g.get("got", "")).strip("'\"")
        return Explanation(
            exc="SyntaxError",
            title="Luau cannot read this line",
            plain=("Something is not written the shape Luau expects. The reported line is "
                   "where it gave up, which is often one line after the real mistake."),
            concept="syntax: the exact shape the language requires",
            hint="Check brackets, quotes, 'then' after if, and 'do' after for and while.",
            parent_says="Is there a word or a bracket missing on that line, or the one before it?",
            search="Roblox syntax error Expected identifier",
            raw=f"{msg}",
            notes=["The line number points at where Luau noticed, not always the mistake."],
        )

    def _unexpected(self, msg, g):
        got = _clean(g.get("got", "")).strip("'\"")
        return Explanation(
            exc="SyntaxError",
            title="An unexpected symbol",
            plain=f"Luau found '{got}' where it did not expect it.",
            concept="syntax: the exact shape the language requires",
            hint="Often an unclosed bracket or quote above this line.",
            parent_says="Is there a bracket or quote left open just above that line?",
            search="Roblox unexpected symbol near",
        )

    def _missing_end(self, msg, g):
        return Explanation(
            exc="SyntaxError",
            title="A block was never closed",
            plain=("Something opened with function, if, for, while or do and never got "
                   "its matching 'end'."),
            concept="blocks open and close in pairs",
            hint="Count the openers and the 'end's.",
            parent_says="Does every for and if and function have an 'end'?",
            search="Roblox 'end' expected",
        )

    def _bad_number(self, msg, g):
        return Explanation(
            exc="SyntaxError",
            title="A number is written badly",
            plain="A number has a stray character in it, or a letter.",
            concept="numbers have an exact written form",
            hint="Check for a typo in the digits, or a missing space around an operator.",
            parent_says="Does anything in that number look like a typo?",
            search="Roblox Malformed number",
        )

    def _unknown_global(self, msg, g):
        return Explanation(
            exc="UnknownGlobal",
            title="A name that does not exist",
            plain="A name is used that Luau cannot find anywhere.",
            concept="names must be declared before they are used",
            hint="Add `local` in front of it the first time, or check the spelling.",
            parent_says="Where was that name first created? Does the spelling match?",
            search="Luau unknown global",
        )

    def _unknown_require(self, msg, g):
        return Explanation(
            exc="UnknownRequire",
            title="A module could not be found",
            plain="The script asks for a module by path and nothing is at that path.",
            concept="modules are reached by a path through the game",
            hint="Check the path in require() points at a real ModuleScript.",
            parent_says="Does that path actually exist in the Explorer?",
            search="Roblox require module path",
        )

    def _type_convert(self, msg, g):
        return Explanation(
            exc="TypeError", title="A value of the wrong type",
            plain="A value was passed where a different type was expected, and Luau "
                  "will not convert it silently.",
            concept="values have types, and they must match",
            hint="Convert it: tonumber(), tostring(), or check what is being passed.",
            parent_says="Is the value the same kind as the function expects?",
            search="Luau type could not be converted",
        )

    def _type_mismatch(self, msg, g):
        want, got = g.get("want", "one type"), g.get("got", "another")
        return Explanation(
            exc="TypeError", title=f"Expected a {want}, got a {got}",
            plain=f"A {got} was used where a {want} is required.",
            concept="values have types, and they must match",
            hint="Check what is actually being passed at the call.",
            parent_says=f"Where does that {got} come from, and why is it not a {want}?",
            search=f"Luau Expected type {want} got {got}",
        )


_DEFAULT = Translator()


def explain(text: str) -> Explanation | None:
    return _DEFAULT.explain(text)