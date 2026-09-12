---
name: q
description: REQUIRED instead of a chain of two or more rg/grep/glob calls to answer a structural question about the code — "which functions call X", "what classes live under src/api", "which handlers are async", "find the longest functions", "who is decorated with @route", "what does module M define". One query over a cached symbol index replaces the whole rg hop sequence and its overlapping output.
---

# q

Ripgrep answers "which lines contain this text". Most code questions are really "which *symbols* satisfy this", and they take four rg calls with context to answer. `q` indexes every function, method, class and constant (Python exactly via ast; JS/TS/Go/Rust/Java/Ruby by patterns) with its span, params, decorators and the names it calls, then answers in one call. File discovery uses `fd` when installed (gitignore-aware, so build output never enters the index) and falls back to `os.walk`.

`Q="python $HOME/.claude/skills/q/scripts/q.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

- `$Q "calls=db.query"` - every symbol that calls `db.query`.
- `$Q "kind=function file~^src/api/ params~request" --cols name,file,line,params`
- `$Q "deco=app.route" --cols name,file,line` / `$Q "name~^test_ len>60 sort=-len"`
- `$Q "file=src/db/pool.py" --cols kind,name,line,end,params` - a module outline with spans, cheaper than reading it.
- `$Q "kind=class exported=1"` / `$Q "calls~^requests\." file!~test`
- `$Q --reindex` after a big checkout; otherwise the index refreshes by mtime automatically.

Columns: kind name file line end len params calls deco ret doc exported lang. Operators: `=` `!=` `~` `!~` `>` `<` `>=` `<=`; `sort=col` / `sort=-col`; `--limit N`.

## Rules
1. Ask the question as one query. If you find yourself planning a second rg to narrow the first, that is a `q` query.
2. `calls=` is exact (or dotted-suffix) match; `calls~` is regex. `name=foo` also matches `Class.foo`.
3. Results give `file line end`. Feed those straight to hashpatch `view` when you need the body; do not rg for the definition again.
