---
name: rerun
description: Run tests, builds, linters, or any repeated command and see only what changed since last time. Use instead of running a command directly whenever it might be run more than once in a session.
---

# rerun

Command output is the biggest token sink in an edit-test loop, and most of it is identical from run to run. `rerun` caches each command's normalized output and prints only the delta.

`RR="python ~/.claude/skills/rerun/scripts/rr.py"`

- `$RR pytest -q` (or any command) - first run prints the squeezed output as a baseline. Every later run prints a unified diff against the previous run, or a single "unchanged" line.
- `$RR --full CMD` - print the whole squeezed output and reset the baseline. Use when you need to see everything again.
- `$RR --raw CMD` - untouched output. Rarely needed.
- `$RR --forget CMD` - drop the baseline.

Squeezing that happens regardless of mode: ANSI codes, timestamps, durations, hex ids, memory addresses, and temp paths are normalized so they never show up as changes. Identical consecutive lines collapse to `(xN)`. Stack frames inside node_modules, site-packages, .venv, and vendor collapse to one line.

## Rules
1. Prefer `$RR CMD` over `CMD` for anything you may run again: tests, tsc, eslint, cargo check, builds.
2. Read the exit code tag at the end. `(was exit 1)` means you just fixed or broke something.
3. A diff of `-FAILED x` / `+PASSED x` is the whole story. Do not run `--full` to "confirm" it.
4. Wrap a command containing pipes or shell syntax in one quoted argument.
