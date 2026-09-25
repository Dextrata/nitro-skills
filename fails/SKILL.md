---
name: fails
description: REQUIRED wrapper for running tests, linters and type checkers — pytest, unittest, jest, vitest, mocha, go test, cargo test, dotnet test, tsc, eslint, ruff, mypy, pyright, clippy. Prints the summary line, each failure once (message + the user-code frame), and the delta against the previous run of the same command (new / still failing / fixed). Use it on the FIRST run too; that stores the baseline. Builds and other repeatable commands still go through rerun.
---

# fails

A test run is 300 lines of dots and 40-line tracebacks to say "3 failed". A second run after a fix is the same again. `fails` parses the runner's output, prints one block per failure (id, message, the frame in your code), and keys every failure so the next run can say what is new, what is still broken and what you fixed. Linters and type checkers get the same treatment grouped by rule, keyed without line numbers so an edit above a warning does not make it "new".

`FAILS="python $HOME/.claude/skills/fails/scripts/fails.py"`

Use `$HOME`, never `~`: PowerShell does not expand `~` inside quotes. `$HOME` expands in Bash and PowerShell alike.

- `$FAILS pytest -q` / `$FAILS npm test` / `$FAILS cargo test` / `$FAILS ruff check .` / `$FAILS npx tsc --noEmit`
- `$FAILS "npm test -- --runInBand 2>&1"` - quote a command with pipes or redirections.
- `some-cmd 2>&1 | $FAILS --stdin` / `$FAILS --file ci.log` - parse output you already have.
- `$FAILS --show F2` - the full raw block of failure F2 from the last run. `--all` lifts the 20-failure cap. `--forget CMD` drops the baseline.

Output:
```
[fails] pytest: 297 passed, 2 failed, 1 error   exit 1
F1  NEW   tests/test_pool.py::test_close
          AttributeError: 'Pool' object has no attribute 'close'
          src/db/pool.py:41 close()  return self._conn.close()
          tests/test_pool.py:30 test_close()
F2  still tests/test_pool.py::TestPool::test_release
          src.db.pool.PoolExhausted: no connections
          src/db/pool.py:41
FIXED tests/test_pool.py::test_acquire_timeout
[fails: 2 failing; 1 new, 1 still, 1 fixed; --show F1 for the full block]
```
Diagnostics (tsc, eslint, ruff, mypy, pyright, clippy, gcc) print one row per rule: severity, rule, count, first locations, sample message.

## Rules
1. Read the last tag first. `0 new, N still, 0 fixed` after an edit means the edit did not touch the failure; do not re-run bare "to see the real output".
2. The frame lines are `file:line` in your code, library frames are already dropped. Feed them straight to hashpatch `view`; do not rg for the test.
3. `--show FN` only when the message and frame are not enough. It is the raw block you would have read anyway, once.
4. Unrecognized output falls back to the exit code and the last 25 lines; if that happens often for a runner, use rerun for it.
