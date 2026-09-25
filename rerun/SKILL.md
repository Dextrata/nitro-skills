---
name: rerun
description: REQUIRED wrapper for builds, scripts, generators and any other command whose output you might see again this session — npm run build, cargo build, make, docker build, a migration, a data script. Use it on the FIRST run too, not just repeats, since that establishes the free baseline. Tests, linters and type checkers go through the fails skill instead (it understands their output). Only skip for genuine one-shot commands unlikely to be rerun (git status, ls).
---

# rerun

Command output is the biggest token sink in an edit-build loop, and most of it is identical from run to run. `rerun` caches each command's normalized output and prints only the delta.

`nitro rr npm run build` is the short form; the nitro hook expands `nitro rr` to `python $HOME/.claude/skills/rerun/scripts/rr.py`. Without the hook installed, type that path (`$HOME`, never `~`: PowerShell does not expand `~` inside quotes). A bare build command is rewritten into this form by the hook anyway.

- `nitro rr npm run build` (or any command) - first run prints the squeezed output as a baseline. Every later run prints a unified diff against the previous run, or a single "unchanged" line.
- `nitro rr --full CMD` - print the whole squeezed output and reset the baseline. Use when you need to see everything again.
- `nitro rr --raw CMD` - untouched output. Rarely needed.
- `nitro rr --forget CMD` - drop the baseline.

Squeezing that happens regardless of mode: ANSI codes, timestamps, durations, hex ids, memory addresses, and temp paths are normalized so they never show up as changes. Identical consecutive lines collapse to `(xN)`. Stack frames inside node_modules, site-packages, .venv, and vendor collapse to one line.

## Rules
1. Prefer `nitro rr CMD` over `CMD` for anything you may run again: builds, codegen, scripts, docker. For pytest/jest/cargo test/tsc/eslint/ruff use `nitro fails`, which keys each failure and reports new/still/fixed instead of a text diff.
2. Read the exit code tag at the end. `(was exit 1)` means you just fixed or broke something.
3. A diff of `-error` / `+ok` is the whole story. Do not run `--full` to "confirm" it.
4. Wrap a command containing pipes or shell syntax in one quoted argument.
