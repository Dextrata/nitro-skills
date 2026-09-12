---
name: recall
description: REQUIRED at the start of any investigation of the form "where/how is X handled", "which file does Y", "how does the Z flow work" — ask recall BEFORE reading or searching, and SAVE the answer with file:line refs after any investigation that took more than two tool calls. Answers persist across sessions and are revalidated by line hashes, so a stale answer is flagged instead of trusted.
---

# recall

Every session re-derives the same facts about a codebase: where auth lives, how config loads, which module owns the queue. `recall` stores those answers with `file:line` refs and a hash of the referenced lines. Next session, asking costs one call and the answer says whether each ref still holds.

`RC="python $HOME/.claude/skills/recall/scripts/recall.py"`

Use `$HOME`, never `~` (PowerShell does not expand `~` inside quotes).

- `$RC ask "where is request auth handled"` - top matches, each ref marked fresh, changed, or missing.
- `$RC save "where is request auth handled" "middleware in src/api/auth.py:40-88 (verify_token); wired in src/app.py:23; tests tests/test_auth.py:1-60"`
- `$RC list [filter]` / `$RC forget ID` / `$RC refresh ID` (after you have re-verified a stale memo).

Stored in `.claude/recall.jsonl` when the repo has a `.claude` dir (commit it; every agent on the team benefits), else in the user cache.

## Rules
1. Ask before you search. A `FRESH` hit ends the investigation.
2. `STALE` refs mean those lines changed; the answer's shape is probably still right. Verify only the stale refs with hashpatch `view`, then `refresh`.
3. Save in the same message you finish an investigation. Include every `path:line` or `path:A-B` you relied on; only refs with line numbers get hashed.
4. Keep answers to three lines. The memo is a pointer, not a document.
