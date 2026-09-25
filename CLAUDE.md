# nitro-skills

Token-saving skills: `hashpatch`, `rerun`, `fails`, `probe`, `refactor`,
`mine`, `shape`, `sdiff`, `q`, `scout`, `why`, `recall`, `budget`. Optimizing
token usage is a priority in this repo, so treat the rules below as
requirements, not suggestions — use the skill whenever its trigger applies,
don't fall back to the default tool just because it's more familiar.

## Mandatory skill usage

- **Starting work in a repo you have not oriented in this session**, or about
  to read package.json / pyproject.toml / Cargo.toml / go.mod / Makefile /
  Dockerfile / CI config / the README "to see what this is" → `scout` once,
  then open only what it names.
- **Editing any existing file** → use `hashpatch` (outline/grep/patch) instead
  of Read+Edit. Exception: a file you are creating from scratch, or a change
  so small you already have the exact line ranges from a prior hashpatch
  `outline`/`grep` call in this session.
- **Looking at the structure of any file** (code, markdown, YAML/TOML/JSON,
  Makefile, Dockerfile, SQL, notebook) → `hashpatch outline`, never a whole
  read.
- **Running tests, a linter or a type checker** (pytest, jest, vitest, cargo
  test, go test, tsc, eslint, ruff, mypy, pyright) → `fails`, on the FIRST run
  too; it prints only the failures and the new/still/fixed delta.
- **Running a build, script or any other command more than once in a
  session** → `rerun` instead of invoking it directly, so repeat runs report
  only the diff. First run can go through `rerun` too (free baseline).
- **Learning what a Python or JS module exports/its function signatures**
  → use `probe` instead of reading the module's source. Do not probe modules
  that start servers, touch the filesystem, or need secrets/network — outline
  those with hashpatch instead.
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
- **Mechanical edits: rename, add-import, wrap a range, delete/move a symbol,
  regex across files** → `refactor`, not one hashpatch patch per file.
- **Log-like output over ~100 lines** (build/server/CI/docker logs) → `mine`.
- **JSON/CSV/table output or files** (curl, gh/aws/kubectl --json, package
  lockfiles, exports) → `shape`, then `--path`.
- **Reviewing changes** → `sdiff` instead of bare `git diff`/`git show`.
- **Asking why a file or some lines are the way they are** (who changed it,
  when, in which commit) → `why FILE:A-B`, never `git log -p`, `git blame` or
  `git show`.
- **A structural code question that would take 2+ rg calls** ("who calls X",
  "which handlers are async", "outline of module M") → `q`.
- **Before changing a signature, renaming, or deleting** → `q blast NAME` once
  instead of grepping for callers.
- **Starting a "where/how is X handled" investigation** → `recall ask` first;
  `recall save` with file:line refs when done.
- **A command denied by the budget hook** → re-issue it through the shaper the
  message names; `budget report` shows what is eating tokens.

## Non-triggers (use judgment, skill is optional)

- Reading a brand-new small file for the first time to understand it
  holistically (under ~60 lines; above that, outline first).
- A file already fully in context from a recent read/outline this turn.
- One-off commands unlikely to be rerun (e.g. `git status`, `ls`).

If a task clearly matches a trigger above, invoke the skill without asking.
These rules are enforced by the nitro-skills PreToolUse hooks where installed;
a denied command names the skill to use. Append `#nitro-skip` only when the
exact raw command is genuinely required.
