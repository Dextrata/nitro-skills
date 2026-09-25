# nitro-skills

Token-saving skills: `hashpatch`, `rerun`, `fails`, `probe`, `refactor`,
`mine`, `shape`, `sdiff`, `q`, `scout`, `why`, `recall`, `budget`. Optimizing
token usage is a priority in this repo, so treat the rules below as
requirements, not suggestions — use the skill whenever its trigger applies,
don't fall back to the default tool just because it's more familiar.

Invoke every skill in its short form: `nitro hp view FILE 40-80`,
`nitro fails pytest -q`, `nitro q blast NAME`. The PreToolUse hook expands
`nitro <skill>` to the script path (names: hp rr fails probe rf mine shape
sdiff q scout why rc budget sessions). Never define `HP="python ..."` shell
variables and never prefix a command with `cd DIR &&`: shell state does not
persist between calls, the working directory is already the project, and
both habits cost real output tokens (measured: ~780k across 642 sessions).

## Mandatory skill usage

- **Starting work in a repo you have not oriented in this session**, or about
  to read package.json / pyproject.toml / Cargo.toml / go.mod / Makefile /
  Dockerfile / CI config / the README "to see what this is" → `nitro scout`
  once, then open only what it names.
- **Editing any existing file** → `hashpatch`: `view FILE SYMBOL` or
  `view FILE A-B` (a leased view), then `apply` citing the lease and bare
  line numbers. Never Read+Edit. Exception: a file you are creating from
  scratch (Write).
- **Looking at part of a file** → `nitro hp view FILE SYMBOL` when you know
  the function, class or markdown section; `nitro hp outline FILE` (any file
  type: code, markdown, YAML/TOML/JSON, Makefile, Dockerfile, SQL, notebook)
  when you do not. Never a whole-file read over 60 lines.
- **Running tests, a linter or a type checker** (pytest, jest, vitest, cargo
  test, go test, tsc, eslint, ruff, mypy, pyright) → `nitro fails CMD`, on
  the FIRST run too; it prints only the failures and the new/still/fixed
  delta.
- **Running a build, script or any other command more than once in a
  session** → `nitro rr CMD`, so repeat runs report only the diff.
- **Learning what a Python or JS module exports/its function signatures**
  → `nitro probe` instead of reading the module's source. Do not probe
  modules that start servers, touch the filesystem, or need secrets/network —
  outline those instead.
- **Searching file contents** -> ripgrep (`rg`) or the Grep tool, never
  grep/egrep/fgrep/findstr/Select-String. When piping into rg pass an explicit
  dash (`cmd | rg PATTERN -`). The hook rewrites simple `grep` calls to `rg`
  for you; anything it cannot map is denied.
- **Finding files by name or extension** -> `fd` (`fd PATTERN [DIR]`,
  `-e py`, `-t f`), never `find`, `ls -R`, `tree`, or `Get-ChildItem
  -Recurse`.
- **Text find-and-replace in a pipeline** -> `sd` (`cmd | sd 'old' 'new'`),
  never `sed`. Editing files in place is `nitro rf replace` or hashpatch.
- **Narrowing JSON after `shape`** -> `--path`, or a narrowing `jq` filter.
  Never `jq .` on a file or response.
- **Mechanical edits: rename, add-import, wrap a range, delete/move a symbol,
  regex across files** → `nitro rf`, not one hashpatch patch per file.
- **Log-like output over ~100 lines** (build/server/CI/docker logs) →
  `nitro mine`.
- **JSON/CSV/table output or files** (curl, gh/aws/kubectl --json, lockfiles,
  exports) → `nitro shape`, then `--path`.
- **Reviewing changes** → `nitro sdiff` instead of bare `git diff`/`git show`.
- **Asking why a file or some lines are the way they are** (who changed it,
  when, in which commit) → `nitro why FILE:A-B`, never `git log -p`,
  `git blame` or `git show`.
- **A structural code question that would take 2+ rg calls** ("who calls X",
  "which handlers are async", "outline of module M") → `nitro q`.
- **Before changing a signature, renaming, or deleting** → `nitro q blast
  NAME` once instead of grepping for callers.
- **Starting a "where/how is X handled" investigation** → `nitro rc ask`
  first; `nitro rc save` with file:line refs when done.
- **A command denied by a hook** → re-issue it through the skill the message
  names. Most denials are now rewrites: the command runs through the right
  skill and the output starts with `[nitro: ...]` saying what changed.
  `nitro budget report` shows what is eating tokens; `nitro sessions` shows
  where whole sessions' tokens went.

## Non-triggers (use judgment, skill is optional)

- Reading a brand-new small file for the first time to understand it
  holistically (under ~60 lines; above that, outline first).
- A file already fully in context from a recent view this turn.
- One-off commands unlikely to be rerun (e.g. `git status`, `ls`).

If a task clearly matches a trigger above, invoke the skill without asking.
These rules are enforced by the nitro-skills PreToolUse hooks where installed.
Append `#nitro-skip` only when the exact raw command is genuinely required.
