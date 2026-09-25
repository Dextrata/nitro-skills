---
name: sdiff
description: REQUIRED instead of `git diff`, `git diff --cached`, `git show`, or `git diff BASE..HEAD` whenever you want to know WHAT changed — reviewing your own edits before a commit, checking a branch, understanding a teammate's change. Prints one line per changed symbol with a classification (whitespace, imports, comment, moved, real) and lets you pull a single hunk by id. Never run a bare git diff first.
---

# sdiff

A raw diff is context lines and noise. `sdiff` maps every hunk to the function or class it lives in and prints one line per symbol: added/removed counts, hunk ids, and whether the change is only whitespace, imports, comments, or a block moved from elsewhere. Real changes get a one-line hint. You then fetch only the hunks you care about.

`nitro sdiff` is the short form; the nitro hook expands `nitro sdiff` to `python $HOME/.claude/skills/sdiff/scripts/sdiff.py`. Without the hook installed, type that path (`$HOME`, never `~`: PowerShell does not expand `~` inside quotes).

- `nitro sdiff` - working tree vs index. `nitro sdiff --cached` - staged. `nitro sdiff HEAD~3` / `nitro sdiff main...HEAD` / `nitro sdiff -- src/` - any git diff args.
- `nitro sdiff --hunk h4` - one hunk in full. `nitro sdiff --file src/x.py` - all hunks of one file.

Example:
```
src/db/pool.py   +14/-3
    Pool.acquire                     +9/-2    h1 h2        | if self._size >= self.max:
    Pool._new                        +2/-0    h3           imports
    (top level)                      +3/-1    h4           ws
tests/test_pool.py  NEW FILE   +80/-0
    symbols: test_acquire, test_release, test_exhausted
[sdiff: 2 files, +94/-3, 4 hunks; --hunk hN for detail]
```

## Rules
1. Rows classified `ws`, `imports`, `comment`, or `moved` need no further look. Fetch hunks only for rows with a `|` hint.
2. For a file you wrote yourself this session, the summary is enough to confirm the edit landed; do not fetch hunks to re-read your own code.
3. Whole new files list their symbols instead of hunks. If you need one, use hashpatch `view` on the file, not `--hunk`.
