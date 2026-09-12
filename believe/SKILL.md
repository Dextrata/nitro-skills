---
name: believe
description: REQUIRED before re-reading or viewing a file you have ALREADY seen or think you understand, to confirm a signature, a class's members, an import, a call, or that some text is present. State the belief as claims; the script checks them against the real file and prints only mismatches. Reading to confirm what you already believe is the most wasteful read there is. Use this instead.
---

# believe

You rarely need to read a file. You need to know whether what you *think* is in it is still true. `believe` takes claims, checks them against the parsed file, and answers in one line per claim. A confirmed belief costs ~10 tokens; a re-read costs hundreds.

`BEL="python $HOME/.claude/skills/believe/scripts/believe.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

```
$BEL src/db.py "connect(url, timeout=30) -> Conn; class Pool: acquire, release; imports tenacity; calls retry; has 'DEFAULT_TIMEOUT'; lines ~120"
```
Output:
```
OK       connect(url, timeout=30) -> Conn
MISMATCH class Pool: acquire, release  =>  missing ['release']; has: acquire, close, __aenter__
OK       imports tenacity
...
[believe: 5/6 confirmed, src/db.py 131 lines]
```

Claim forms: `name(params) -> ret`, `Class.method(params)`, `class Name: members`, `imports a, b.c`, `calls name`, `decorated fn @deco`, `has "text"`, `no "text"`, `lines ~N`. Separate with `;` or newlines (stdin).

## Rules
1. Before any `view`/`Read` of a file you have touched this session, try `believe` first. Only view the range a MISMATCH points at.
2. Mismatch lines carry the truth (`=> actually ...`). That is usually all you needed; do not view to double-check it.
3. Python is parsed with `ast`; JS/TS with patterns (functions, classes, imports, calls). Exit code 1 means at least one mismatch.
