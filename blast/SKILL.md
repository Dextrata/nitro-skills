---
name: blast
description: REQUIRED before changing a function's signature, renaming a symbol, deleting code, or altering behavior something else may depend on — and whenever you are about to rg for a name "to see who uses it". Prints the definition, every caller grouped by the function it sits in, what the symbol itself calls, and optionally the tests that mention it, in one call.
---

# blast

The reading an agent does before an edit is mostly reassurance: who calls this, what does it call, will a test break. `blast` answers that as a compact adjacency list so you can stop grepping around the change.

`BLAST="python $HOME/.claude/skills/blast/scripts/blast.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

- `$BLAST acquire` / `$BLAST Pool.acquire` - def, callees, callers grouped by enclosing symbol.
- `$BLAST src/db/pool.py:88` - resolve the symbol at a line first.
- `$BLAST acquire --depth 2` - callers of the callers. `--tests` - test files mentioning it.

Example:
```
def   method Pool.acquire  src/db/pool.py:80-104  (self, timeout=None)
calls 4: Pool._new, Pool._check, log.debug, time.monotonic
callers of acquire: 7 refs in 4 symbols
    get_session                          src/api/deps.py:31   conn = await pool.acquire(timeout=5)
    Worker.run                           src/jobs/worker.py:58,71
    test_acquire_timeout                 tests/test_pool.py:22,25,30
    (module level)                       scripts/warm.py:9
tests: tests/test_pool.py, tests/test_deps.py
[blast: acquire, 1 def(s), 7 refs]
```

## Rules
1. Run `blast` once before the edit, not rg five times. The caller list is the checklist of places to re-check afterwards.
2. `(module level)` refs are usually imports or scripts; they matter for renames, not for behavior changes.
3. Shares the q index; a stale result means `q --reindex`.
