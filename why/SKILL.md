---
name: why
description: REQUIRED instead of `git log -p`, `git log --follow`, `git blame` or `git show` when you want to know why a file or a range of lines is the way it is — who changed it, when, in which commit, with what message. Prints one line per commit that touched the file or the lines (sha, date, author, +/- inside the target, subject, issue refs), and fetches a single commit's hunk on request. Never run a bare `git log -p` or whole-file `git blame`.
---

# why

"Why is this here?" is answered by two or three commit messages, not by a diff stream. `why` follows a file or a line range through history with `git log -L` and prints a row per commit; `--show` fetches only the hunk of one commit that touched those lines; `--blame` groups a range into runs of lines that share their last commit, without printing the code you already have.

`nitro why FILE:A-B` is the short form; the nitro hook expands `nitro why` to `python $HOME/.claude/skills/why/scripts/why.py`. Without the hook installed, type that path (`$HOME`, never `~`: PowerShell does not expand `~` inside quotes). A bare `git blame FILE` or unbounded `git log` is rewritten by the hook anyway.

- `nitro why src/db/pool.py:80-104` - commits that touched those lines (the enclosing symbol is named). `nitro why src/db/pool.py:88` for one line.
- `nitro why src/db/pool.py` - the file's history, newest first, 12 rows; `-n 30` for more.
- `nitro why src/db/pool.py:80-104 --show 9f3c1ab` - only that commit's hunk for those lines.
- `nitro why --blame src/db/pool.py:80-104` - which commit last touched each run of lines.

Output:
```
why src/db/pool.py:80-104 (Pool.acquire)   4 commit(s)
  9f3c1ab  2026-03-02 JP           +12/-3     Add timeout to Pool.acquire  #142
  b7e21c0  2025-11-14 Ana          +4/-1      Retry on PoolExhausted  PLAT-88
  4d0a9e2  2025-08-03 JP           +2/-2      Rename conn -> connection
  0c1f7aa  2025-06-01 JP           +18/-0     Initial pool
[why: src/db/pool.py:80-104 (Pool.acquire), 4 commit(s); first 2025-06-01 0c1f7aa, last 2026-03-02 9f3c1ab; --show SHA for its hunk]
```

## Rules
1. Ask about the lines you care about, not the file: `FILE:A-B` from a hashpatch `view` or a `q` result. Whole-file history is for "is this file dead / who owns it".
2. The subject and refs usually answer the question. `--show` one commit only when you need the actual change; never page through several.
3. `--blame` replaces `git blame`; it prints no code, only sha/date/author per run of lines, so it is the cheap way to find the commit behind one line.
4. Only `git` is invoked and nothing is written. On a shallow clone the history stops where the clone does.
