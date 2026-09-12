---
name: refactor
description: REQUIRED for mechanical multi-line or multi-file edits — renaming an identifier, adding an import, wrapping a range in try/with/if, deleting or moving a top-level function or class, regex replace across files. One line of intent replaces a patch per file. Use it before hashpatch apply whenever the edit is describable in a sentence; hashpatch is for edits that need hand-written replacement lines.
---

# refactor

A rename across nine files costs nine patches. With `refactor` it costs one line, and the reply is one line per file. The script does the mechanical work (token-aware for Python so strings and comments are untouched; word-boundary elsewhere). Candidate files come from `rg -l` and `fd`, so a rename across a large tree reads only the files that mention the name.

`RF="python $HOME/.claude/skills/refactor/scripts/rf.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

- `$RF rename oldName newName [src/ tests/]` - identifier rename. Defaults to the whole tree.
- `$RF add-import src/x.py "from pathlib import Path"` - inserted after the last import; no-op if present.
- `$RF wrap src/x.py 20-31 try ValueError "return None"` - wrap a line range. Also `wrap FILE A-B with EXPR` / `if COND` / `for ...`.
- `$RF rm-symbol src/x.py old_helper` - delete a top-level def/class (decorators included, trailing blanks swallowed).
- `$RF move-symbol src/a.py helper src/b.py` - cut from one file, append to another.
- `$RF replace 'log\.warn\(' 'log.warning(' src/` - regex across files.
- Prefix `--dry` to see what would change.

## Rules
1. Line ranges come from a hashpatch `outline`/`view` in this conversation. After `wrap` the tool prints the new range; trust it.
2. Rename is by identifier, not by substring: `user` does not touch `username`. Use `replace` when you really mean substring.
3. `rename` on JS/TS is regex-based and will rename inside strings; check with `--dry` when the identifier is a common word.
4. For a one-off transform in a pipeline use `sd` (`cmd | sd 'old' 'new'`, `$1` for groups). For files use `replace` here: `sd FILE` in-place edits are blocked by the hook because they are unanchored and unreviewable.
