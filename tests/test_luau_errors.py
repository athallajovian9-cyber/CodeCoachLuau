"""Tests for the Luau error translator.

Every case writes a genuinely broken script, RUNS IT with the real Luau
interpreter, and feeds the translator the output Luau actually produced.
Nothing is tested against a message typed from memory.

    python run_tests.py
"""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import luau_errors as LE

LUAU = HERE / "tools" / "luau.exe"
WORK = Path(tempfile.gettempdir()) / "codecoach_luau_tests"


def run_broken(source: str) -> tuple[str, str]:
    """Run a broken script. Returns (stdout, stderr) SEPARATELY.

    Kept apart on purpose: the error translator is given stderr only. Merging
    them fed ordinary program output into the translator, and a program that
    simply printed a number came back as "Luau stopped: 1" - the tool telling a
    parent their working code was broken.
    """
    WORK.mkdir(parents=True, exist_ok=True)
    p = WORK / "broken.luau"
    p.write_text(textwrap.dedent(source), encoding="utf-8")
    r = subprocess.run([str(LUAU), str(p)], capture_output=True, text=True, timeout=20)
    return r.stdout or "", r.stderr or ""


def explain_source(source: str) -> LE.Explanation:
    _out, err = run_broken(source)
    e = LE.explain(err)
    if e is None:
        raise AssertionError(f"translator returned None for real stderr:\n{err}")
    return e


@unittest.skipUnless(LUAU.is_file(), "luau.exe not present in tools/")
class TestRealLuauErrors(unittest.TestCase):

    def test_index_nil(self):
        e = explain_source("""
            local t = nil
            print(t.x)
        """)
        self.assertIn("index nil", e.exc)
        self.assertIn("nil", e.plain)
        self.assertIn("WaitForChild", e.hint)

    def test_call_a_nil_value(self):
        e = explain_source("""
            local f = nil
            f()
        """)
        self.assertIn("call a nil", e.exc)
        self.assertIn("spell", e.parent_says.lower())

    def test_index_a_number(self):
        e = explain_source("""
            local x = 5
            print(x[1])
        """)
        self.assertIn("index", e.exc)
        self.assertIn("number", e.plain)

    def test_iterate_over_a_number(self):
        e = explain_source("""
            for k in 5 do print(k) end
        """)
        self.assertIn("iterate", e.exc)
        self.assertIn("table", e.plain)

    def test_compare_with_nil(self):
        e = explain_source("""
            local a = nil
            if a > 3 then print(1) end
        """)
        self.assertIn("compare", e.exc)

    def test_syntax_error(self):
        e = explain_source("local x = = 5")
        self.assertEqual(e.exc, "SyntaxError")
        self.assertIn("Luau cannot read", e.title)

    def test_concat_is_not_an_error_in_luau(self):
        # `"a" .. 5` actually WORKS in Luau - numbers are coerced to text. The
        # Python version of this tool treats it as an error; here it must not be
        # reported as one, because it is not one.
        _out, err = run_broken('local s = "a" .. 5\nprint(s)')
        self.assertIsNone(LE.explain(err), "Luau coerces this; it is not an error")

    def test_undefined_global_is_not_an_error(self):
        # Reading an unknown name gives nil, it does not raise. This belongs to
        # the silent detector, not the error translator.
        _out, err = run_broken('print(undefinedThing)')
        self.assertIsNone(LE.explain(err))


class TestSearchQuery(unittest.TestCase):

    def test_no_file_paths_in_the_query(self):
        for src in ("local t = nil\nprint(t.x)", "local f = nil\nf()",
                    "local x = 5\nprint(x[1])"):
            e = explain_source(src)
            with self.subTest(exc=e.exc):
                self.assertNotIn("\\", e.search)
                self.assertNotIn("Temp", e.search)
                self.assertNotIn(".luau", e.search)

    def test_queries_are_short(self):
        for src in ("local t = nil\nprint(t.x)", "for k in 5 do end",
                    "local a = nil\nif a > 3 then end"):
            e = explain_source(src)
            with self.subTest(exc=e.exc):
                self.assertLess(len(e.search), 80, e.search)

    def test_roblox_specific_queries_mention_roblox(self):
        # Searching this error without the word Roblox returns Node.js and C
        # answers, which are useless to a kid working in Studio.
        e = explain_source("local t = nil\nprint(t.x)")
        self.assertIn("Roblox", e.search)


class TestEveryExplanationIsUsable(unittest.TestCase):

    SOURCES = [
        "local t = nil\nprint(t.x)",
        "local f = nil\nf()",
        "local x = 5\nprint(x[1])",
        "for k in 5 do print(k) end",
        "local a = nil\nif a > 3 then print(1) end",
        "local x = = 5",
    ]

    def test_fields_are_populated(self):
        for src in self.SOURCES:
            e = explain_source(src)
            with self.subTest(exc=e.exc):
                self.assertTrue(e.title)
                self.assertTrue(e.plain)
                self.assertTrue(e.parent_says)
                self.assertTrue(e.search)
                self.assertGreater(len(e.parent_says), 15)

    def test_no_jargon_in_plain(self):
        jargon = ["stacktrace", "concatenate", "operand", "nil value",
                  "AstExpr", "token", "bytecode"]
        for src in self.SOURCES:
            e = explain_source(src)
            with self.subTest(exc=e.exc):
                for word in jargon:
                    self.assertNotIn(word, e.plain.lower(),
                                     f"'{word}' is jargon")

    def test_parent_says_is_a_sentence(self):
        for src in self.SOURCES:
            e = explain_source(src)
            with self.subTest(exc=e.exc):
                self.assertTrue(e.parent_says[0].isupper()
                                or e.parent_says[0] in '"\'')
                self.assertTrue(e.parent_says.rstrip().endswith(("?", ".", "!")))

    def test_raw_is_kept_for_a_programmer(self):
        e = explain_source("local t = nil\nprint(t.x)")
        self.assertIn("attempt to index nil", e.raw)


class TestNoError(unittest.TestCase):

    def test_empty(self):
        self.assertIsNone(LE.explain(""))

    def test_whitespace(self):
        self.assertIsNone(LE.explain("   \n "))

    def test_clean_program_is_not_an_error(self):
        _out, err = run_broken('local x = 1\nprint(x)')
        self.assertIsNone(LE.explain(err))

    def test_unknown_message_still_usable(self):
        e = LE.explain("C:/x/y.luau:3: some brand new luau failure")
        self.assertIsNotNone(e)
        self.assertTrue(e.parent_says)
        self.assertIn("some brand new luau failure", e.raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)