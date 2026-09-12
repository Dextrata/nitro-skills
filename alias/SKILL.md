---
name: alias
description: REQUIRED wrapper for commands whose output is dense with long repeated strings — rg/grep results across deep directory trees, git log/diff --stat, stack traces, dependency trees, anything printing UUIDs or hashes. Replaces each recurring long string with a short §N token (legend printed once) and lets you use §N in later commands. Run the command through it instead of bare.
---

# alias

Deep paths, hashes and dotted module names are the most expensive tokens in tool output, and they repeat constantly. `alias` is LZ compression for the conversation: any string of 18+ chars that recurs gets a stable `§N` token for the rest of the session. You can type `§N` back in commands; the script (and the optional hook) expands it.

`AL="python $HOME/.claude/skills/alias/scripts/al.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

- `$AL rg -n "TODO" src` / `$AL git log --stat -20` / `$AL CMD...` - run, print `§N = string` for each NEW alias, then the compressed output.
- `$AL --stdin` - filter a pipeline.
- `$AL x §3/config.py` - expand tokens in any text. Arguments to `$AL CMD` are expanded automatically, so `$AL cat §3/config.py` just works.
- `$AL --legend` - the whole table. `--reset` clears it.

## Rules
1. Refer to aliased strings by `§N` in your own prose and commands; never retype the long form.
2. With `hooks/expand-aliases.py` installed, `§N` works in every Bash/PowerShell command, not only through `$AL`.
3. The legend line for an alias is printed exactly once. If you lost it, `--legend`.
