---
name: mine
description: REQUIRED for any command expected to print more than ~100 lines of log-like output — build logs, server logs, CI output, install/download output, verbose test runs, docker/kubectl logs, tail of a log file. Clusters the lines into templates with counts so 10,000 lines become a 20-line table. Never dump or tail a big log into context; mine it.
---

# mine

Logs are the same few sentences with different numbers. `mine` masks the numbers, paths, hashes and timestamps, clusters what is left (Drain-style), and prints one row per template: how many times, where it first and last appeared, and example values for each wildcard.

`MINE="python $HOME/.claude/skills/mine/scripts/mine.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

- `$MINE npm run build` / `$MINE docker compose logs` / `$MINE CMD...` - run and mine.
- `$MINE --file server.log` / `some-cmd | $MINE --stdin`.
- `$MINE --keep "error|fail|traceback" CMD` - templates, plus those lines verbatim.
- `$MINE --top 15 CMD` - fewer rows. `$MINE --show 3` - raw lines behind template 3 of the last run.

Example row: `  2 x184   L12-2210   <ts> GET <path> <n> <*>ms   [4:12|37]`

## Rules
1. `--keep` is how you see the errors; do not re-run the command bare to "see the real output".
2. Use `--show ID` only for the one template you need to investigate.
3. For test suites prefer `rerun`; use `mine` when the output is a stream of similar lines rather than a pass/fail list.
