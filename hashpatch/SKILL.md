---
name: hashpatch
description: REQUIRED for any edit to an existing file, and for viewing part of one. Replaces Read+Edit with leased views and line-number patches (outline/grep/view/apply) so you never re-transmit code you already saw and never read a whole file to edit five lines. `view FILE SYMBOL` shows one function, class or markdown section; `outline` understands code, markdown, YAML/TOML/INI/JSON, Makefile, Dockerfile, shell, SQL, CSS, HTML and notebooks. Use before Read or Edit on any file that already exists, no matter how small the change. Skip only for brand-new files (use Write) or a file already fully viewed this turn.
---

# hashpatch

Edit files by *pointing* at lines, not by quoting them. A view prints `N|text` lines and closes with a lease: a hash of exactly those lines. A patch repeats the lease and cites bare line numbers inside it; if the file changed since the view, the lease is stale and nothing is written. The reply is a receipt (each hunk's new span and a fresh lease), not the lines you just wrote. Do not Read a file whole and do not use Edit with an old_string.

`nitro hp ...` is the short form; the nitro hook expands `nitro hp` to `python $HOME/.claude/skills/hashpatch/scripts/hp.py`. Without the hook installed, type that path (`$HOME`, never `~`: PowerShell does not expand `~` inside quotes).

## Locate (cheap)
- `nitro hp view FILE SYMBOL` - one function/method/class (`Pool.acquire`), or one markdown section by heading, under a lease. Start here when you know the name.
- `nitro hp outline FILE` - structure with `N:HHHH` anchors: def/class/function/export/ALL_CAPS constants in code; `#` headers in markdown; top-level keys in YAML/TOML/INI/JSON/.env; Makefile targets; Dockerfile FROM/WORKDIR/CMD; shell functions; SQL statements; CSS selectors; HTML sections; one line per notebook cell. Ends with `[outline: FILE, N lines, K entries]`.
- `nitro hp grep FILE REGEX [CTX]` - matching lines with anchors, optional context.
- `nitro hp view FILE A-B` - a slice under a lease. `--anchors` adds per-line hashes if you need to cite single lines later.

## Edit
```
nitro hp apply FILE <<'EOF'
[lease src/db/pool.py 40-80 h=3f9ac2]
@@
@42-44
    replacement lines (verbatim, no prefix)
@@
@57+
    inserted after line 57
@@
@12
@@
EOF
```
- First line: the lease line exactly as the view printed it (or `#lease 40-80:3f9ac2`). Then hunks.
- `@N` replace one line; `@N-M` replace a range; empty body = delete. `@N+` insert after; `@N^` insert before; `@0+` top of file / create file.
- Lines from `grep`, `outline` or `--anchors` are cited with their hash and need no lease: `@42:ab3f`, `@42:ab3f-44:c1d0`, `@57:9e1a+`.
- Line numbers are from the ORIGINAL file. Put several hunks in one call; the tool handles offsets.
- Body lines are verbatim (UTF-8). A body may not contain a bare `@@` line.
- Receipt: `h1 @42-44 -> now 42-46`, then `[lease FILE 40-82 h=...]` covering everything touched. A second edit cites the new lease and new numbers; nothing to re-view. `--echo` prints the lines if you truly need them; `--dry` validates only.

## Rules
1. Leases and anchors come only from tool output in this conversation. Never guess or fabricate one.
2. `REJECTED` means the file moved under you: re-`view` the range and retry. Nothing was written.
3. For brand-new files or total rewrites, plain Write is fine. hashpatch is for surgery.
4. A CSV outline prints the header and the row count; a minified JSON outline points you at the shape skill. Neither should be viewed whole.
