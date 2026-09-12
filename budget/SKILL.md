---
name: budget
description: Use when a command is denied by the budget hook, when you want to know which commands are eating the session's tokens, or before running a command whose output size you cannot predict. Reports per-command token spend from history and predicts output lines for a command shape. The hooks/budget-guard.py PreToolUse hook enforces the cap automatically; this skill is how you read the ledger and choose a shaper.
---

# budget

Every other nitro skill shrinks a *kind* of output. `budget` is the enforcement layer: a PostToolUse hook records how many lines each command shape produced, and a PreToolUse hook denies the next run of anything that exceeded the cap (120 lines) unless it goes through a shaper or is bounded. Known floods (unbounded `git log`, `find`, `pip list`, raw `curl`, `cat x.json`, `docker logs`) are denied even on first sight.

`BUDGET="python $HOME/.claude/skills/budget/scripts/budget.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

- `$BUDGET report` - top commands by tokens spent in this workspace, with max line count and run count.
- `$BUDGET predict "npm run build"` - what history says this shape produces.
- `$BUDGET reset`.

When denied, pick the shaper the message names:

| output looks like | use |
|---|---|
| repeats things you already saw | `seen` |
| deep paths / hashes everywhere | `alias` |
| log stream, build output | `mine` |
| JSON / CSV / table | `shape` |
| stack traces | `trace` |
| test / lint results | `rerun` |
| a git diff | `sdiff` |
| a recursive file listing | `fd PATTERN` (gitignore-aware; not a skill, just the tool the hook names) |
| a JSON payload you need one field of | `shape` then `--path`, or `cmd \| jq -c '.field'` |

## Rules
1. A denial is information: the raw command would have cost more than the whole skill set. Re-issue it through the named shaper, never with `#nitro-skip` unless the raw bytes are truly needed.
2. Shapers compose: `$SEEN $MINE CMD`, `$TR $RR pytest`.
3. `report` at the end of a long session tells you which habit to fix next.
