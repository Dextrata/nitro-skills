---
name: trace
description: REQUIRED wrapper for running anything that may crash or print stack traces — a failing script, a server start, a test file that errors, a CLI that throws. Strips library frames, collapses recursion, keeps only user-code frames and the message, and replaces a trace you already saw with a one-line pointer. Run the command through it instead of bare, and re-run failing things through it too.
---

# trace

A Python traceback is forty lines of which four matter: your frames and the message. A Node one is worse. `trace` keeps the user-code frames, folds the rest into `… 12 library frames`, collapses recursion to `(xN)`, and remembers every trace it has shown you so a repeat costs one line.

`TR="python $HOME/.claude/skills/trace/scripts/trace.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

- `$TR python app.py` / `$TR node server.js` / `$TR CMD...` - run and compress. Non-trace lines pass through.
- `cmd | $TR --stdin` / `$TR --file crash.log`.
- `$TR --show 3` - the full raw trace #3 if a library frame is actually the culprit.

Output for a new trace:
```
[trace #3]
    src/db/pool.py:88 acquire()  conn = self._new()
    src/db/pool.py:41 _new()  raise PoolExhausted(...)
    … 9 library frames
  PoolExhausted: no connections after 30s
```
Repeat: `[trace #3: same as before] PoolExhausted: no connections after 30s`

## Rules
1. Combine with rerun for test suites (`$TR $RR pytest`): rerun diffs, trace compresses what remains.
2. `same as before` means the fix did not change the failure. Do not `--show` it; re-read your earlier copy.
3. Library frames are dropped, not hidden from you forever: `--show N` exists for the rare case the bug is inside a dependency.
