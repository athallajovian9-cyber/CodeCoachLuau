#!/usr/bin/env python3
"""Run every CodeCoach Luau test. One command, one exit code."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    sys.path.insert(0, str(HERE))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in ("tests.test_luau_errors", "tests.test_luau_silent"):
        try:
            suite.addTests(loader.loadTestsFromName(name))
        except Exception as exc:
            print(f"  could not load {name}: {exc}")
            return 1
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    total, bad = result.testsRun, len(result.failures) + len(result.errors)
    print()
    print("  ============================================")
    print(f"  checks={total}  passes={total - bad}  fails={bad}")
    print("  ============================================")
    for case, _ in result.failures + result.errors:
        print(f"    - {case}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
