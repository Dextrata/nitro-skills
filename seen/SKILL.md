---
name: seen
description: REQUIRED wrapper for any shell command whose output may repeat lines you were already shown this session — git diff, git log, rg with context, cat of a file you viewed, a second test run, a build log. Folds every block of 4+ lines that appeared in an earlier output into a one-line pointer, so nothing enters context twice. Use it instead of running the bare command. Skip only for tiny one-shot commands (git status, ls).
---

# seen

Most repeated tool output is not new: the same diff hunk, the same stack trace, the same rg hit inside a function you viewed ten minutes ago. `seen` keeps a per-workspace index of every 4-line window the model has already been shown and folds any re-occurrence into `[seen #ID L12-40, 29 lines]`.

`SEEN="python $HOME/.claude/skills/seen/scripts/seen.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

- `$SEEN git diff` / `$SEEN rg -n foo src -C3` / `$SEEN CMD...` - run and fold. New lines print verbatim.
- `$SEEN --stdin` - filter a pipeline: `some-cmd | $SEEN --stdin`.
- `$SEEN --show 7 12-40` - reprint a folded block if you truly need it again.
- `$SEEN --reset` - forget the index for this workspace.

Every output ends with `[seen: output #N, L lines, F folded, exit C]`. Read the exit code there.

## Rules
1. A folded block is content you already have in context. Scroll up mentally; do not `--show` it unless the earlier copy was truncated.
2. Timestamps, durations and ANSI codes are normalized before hashing, so a re-run that differs only cosmetically folds completely.
3. Combine freely with rerun: `$SEEN python $HOME/.claude/skills/rerun/scripts/rr.py pytest -q` folds whatever the diff repeats.
