---
name: budget
description: Use when a command is denied by a hook, when you want to know which commands are eating the session's tokens, or before running a command whose output size you cannot predict. `budget report` reads the per-command ledger the hooks keep; `sessions` measures whole past sessions from the Claude Code transcripts (where prompt tokens go, what the hooks and skills saved). The hooks enforce the cap automatically; this skill is how you read the numbers.
---

# budget

Every other nitro skill shrinks a *kind* of output. `budget` is the enforcement layer plus its instruments: a PostToolUse hook records how many lines each command shape produced, a PreToolUse hook denies the next run of anything that exceeded the cap (120 lines) unless it goes through a shaper or is bounded, and known floods (unbounded `git log`, whole-file `git blame`, raw `curl`, `cat x.json`, `docker logs`) are rewritten into the right skill on first sight.

`nitro budget report` is the short form; the nitro hook expands `nitro budget` to `python $HOME/.claude/skills/budget/scripts/budget.py` and `nitro sessions` to `.../budget/scripts/sessions.py`. Without the hook installed, type those paths (`$HOME`, never `~`: PowerShell does not expand `~` inside quotes).

- `nitro budget report` - top commands by tokens spent in this workspace, with max line count and run count.
- `nitro budget predict "npm run build"` - what history says this shape produces.
- `nitro budget reset`.
- `nitro sessions` - every Claude Code transcript on this machine, aggregated: real prompt/output tokens, what a prompt is made of, tool output by kind, hashpatch replay, hook round trips, boilerplate. `--projects DIR`, `--min KB`. Prints aggregates only.

When a command is denied instead of rewritten, pick the skill the message names:

| output looks like | use |
|---|---|
| test, lint or type-check results | `nitro fails` |
| a build or script you will run again | `nitro rr` |
| log stream, install output | `nitro mine` |
| JSON / CSV / table | `nitro shape` |
| a git diff | `nitro sdiff` |
| git history or blame for a file / lines | `nitro why` |
| manifests, README, "what is this repo" | `nitro scout` |
| a big file's structure or one symbol | `nitro hp outline` / `nitro hp view FILE SYMBOL` |
| a recursive file listing | `fd PATTERN` (gitignore-aware; not a skill, just the tool the hook names) |
| a JSON payload you need one field of | `nitro shape` then `--path`, or `cmd \| jq -c '.field'` |

## Rules
1. A denial is information: the raw command would have cost more than the whole skill set. Re-issue it through the named skill, never with `#nitro-skip` unless the raw bytes are truly needed.
2. Shapers nest: `nitro mine nitro rr npm run build` mines what the diff leaves; every `nitro <skill>` in the command line is expanded.
3. `report` at the end of a long session tells you which habit to fix next; `sessions` tells you which habit cost the most across all sessions.
