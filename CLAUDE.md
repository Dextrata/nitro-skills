# nitro-skills

Token-saving skills: `hashpatch`, `rerun`, `probe`, `seen`, `alias`,
`believe`, `refactor`, `mine`, `shape`, `trace`, `sdiff`, `q`, `blast`,
`recall`, `budget`. Optimizing token usage is a
priority in this repo, so treat the rules below as requirements, not
suggestions — use the skill whenever its trigger applies, don't fall back to
the default tool just because it's more familiar.

## Mandatory skill usage

- **Editing any existing file** → use `hashpatch` (outline/grep/patch) instead
  of Read+Edit. Exception: a file you are creating from scratch, or a change
  so small you already have the exact line ranges from a prior hashpatch
  `outline`/`grep` call in this session.
- **Running any test, build, or lint command more than once in a session**
  → use `rerun` instead of invoking it directly, so repeat runs report only
  the diff. First run of a given command can go through `rerun` too (it
  establishes the baseline for free).
- **Learning what a Python or JS module exports/its function signatures**
  → use `probe` instead of reading the module's source. Do not probe modules
  that start servers, touch the filesystem, or need secrets/network — read
  those normally.
- **Searching file contents** -> use ripgrep (`rg`) or the Grep tool, never
  grep/egrep/fgrep/findstr/Select-String. When piping into rg pass an explicit
  dash (`cmd | rg PATTERN -`): some builds ignore the pipe and silently search
  the working tree instead. Or redirect to a file first and search that.
- **Finding files by name or extension** -> use `fd` (`fd PATTERN [DIR]`,
  `-e py`, `-t f`), never `find`, `ls -R`, `tree`, or `Get-ChildItem
  -Recurse`. `fd` skips .gitignore'd and hidden paths, so the listing is short.
- **Text find-and-replace in a pipeline** -> use `sd` (`cmd | sd 'old' 'new'`,
  `$1` for groups, `-s` literal), never `sed`. Editing files in place is still
  `refactor` (`replace`) or `hashpatch`; `sd FILE` is blocked because the edit
  is unanchored.
- **Narrowing JSON after `shape`** -> `--path`, or a narrowing `jq` filter
  (`cmd | jq -c '.items[].id'`). Never `jq .` on a file or response.
- **Any command whose output may repeat lines already shown** (git diff, git
  log, rg with context, second test run) â†’ wrap in `seen`.
- **Output dense with long paths/hashes/dotted names** â†’ wrap in `alias`; refer
  to aliased strings as `Â§N` afterwards.
- **Confirming something you believe about a file you already saw** (a
  signature, members, an import, a call, a literal) â†’ `believe`, never a
  re-view.
- **Mechanical edits: rename, add-import, wrap a range, delete/move a symbol,
  regex across files** â†’ `refactor`, not one hashpatch patch per file.
- **Log-like output over ~100 lines** (build/server/CI/docker logs) â†’ `mine`.
- **JSON/CSV/table output or files** (curl, gh/aws/kubectl --json, package
  lockfiles, exports) â†’ `shape`, then `--path`.
- **Anything that may print a stack trace** â†’ wrap in `trace`.
- **Reviewing changes** â†’ `sdiff` instead of bare `git diff`/`git show`.
- **A structural code question that would take 2+ rg calls** ("who calls X",
  "which handlers are async", "outline of module M") â†’ `q`.
- **Before changing a signature, renaming, or deleting** â†’ `blast` once
  instead of grepping for callers.
- **Starting a "where/how is X handled" investigation** â†’ `recall ask` first;
  `recall save` with file:line refs when done.
- **A command denied by the budget hook** â†’ re-issue it through the shaper the
  message names; `budget report` shows what is eating tokens.

## Non-triggers (use judgment, skill is optional)

- Reading a brand-new file for the first time to understand it holistically.
- A file already fully in context from a recent read/outline this turn.
- One-off commands unlikely to be rerun (e.g. `git status`, `ls`).

If a task clearly matches a trigger above, invoke the skill without asking.
These rules are enforced by the nitro-skills PreToolUse hooks where installed;
a denied command names the skill to use. Append `#nitro-skip` only when the
exact raw command is genuinely required.
