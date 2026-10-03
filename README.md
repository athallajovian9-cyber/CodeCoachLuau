# CodeCoach Luau

Tells a parent what is wrong with their kid's Roblox script, in words a
non-programmer can read — including the bugs Luau never mentions.

```
RUN_CodeCoach_Luau.bat              watch a folder, report on every save
python luaucheck.py script.luau     check one script
python luaucheck.py --folder .      every .luau underneath
```

Offline. No account, no subscription. Nothing leaves the machine.

## Why a Luau version

Because the alternative is a kid learning to code in a language they cannot use
to make anything. Luau is a real language with a real type checker, and the games
they build are games they can actually play — and so can you.

## The problem this exists for

```lua
local score = 0
local scor = score + 10     -- typo
print("score is " .. score) -- prints 0. No error. Nothing.
```

That is the worst bug a beginner faces and it is **invisible**. Luau is happy.
There is no message to search, nothing to paste into Google. The kid stares at
it, the parent asks what's wrong, and the answer is "I don't know."

## What a parent gets

```
  typo.luau
  ----------------------------------------------------------------
  ONE THING TO FIX
  It runs, but something below is not doing anything.

  STUCK FOR 22 MINUTES
  This is not 'not trying'. Same problem, 12 checks in a row.
  This is the moment to walk over and ask a question.

  SILENT - no error, it just does nothing

  Line 2: 'scor' is set and then never used
    The line creates 'scor', but nothing later reads it. The script
    runs and says nothing - which usually means the value was meant
    to go somewhere, or the name was spelled differently from the
    one being used.

  WHAT YOU COULD SAY
    "Can they find 'scor' again anywhere below that line? Compare
    the spelling with the name they meant to change."
```

## Two failures specific to Luau

Python's version of this tool cannot catch these, because Python does not do
them. Luau does, silently:

```lua
-- 1. Extra arguments are quietly discarded. No error, ever.
local function add(a) return a end
print(add(1, 2, 3))          -- runs fine, 2 and 3 vanish

-- 2. Reading an undefined name gives nil, not an error.
print(myUndefinedThing)      -- prints nil, no complaint
```

Both are caught. Both are invisible at runtime.

## It does not run your kid's Roblox script, and that is deliberate

A Roblox script **cannot** run outside Roblox. Standalone `luau.exe` has no
`game`, no `workspace`, no `Instance`. Running a normal Studio script under it
gives:

```
attempt to index nil with 'Players'
```

which is the tool **inventing** an error about code that is perfectly correct. A
parent told that would go hunting for a bug that does not exist.

So the default is static analysis: parse the file, find the silent failures,
never execute. The report says so explicitly when a file talks to Roblox.

`--run` is there for pure-Luau scripts with no Roblox API calls. It still refuses
the Roblox ones.

## How it works

```
tools/luau-ast.exe   Luau's own parser, emitting the tree as JSON
luau_silent.py       the silent-failure checks, over that tree
luau_errors.py       real Luau error messages, translated
coach.py             the stuck tracker
report.py            one screen, ordered for a parent
```

`luau-ast.exe` is what makes this better than the Python version in one respect:
**it resolves scopes itself**. Every local read carries a pointer back to the
exact declaration it refers to, so "declared and never read" is exact rather than
an approximation — no guessing about shadowing.

## Tests

```
python run_tests.py
```

**42 tests, exit code 0 only when everything passes.**

Every error case writes a genuinely broken script, **runs it with the real Luau
interpreter**, and feeds the translator the output Luau actually produced. And a
suite of correct scripts — including Roblox ones using `game`, `Vector3`,
`task.wait`, `pcall`, metatables — must produce **zero findings**, because a
detector that cries wolf gets switched off within a day. That guard is proven to
fail when removed.

## A bug the tests caught

Normal program output was being turned into an error. A script that simply
printed `1` came back as *"Luau stopped: 1"* — the tool telling a parent their
working code was broken. The translator now only describes text that has the
`path:line: message` shape of a real error; anything else is not an error and
gets no explanation.

## What it cannot do

- **Roblox API checking.** It cannot tell you that `:WaitForChild("Foo")` names
  something that does not exist in the Explorer. That needs the live DataModel,
  which only Studio has.
- **Runtime silent failures.** Static only, so a `while` loop whose condition
  never changes is not caught.
- **It does not lock anything.** No parental controls, no screen-time
  enforcement. It reports. A tool that takes the computer away teaches a kid to
  defeat the tool; a tool that makes a parent useful teaches a kid to ask.

## Requirements

Python 3, and `luau.exe` + `luau-ast.exe` in `tools/` — from the
[Luau releases](https://github.com/luau-lang/luau/releases). They are bundled in
the release zip.

## Licence

MIT. `tools/` contains Luau binaries, MIT licensed by the Luau project.