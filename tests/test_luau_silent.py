"""Tests for the Luau silent-failure detector.

Two suites, and the second matters more:

  TestFindsSilentFailures    the bugs it must catch
  TestCorrectCodeIsSilent    working scripts that must produce NOTHING

A detector that cries wolf on working code gets turned off within a day.

Every case is parsed by the real `luau-ast.exe` - the tree comes from Luau, not
from a fixture I wrote by hand.

    python run_tests.py
"""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import luau_silent as LS

AST = HERE / "tools" / "luau-ast.exe"
WORK = Path(tempfile.gettempdir()) / "codecoach_luau_ast"
CHECKER = LS.Checker(AST)


def analyse(source: str) -> list[LS.Finding]:
    WORK.mkdir(parents=True, exist_ok=True)
    p = WORK / "s.luau"
    p.write_text(textwrap.dedent(source), encoding="utf-8")
    return CHECKER.analyse(p)


def kinds(source: str) -> list[str]:
    return [f.kind for f in analyse(source)]


def names(source: str) -> list[str]:
    return [f.name for f in analyse(source)]


@unittest.skipUnless(AST.is_file(), "luau-ast.exe not present in tools/")
class TestFindsSilentFailures(unittest.TestCase):

    def test_the_typo_that_started_all_this(self):
        src = """
            local score = 0
            local scor = score + 10
            print(score)
        """
        found = analyse(src)
        self.assertEqual([f.name for f in found], ["scor"])
        self.assertEqual(found[0].kind, "assigned_never_used")
        self.assertIn("never used", found[0].title)

    def test_assigned_but_never_read(self):
        self.assertEqual(names("""
            local total = 5
            local other = total + 1
            print(total)
        """), ["other"])

    def test_a_used_local_is_not_reported(self):
        self.assertEqual(analyse("""
            local x = 10
            print(x)
        """), [])

    def test_function_written_and_never_called(self):
        found = analyse("""
            local function jump()
                return 1
            end
            print("done")
        """)
        self.assertIn("function_never_called", [f.kind for f in found])
        self.assertIn("jump", [f.name for f in found])

    def test_counted_loop_that_can_never_run(self):
        self.assertIn("loop_never_runs", kinds("""
            for i = 1, 0 do
                print(i)
            end
        """))

    def test_counted_loop_backwards(self):
        # from 5 to 1 with the default step of +1 never reaches.
        self.assertIn("loop_never_runs", kinds("""
            for i = 5, 1 do
                print(i)
            end
        """))

    def test_a_real_counted_loop_is_fine(self):
        self.assertNotIn("loop_never_runs", kinds("""
            for i = 1, 5 do
                print(i)
            end
        """))

    def test_while_false(self):
        self.assertIn("loop_never_runs", kinds("""
            while false do
                print("never")
            end
        """))

    def test_constant_condition(self):
        self.assertIn("constant_condition", kinds("""
            if true then
                print("yes")
            else
                print("no")
            end
        """))

    def test_too_many_arguments_which_luau_silently_discards(self):
        # Luau does NOT error when a function is given extra values - they are
        # quietly dropped. So this is a silent failure unique to Luau, and it is
        # invisible at runtime.
        found = analyse("""
            local function add(a)
                return a
            end
            print(add(1, 2, 3))
        """)
        self.assertIn("too_many_arguments", [f.kind for f in found])

    def test_varargs_are_not_flagged(self):
        self.assertEqual([f for f in analyse("""
            local function many(...)
                return select("#", ...)
            end
            print(many(1, 2, 3, 4))
        """) if f.kind == "too_many_arguments"], [])

    def test_undefined_global_reads_as_nil_not_an_error(self):
        # print(undefinedThing) is not an error in Luau - it prints nil. So this
        # is a silent failure and belongs here, not in the error translator.
        found = analyse("""
            print(myUndefinedThing)
        """)
        self.assertIn("undefined_global", [f.kind for f in found])
        self.assertIn("myUndefinedThing", [f.name for f in found])

    def test_roblox_globals_are_known(self):
        # A false positive on `game` or `Vector3` would make the tool useless
        # for Roblox work, which is the whole point of this version.
        self.assertEqual([f for f in analyse("""
            local part = Instance.new("Part")
            part.Position = Vector3.new(0, 5, 0)
            print(game.Workspace)
            print(script.Name)
            task.wait(1)
            print(math.floor(1.5))
        """) if f.kind == "undefined_global"], [])

    def test_a_real_kid_script(self):
        src = """
            local player = game.Players.LocalPlayer
            local speed = 16
            local spd = speed * 2

            local function onJump()
                print("jumped")
            end

            print(player.Name)
            print(speed)
        """
        found = analyse(src)
        got = sorted(f.name for f in found)
        self.assertIn("spd", got)
        self.assertIn("onJump", got)


