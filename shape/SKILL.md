---
name: shape
description: REQUIRED for any command or file that returns structured data — curl/http responses, API JSON, package.json/lockfiles, CSV/TSV exports, SQL query results, kubectl/aws/gh CLI JSON, JSON-lines logs. Prints the schema with types, cardinalities and a few sample rows instead of the payload. Never cat a JSON or CSV file and never dump an API response raw; shape it and drill in with --path.
---

# shape

A 3,000-line JSON response has maybe 30 distinct keys. `shape` prints those keys with their types, how many distinct values each has, min/max for numbers, three examples, and a sample row or two. You then descend with `--path` to the one branch you need.

`SHAPE="python $HOME/.claude/skills/shape/scripts/shape.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

- `$SHAPE curl -s https://api.example.com/users` / `$SHAPE gh pr list --json number,title,author` / `$SHAPE CMD...`
- `$SHAPE --file data.csv` / `$SHAPE --file package-lock.json` / `cmd | $SHAPE --stdin`
- `$SHAPE --path data.items[0].tags CMD` - descend before shaping. On an array of objects, `--path items.name` gives the column.
- `$SHAPE --rows 10 ...` more samples. `$SHAPE --full --path items[2] ...` prints one small branch pretty-printed.

Detects JSON, JSON-lines, CSV/TSV (header inferred), markdown/pipe tables, space-aligned columns; anything else gets a line count with head and tail.

## Rules
1. Shape first. Use `--full` only on a branch you have already narrowed with `--path`, never on the root.
2. Cardinality lines answer most questions ("is status ever not 200?") without seeing rows.
3. stderr is summarized to five lines after the schema; the exit code is in the final tag.
4. `jq` is for narrowing, never dumping: after `shape`, `cmd | jq -c '.items[].id'` is fine and stays under the budget cap; `jq .` on a file or response is blocked.
