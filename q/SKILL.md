---
name: q
description: REQUIRED instead of a chain of two or more rg/grep/glob calls to answer a structural question about the code — "which functions call X", "what classes live under src/api", "which handlers are async", "find the longest functions", "who is decorated with @route", "what does module M define" — and REQUIRED as `q blast NAME` before changing a function's signature, renaming a symbol, deleting code, or whenever you are about to rg for a name "to see who uses it". One query over a cached symbol index replaces the whole rg hop sequence and its overlapping output.
---

# q

Ripgrep answers "which lines contain this text". Most code questions are really "which *symbols* satisfy this", and they take four rg calls with context to answer. `q` indexes every function, method, class and constant (Python exactly via ast; JS/TS/Go/Rust/Java/Ruby by patterns) with its span, params, decorators and the names it calls, then answers in one call. File discovery uses `fd` when installed (gitignore-aware, so build output never enters the index) and falls back to `os.walk`.

`nitro q "calls=db.query"` is the short form; the nitro hook expands `nitro q` to `python $HOME/.claude/skills/q/scripts/q.py`. Without the hook installed, type that path (`$HOME`, never `~`: PowerShell does not expand `~` inside quotes).

## Query
- `nitro q "calls=db.query"` - every symbol that calls `db.query`.
- `nitro q "kind=function file~^src/api/ params~request" --cols name,file,line,params`
- `nitro q "deco=app.route" --cols name,file,line` / `nitro q "name~^test_ len>60 sort=-len"`
- `nitro q "file=src/db/pool.py" --cols kind,name,line,end,params` - a module outline with spans, cheaper than reading it.
- `nitro q "kind=class exported=1"` / `nitro q "calls~^requests\." file!~test`
- `nitro q --reindex` after a big checkout; otherwise the index refreshes by mtime automatically.

Columns: kind name file line end len params calls deco ret doc exported lang. Operators: `=` `!=` `~` `!~` `>` `<` `>=` `<=`; `sort=col` / `sort=-col`; `--limit N`.

## Blast radius (before an edit)
- `nitro q blast acquire` / `nitro q blast Pool.acquire` - the definition(s), what it calls, every caller grouped by the symbol it sits in.
- `nitro q blast src/db/pool.py:88` - resolve the symbol at that line first. `--depth 2` adds callers of the callers; `--tests` lists test files that mention it.

```
def   method Pool.acquire  src/db/pool.py:80-104  (self, timeout=None)
calls 4: Pool._new, Pool._check, log.debug, time.monotonic
callers of acquire: 7 refs in 4 symbols
    get_session                          src/api/deps.py:31   conn = await pool.acquire(timeout=5)
    Worker.run                           src/jobs/worker.py:58,71
    test_acquire_timeout                 tests/test_pool.py:22,25,30
    (module level)                       scripts/warm.py:9
tests: tests/test_pool.py, tests/test_deps.py
[q blast: acquire, 1 def(s), 7 refs]
```

## Rules
1. Ask the question as one query. If you find yourself planning a second rg to narrow the first, that is a `q` query.
2. `calls=` is exact (or dotted-suffix) match; `calls~` is regex. `name=foo` also matches `Class.foo`.
3. Results give `file line end`. Feed those to `nitro hp view FILE SYMBOL` when you need the body; do not rg for the definition again.
4. Run `blast` once before the edit, not rg five times. The caller list is the checklist of places to re-check afterwards; `(module level)` refs are usually imports and matter for renames, not behavior changes.