@unittest.skipUnless(AST.is_file(), "luau-ast.exe not present in tools/")
class TestCorrectCodeIsSilent(unittest.TestCase):
    """Working scripts. Any finding here is a false positive, and a false
    positive is worse than a miss."""

    CORRECT = {
        "simple use": """
            local x = 10
            print(x)
        """,
        "reassignment": """
            local x = 1
            x = 2
            print(x)
        """,
        "function called": """
            local function greet()
                return "hi"
            end
            print(greet())
        """,
        "function with unused parameter": """
            local function handler(a, b)
                return a
            end
            print(handler(1, 2))
        """,
        "throwaway underscore": """
            for _, v in ipairs({1, 2}) do
                print(v)
            end
        """,
        "multiple assignment": """
            local a, b = 1, 2
            print(a, b)
        """,
        "swap": """
            local a, b = 1, 2
            a, b = b, a
            print(a, b)
        """,
        "used in a string": """
            local name = "Zed"
            print("hello " .. name)
        """,
        "used in a nested function": """
            local function outer()
                local target = 10
                local function inner()
                    return target
                end
                return inner()
            end
            print(outer())
        """,
        "table built and read": """
            local t = {}
            t.a = 1
            print(t.a)
        """,
        "loop with a real range": """
            for i = 1, 3 do
                print(i)
            end
        """,
        "while true with break": """
            local n = 0
            while true do
                n = n + 1
                if n > 3 then break end
            end
            print(n)
        """,
        "real comparison": """
            local x = 5
            if x > 3 then
                print("big")
            end
        """,
        "if with a real condition": """
            local flag = true
            if flag then
                print(1)
            else
                print(2)
            end
        """,
        "returning a built value": """
            local function build()
                local data = { a = 1 }
                return data
            end
            print(build())
        """,
        "ipairs": """
            for i, v in ipairs({10, 20}) do
                print(i, v)
            end
        """,
        "nested loop accumulator": """
            local grid = {{1, 2}, {3, 4}}
            local total = 0
            for _, row in ipairs(grid) do
                for _, cell in ipairs(row) do
                    total = total + cell
                end
            end
            print(total)
        """,
        "pcall": """
            local ok, err = pcall(function()
                error("x")
            end)
            print(ok, err)
        """,
        "metatable": """
            local t = setmetatable({}, {})
            print(t)
        """,
        "the standard library": """
            print(math.floor(1.5))
            print(string.upper("hi"))
            print(table.concat({1, 2}, ","))
            print(os.time())
        """,
    }

    def test_none_of_these_report_anything(self):
        failures = []
        for label, src in self.CORRECT.items():
            found = analyse(src)
            if found:
                failures.append((label, [(f.kind, f.name) for f in found]))
        if failures:
            report = "\n".join(f"    {label}: {detail}" for label, detail in failures)
            self.fail(f"false positives on correct code:\n{report}")


@unittest.skipUnless(AST.is_file(), "luau-ast.exe not present in tools/")
class TestRobustness(unittest.TestCase):

    def test_syntax_error_returns_nothing(self):
        self.assertEqual(analyse("local x = = 5"), [])

    def test_empty_source(self):
        self.assertEqual(analyse(""), [])

    def test_only_comments(self):
        self.assertEqual(analyse("-- nothing here\n"), [])

    def test_findings_ordered_by_line(self):
        found = analyse("""
            local a = 1
            local b = 2
            local c = 3
            print("done")
        """)
        self.assertEqual([f.line for f in found], sorted(f.line for f in found))

    def test_line_numbers_are_one_based_for_an_editor(self):
        found = analyse("""local score = 0
local scor = score + 1
print(score)
""")
        self.assertEqual(found[0].line, 2)


@unittest.skipUnless(AST.is_file(), "luau-ast.exe not present in tools/")
class TestEveryFindingIsUsable(unittest.TestCase):

    SOURCES = [
        "local score = 0\nlocal scor = score + 1\nprint(score)",
        "local function f() return 1 end\nprint(2)",
        "for i = 1, 0 do print(i) end",
        "while false do print(1) end",
        "if true then print(1) else print(2) end",
        "local function f(a) return a end\nprint(f(1,2))",
        "print(undefinedThing)",
    ]

    def test_fields_populated(self):
        for src in self.SOURCES:
            for f in analyse(src):
                with self.subTest(kind=f.kind):
                    self.assertTrue(f.title)
                    self.assertTrue(f.plain)
                    self.assertTrue(f.parent_says)
                    self.assertTrue(f.fix_hint)
                    self.assertGreater(len(f.parent_says), 15)

    def test_no_jargon_in_plain(self):
        jargon = ["ast", "node", "scope", "linter", "token", "bytecode",
                  "stacktrace", "nil value"]
        for src in self.SOURCES:
            for f in analyse(src):
                with self.subTest(kind=f.kind):
                    for word in jargon:
                        self.assertNotIn(word, f.plain.lower())

    def test_parent_says_is_a_sentence(self):
        for src in self.SOURCES:
            for f in analyse(src):
                with self.subTest(kind=f.kind):
                    self.assertTrue(f.parent_says.rstrip().endswith(("?", ".", "!")))


if __name__ == "__main__":
    unittest.main(verbosity=2)