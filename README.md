# Nitro Skills by Dextrata
[nitroskills.com](https://nitroskills.com) - a gift to the community from [Dextrata](https://dextrata.com)

Skills that cut the number of tokens an AI coding agent burns while working. Each one is a short `SKILL.md` (the only part that ever enters the model's context) plus a script that gets *executed*, never read. That is the trick: the clever logic costs zero tokens no matter how many times it is reused.

The first three (`hashpatch`, `rerun`, `probe`) shrink reads, edits and repeated command output. The rest (`seen`, `alias`, `believe`, `refactor`, `mine`, `shape`, `trace`, `sdiff`, `q`, `blast`, `recall`, `budget`) attack everything else: repeated output, long strings, reassurance reads, mechanical edits, logs, payloads, traces, diffs, search hops, re-derived facts, and unbounded floods. See [Skill reference](#skill-reference) below.

## Automatic install

```
python install.py
```

This installs everything into the global Claude directory (`~/.claude`), and
works unchanged on Windows, Linux, and macOS:

- Copies all 15 skill folders into `~/.claude/skills/`.
- Copies all 5 hooks into `~/.claude/hooks/`.
- Merges the hooks into `~/.claude/settings.json` (`PreToolUse`/`PostToolUse`
  entries on the `Bash|PowerShell` and `Read` matchers), without touching any
  existing settings you already have. Safe to re-run — it does not duplicate
  entries.
- Checks for Python, Node (optional, only for `probe js`), and the CLI tools
  the skills and hooks rely on - ripgrep, fd, sd (required) and jq (optional) -
  and, for anything missing, runs your system package manager (winget/choco/
  scoop, Homebrew, apt/dnf/pacman/zypper/apk, cargo as fallback) to install it.
  Linux package managers are run with `sudo` and may prompt for your password.
  `--no-tools` prints the commands instead of running them.

Flags:

```
python install.py --dry-run    # show what would happen, change nothing
python install.py --no-hooks   # copy skills only, skip settings.json
python install.py --no-tools   # do not run package managers; only print install hints
python install.py --yes        # accept the disclaimer non-interactively (scripts/CI)
```

The installer prints a disclaimer and stops until you type `I AGREE`; nothing
is copied, written, or installed before that. Without a terminal (CI, piped
stdin) it exits with code 2 unless `--yes` is passed, which counts as the same
acceptance. The same text is in [Disclaimer](#disclaimer) below. Read it.

Requires only Python 3 (already a dependency of every skill). Restart Claude
Code, or start a new session, after installing so it picks up the new
`settings.json`.

You should also add rules to your project's `CLAUDE.md` to document when each
skill is required — installing/enforcing the hooks makes usage *mechanical*,
but a `CLAUDE.md` makes it *legible* to the agent. See [CLAUDE.md](CLAUDE.md)
in this repo for a working example you can adapt.

## Manual install

If you'd rather install by hand, or per-project instead of globally, copy
each folder into `~/.claude/skills/` (global) or `.claude/skills/` (per
project). The SKILL.md one-liners reference the scripts via
`$HOME/.claude/skills/...` (works on macOS, Linux, and Windows) rather than
`~` because PowerShell does not expand `~` inside quoted arguments:

```
hashpatch/   SKILL.md  scripts/hp.py
rerun/       SKILL.md  scripts/rr.py
probe/       SKILL.md  scripts/probe.py
seen/        SKILL.md  scripts/seen.py
alias/       SKILL.md  scripts/al.py
believe/     SKILL.md  scripts/believe.py
refactor/    SKILL.md  scripts/rf.py
mine/        SKILL.md  scripts/mine.py
shape/       SKILL.md  scripts/shape.py
trace/       SKILL.md  scripts/trace.py
sdiff/       SKILL.md  scripts/sdiff.py
q/           SKILL.md  scripts/q.py
blast/       SKILL.md  scripts/blast.py
recall/      SKILL.md  scripts/recall.py
budget/      SKILL.md  scripts/budget.py
```

Requires Python 3. `probe js` also needs Node.

### External tools (required)

The skills and hooks assume a small set of fast, gitignore-aware CLI tools are
the *only* ones in use, and the Bash hook blocks the slow classics once it is
installed. Each one exists to cut output (and therefore tokens), not just time:

| tool | replaces | why |
|---|---|---|
| **ripgrep** (`rg`) | grep, egrep, findstr, Select-String | required; the only content search the hooks allow |
| **fd** | find, ls -R, tree, Get-ChildItem -Recurse | required; skips .gitignore'd/hidden paths so listings are short. Backs file discovery in `q`, `blast`, `refactor` |
| **sd** | sed (stream transforms) | required; plain regex, no escaping dance, so replacements work first time. In-place `sd FILE` is blocked - file edits go through `refactor`/`hashpatch` |
| **jq** | `python -c "import json..."`, `jq .` dumps | optional; for narrowing JSON *after* `shape`. `jq .` is blocked |

`refactor` also uses `rg -l` to pre-select the files that mention a name, so a
rename across a large tree reads only the files that need it.

The installer runs these for you for whatever is missing (`--no-tools` to only
print them). To install by hand:

**macOS:**
```
brew install ripgrep fd sd jq
```

**Linux (Debian/Ubuntu):** `fd` is packaged as `fdfind`; add a symlink so the
hook messages match. `sd` is not in the Debian/Ubuntu repos, use cargo.
```
sudo apt install ripgrep fd-find jq
ln -s "$(command -v fdfind)" ~/.local/bin/fd
cargo install sd
```

**Linux (Fedora):**
```
sudo dnf install ripgrep fd-find jq
cargo install sd
```

**Linux (Arch):**
```
sudo pacman -S ripgrep fd sd jq
```

**Windows:**
```
winget install BurntSushi.ripgrep.MSVC sharkdp.fd chmln.sd jqlang.jq   # Windows Package Manager
choco install ripgrep fd sd-cli jq                                      # Chocolatey
scoop install ripgrep fd sd jq                                          # Scoop
```

**Any platform (with Rust):**
```
cargo install ripgrep fd-find sd
```

Release pages: [ripgrep](https://github.com/BurntSushi/ripgrep/releases),
[fd](https://github.com/sharkdp/fd/releases), [sd](https://github.com/chmln/sd/releases),
[jq](https://jqlang.github.io/jq/download/). Verify with `rg --version`,
`fd --version`, `sd --version`, `jq --version`.

One ripgrep quirk to know: on some builds `cmd | rg PATTERN` ignores the pipe
and silently searches the working tree instead, so always pipe with an explicit
dash (`cmd | rg PATTERN -`) or redirect to a file and search that. The Bash
hook enforces this. If `fd` or `sd` is missing the skills fall back to Python
(`os.walk`, `re`) and keep working; only the hook messages point at a tool you
do not have.

Installing the skills only makes them *available* - the agent still decides
whether to use them. **To make usage consistent and enforce the skills, you must
install the PreToolUse hooks** (see Hooks section below). Without them, agents will
bypass the skills and use shell commands instead. You should also add rules to your
project's `CLAUDE.md` to document when each skill is required. See
[CLAUDE.md](CLAUDE.md) in this repo for a working example you can adapt.

## Hooks (required for skills to work)

Without the PreToolUse hooks, agents will bypass the skills and use shell commands
instead (cat/sed -i for edits, bare test commands for runs, grep for searching).
Two `PreToolUse` hooks make skill usage mechanical and unavoidable.

### Installing hooks

Both hooks are installed per-project in `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/nitro-skills/hooks/enforce-nitro-bash.py"
          }
        ]
      },
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/nitro-skills/hooks/block-whole-file-reads.py"
          }
        ]
      }
    ]
  }
}
```

Replace `/path/to/nitro-skills` with the actual path to this repo (absolute path recommended).
Both hooks take `python` and read the tool call as JSON on stdin.

The rest add three optional hooks on the same `Bash|PowerShell` matcher.
`expand-aliases.py` and `budget-guard.py` are `PreToolUse`; `budget-record.py`
is `PostToolUse` (it feeds the guard's predictions):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          { "type": "command", "command": "python /path/to/nitro-skills/hooks/enforce-nitro-bash.py" },
          { "type": "command", "command": "python /path/to/nitro-skills/hooks/expand-aliases.py" },
          { "type": "command", "command": "python /path/to/nitro-skills/hooks/budget-guard.py" }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          { "type": "command", "command": "python /path/to/nitro-skills/hooks/budget-record.py" }
        ]
      }
    ]
  }
}
```

**Global installation:** Add the hook paths to `~/.claude/settings.json`:
- **Unix (macOS/Linux):** `~/.claude/settings.json`
- **Windows:** `%USERPROFILE%\.claude\settings.json` (or `~/.claude/settings.json` with `$HOME` expansion)

Project-level hooks override global ones, so test per-project first in `.claude/settings.json`, then move them global once validated.

### Hook descriptions


CLAUDE.md rules are requests; an agent in a hurry, or one whose harness steers
it toward the shell, will still `cat` a file, `sed -i` an edit, or run `npm
test` bare. Two `PreToolUse` hooks make the rules mechanical. Each file's
docstring has the `.claude/settings.json` wiring; both take `python` and read
the tool call as JSON on stdin.

- [hooks/block-whole-file-reads.py](hooks/block-whole-file-reads.py) - denies a
  whole-file `Read` of an existing file over 60 lines and points at hashpatch
  `outline`/`grep`/`view` or probe. Ranged reads and new files pass.
- [hooks/enforce-nitro-bash.py](hooks/enforce-nitro-bash.py) - matcher
  `Bash|PowerShell`. Denies, in order: grep-family commands (use `rg`); `cmd |
  rg PATTERN` without an explicit `-`; `find`/`ls -R`/`tree`/`Get-ChildItem
  -Recurse` (use `fd`); `cat`/`sed -n`/`head`/`tail`/`Get-Content` dumping more
  than 60 lines of an existing file into context; in-place edits of an existing
  file (`sed -i`, `perl -i`, `sd FILE`, `>`/`>>` redirection, `tee`,
  `Set-Content`, inline `python -`/`node -e` scripts that write); `sed` as a
  stream transform (use `sd`); `jq .` whole-document dumps (use `shape`); and
  test/build/lint commands not wrapped in rerun. Creating a new file by
  redirection, `cmd | sd 'a' 'b'`, and piping a dump onward are allowed. Append
  `#nitro-skip` to a command that genuinely needs to bypass it.

The Read hook alone is not enough: an agent told to prefer the shell never
calls Read, so the Bash hook is the one that closes the gap.

- [hooks/expand-aliases.py](hooks/expand-aliases.py) - `PreToolUse`. Rewrites
  `§N` tokens (assigned by the `alias` skill) in a command back to the real
  string via `updatedInput`, so the agent can type `cat §3/config.py`.
- [hooks/budget-record.py](hooks/budget-record.py) - `PostToolUse`. Records
  lines and characters per command shape in `~/.cache/nitro/budget`.
- [hooks/budget-guard.py](hooks/budget-guard.py) - `PreToolUse`. Denies a
  command whose shape produced more than 120 lines last time unless it is
  routed through a shaping skill or bounded (`| head`, `| sd`, a narrowing
  `| jq FILTER`, `-n`, `--oneline`, `--stat`), and denies known floods on first
  sight (unbounded `git log`, `find`/`ls -R`/`tree`, `pip list`/`npm ls`/`env`,
  raw `curl`/`gh api`/`kubectl -o json`, `cat` or `jq .` of `.json`/`.csv`/`.log`,
  `docker logs`). Names the shaper or tool to use (`fd`, `shape`, `mine`, ...).
  `#nitro-skip` bypasses it.

## Skill reference

Each of these follows the same contract: a short `SKILL.md`, a stdlib-only
Python script, a one-line summary tag at the end of every output with the exit
code. All per-workspace state lives under `~/.cache/nitro/<skill>/<cwd-hash>`
(0700 on POSIX), except `recall`, which writes `.claude/recall.jsonl` in the
repo so it can be committed.

| skill | replaces | what it prints instead |
|---|---|---|
| **hashpatch** | `Read` then `Edit` on a file that already exists | `N:HHHH` anchored lines; `outline` / `grep` / `view` to locate, `apply` to patch, fresh anchors back |
| **rerun** | re-running tests / builds / linters and re-reading the whole output | the first run as a baseline, then only the diff, or one `unchanged` line |
| **probe** | reading a module's source just to learn its API | one signature per function and class, read off the imported module |
| **seen** | running a command whose output you partly saw already | the new lines; every block of 4+ lines shown before folds to `[seen #7 L12-40, 29 lines]` |
| **alias** | retyping/rereading deep paths, hashes, dotted names | `§N` tokens with a one-time legend; `§N` works in later commands (with the hook, in every command) |
| **believe** | re-reading a file to confirm what you think is in it | `OK`/`MISMATCH` per claim, mismatches carry the truth |
| **refactor** | one patch per file for rename / add-import / wrap / delete / move / regex | one line of intent in, one line per touched file out |
| **mine** | dumping or tailing a build/server log | Drain-style templates with counts and first/last line; `--keep error` for verbatim errors |
| **shape** | `cat data.json`, raw `curl`, `gh --json` | schema with types, cardinalities, min/max, 3 samples; `--path` to descend |
| **trace** | reading a 40-line traceback | user frames + message, library frames counted, recursion collapsed, repeats become one line |
| **sdiff** | `git diff` | one row per changed symbol, classified ws / imports / comment / moved / real; `--hunk hN` on demand |
| **q** | 2-5 chained rg calls for a structural question | one query over a cached symbol index (kind, name, span, params, calls, decorators) |
| **blast** | grepping for callers before an edit | def, callees, callers grouped by enclosing symbol, tests that mention it |
| **recall** | re-deriving "where is X handled" every session | the saved answer, each `file:line` ref re-validated by line hash (FRESH / STALE) |
| **budget** | discovering the flood after it happened | per-command token ledger; hooks deny the next oversized run and name the shaper |

### hashpatch (explain like I'm 5)

Imagine you want your friend to fix one sentence in a book. The old way: you read them the *whole book*, then read the sentence out loud *again* so they know which one, then say the new sentence. That's three copies of a lot of words.

hashpatch gives every line in the book a tiny sticker, like `42:ab3f`. Now you just say "replace sticker 42:ab3f with this new sentence." No re-reading. And if someone changed the book since you looked, the sticker won't match and nothing happens, so it is safe.

It also lets you look at just the *chapter titles* (`outline`), or just the lines with a word you care about (`grep`), instead of the whole book.

### rerun (explain like I'm 5)

You run your tests. They print 300 lines. You fix one thing and run again. They print 300 lines again, and 299 of them are exactly the same as before.

rerun remembers what the tests said last time and only tells you *what's different*. If nothing changed, it says "nothing changed" in one line. It also ignores stuff that always looks different but doesn't matter, like the time on the clock or how many milliseconds something took.

### probe (explain like I'm 5)

You want to know what buttons are on a remote control. The old way: read the entire instruction manual. probe just *picks up the remote and looks at it*. It imports the module and asks the running program "what functions do you have, and what do they take?" You get one line per function instead of the whole file. It even sees buttons the manual forgot to mention.

### seen (explain like I'm 5)

You show your friend the same page of the book twice. The second time they say "I already read that page" instead of reading it aloud again. `seen` remembers every 4-line stretch it has ever shown and folds repeats into a pointer.

### alias (explain like I'm 5)

Instead of saying "the red house on the corner of Maple Street and Fifth Avenue next to the bakery" every time, you agree to call it "house 3". `alias` does that for long paths and ids, and the hook lets you say "house 3" back.

### believe (explain like I'm 5)

You do not re-read the recipe to check it says two eggs. You ask "does it say two eggs?" and get yes or "no, three". Reading to confirm a belief is the most expensive way to say yes.

### refactor (explain like I'm 5)

"Rename Bob to Robert everywhere" is one sentence. It should not cost you rewriting every page that mentions Bob.

### mine (explain like I'm 5)

A log is the same five sentences with different numbers filled in. `mine` shows you the five sentences and how often each one happened.

### shape (explain like I'm 5)

You do not read a phone book to learn it has names and numbers. `shape` tells you the columns, how many rows, and shows you three.

### trace (explain like I'm 5)

A crash report lists every room the error walked through, including forty rooms in the library's basement. `trace` shows you only the rooms in your house.

### sdiff (explain like I'm 5)

"What changed?" should be answered "the login function, two lines", not by reading both versions.

### q / blast (explain like I'm 5)

Instead of flipping through the whole book four times looking for every mention of a character, you ask the index. `blast` is the same question asked before you rewrite the character.

### recall (explain like I'm 5)

Yesterday you found where the keys are kept. Today you should not search the house again. `recall` writes it on the fridge, and checks the drawer is still there before trusting the note.

### budget (explain like I'm 5)

A grown-up who stops you before you pour the whole cereal box into the bowl, and tells you which cup to use instead.

### Composition

Shapers nest: `$SEEN $MINE npm run build`, `$TR $RR pytest -q`, `$AL $SD --cached`. The last tag printed is the outermost skill's; every skill passes the inner exit code through.

---

## Test results

`python tests.py` builds throwaway repos/dirs in temp locations and exercises every script and hook (edit, rename, wrap, move, diff attribution, fold, alias round trip, trace dedupe, template mining, JSON/CSV shaping, memo staleness, budget deny/allow, fd/rg fallbacks, installer dry run). Five `unittest.TestCase` classes: `EnforceHookTests` (the enforce-nitro-bash hook, 47 allow/deny cases including the fd/sd/jq rules), `CoreSkillTests` (hashpatch, rerun, probe - 14 cases), `SkillsTests` (the remaining 12 skills, their hooks, and `q.list_files` agreement between `fd` and `os.walk`), `InstallerTests` (dry run prints the disclaimer and checks every tool without writing), and `BenchTests` (every `bench.py` scenario runs and yields a real measurement, and no skill is left without one).

Latest run:

```
Ran 33 tests in 12.2s

OK
```

All 33 tests pass. Run it yourself with:

```
python tests.py
```

---

## Anything else

### How many tokens does this save?

Every skill has a scenario in `bench.py`, which builds a fixture, runs the
command an agent would have run without the skill, runs the skill, and counts
both. Tokens are approximated as characters / 4. Reproduce the whole table with:

```
python bench.py            # summary
python bench.py --markdown # this table
```

| skill | task | baseline | with skill | baseline tok | skill tok | saved |
|---|---|---|---|---|---|---|
| **hashpatch** | Edit one function in a 60-function file | Read whole file + Edit (old + new text) | outline + grep + patch | 3,548 | 1,404 | **60%** |
| **hashpatch-fair** | Same edit, disciplined ranged read | Read a 60-line range + Edit | grep + patch | 360 | 497 | **-38%** |
| **probe** | Learn a module's API | Read whole module source | probe signatures | 3,525 | 159 | **95%** |
| **rerun** | Second run of a 300-line suite | full 300-line output every run | diff vs stored baseline | 1,577 | 20 | **99%** |
| **seen** | Re-showing output already seen | re-printing output already shown | folded pointers to earlier blocks | 3,525 | 805 | **77%** |
| **alias** | rg hits across a deep tree | repeated deep paths verbatim | §N tokens + one legend | 2,385 | 1,383 | **42%** |
| **believe** | Confirm 4 facts about a file | re-reading the file to confirm | OK/MISMATCH per claim | 3,525 | 60 | **98%** |
| **refactor** | Rename a symbol across 6 files | one patch per file (old + new per hit) | one line of intent, one line per file | 603 | 39 | **94%** |
| **mine** | A 4,000-line build log | dumping a 4,000-line build log | templates with counts | 58,918 | 94 | **100%** |
| **shape** | A 400-item JSON response | cat a 400-item JSON response | schema + 3 samples | 20,538 | 125 | **99%** |
| **trace** | The same crash twice | full traceback, twice while iterating | user frames once, then a pointer | 555 | 230 | **59%** |
| **sdiff** | Review a mixed change | git diff | one row per changed symbol, classified | 116 | 61 | **47%** |
| **q** | Structural question over 5 files | 4 chained rg calls with overlapping hits | 2 index queries | 4,780 | 37 | **99%** |
| **blast** | Find callers before an edit | rg -C 3 for every mention | def + callers grouped + callees | 782 | 585 | **25%** |
| **recall** | Re-answer a past investigation | re-deriving the answer with rg + reads | saved answer, refs revalidated | 349 | 39 | **89%** |
| **budget** | Predict a flood before running it | running the command and flooding context | predicted size, denied before the flood | 58,918 | 4 | **100%** |

The scenarios are chosen to be the case the skill exists for, and they are not
all equally favourable. What the numbers actually say:

- **The shapers are the big, reliable wins.** `mine`, `shape`, `budget`, `q`,
  `rerun` and `probe` all clear 95%, because their output size is fixed by the
  *schema* of the answer, not by the size of the input. A 4,000-line log and a
  400,000-line log both mine to about 20 lines.
- **The memory skills pay off on the second encounter**, not the first.
  `seen` (77%), `trace` (59%), `believe` (98%) and `recall` (89%) all measure
  the repeat, because the first run is the baseline they store. In a session
  that never revisits anything, they save nothing — that is the honest case.
- **`hashpatch` depends entirely on the baseline you compare against.** Against
  a whole-file read (what `Read` does by default) it saves 60%. Against a
  disciplined 60-line ranged read it *costs* 38%, which is why that row is in
  the table. Its value in that case is safety rather than tokens: a stale
  anchor is rejected instead of silently mis-editing. It also wins on the
  second and later edits to one file, since the post-apply anchors replace a
  re-read.
- **`alias` (42%) and `blast` (25%) are the weakest**, and both are
  input-shape-dependent. `alias` only wins when a few long strings recur many
  times; a unique long name per line compresses to nothing and the legend is
  pure overhead. `blast` beats `rg -C 3` mainly by not printing overlapping
  context windows.

**Blended expectation: roughly 25 to 40% of total session tokens** on typical
edit-test-iterate work in an existing codebase. The per-scenario percentages
above are much higher than that, and the gap is deliberate — the scenarios
measure the tool traffic a skill touches, while a session also contains system
prompt, conversation, reasoning and one-off commands that no skill changes.
Assumptions behind the blend:

- Tool traffic (reads, edits, command output) is 60 to 80% of a session.
- Reads and edits are about half of tool traffic, cut by ~50% on a realistic
  mix of whole-file and ranged habits.
- Command output is about a third, cut by ~60% (weighted toward real suites,
  not 10-line toys).
- The remainder (git, listings, one-off commands) is unchanged.
- The SKILL.md files cost ~500 tokens per session for the three core skills;
  the full set is loaded on demand, not up front.

An earlier draft of this README claimed 45 to 60% and measured only hashpatch,
rerun and probe. The fair-baseline rows above corrected the number, and the
remaining twelve skills are now measured rather than asserted. Savings are
smallest on greenfield work and largest on maintenance work with big files and
noisy output.

One effect not in the table: everything an agent reads stays in context and is re-sent on every later turn. Cutting a 4k-token read to 300 tokens saves ~3.7k tokens *per subsequent turn*, so the compounding benefit over a long session is larger than the per-task numbers suggest.

### Correctness and security review

All fifteen skills and the five hooks were reviewed and are covered by a
regression suite (`python tests.py`, 33 tests: hook allow/deny behaviour, the
core line-op edge cases, per-skill round-trips, the installer, and the
benchmark harness). Core edge cases exercised: trailing blank lines in patch
bodies, inserts inside replaced ranges, overlapping hunks, non-UTF-8 bytes,
missing trailing newline, CRLF, file creation, malformed anchors, carriage
returns in command output, timestamp/duration/temp-path churn, exit-code
transitions, shell pipelines, Windows drive letters in module paths, missing
modules. Bugs found and fixed during review: inserts inside a replaced range
were silently swallowed; non-UTF-8 files crashed; the last blank line of a
patch body was dropped; rerun swallowed the exit code on baseline runs and
split lines on stray carriage returns; probe split `C:\path` on the drive
colon.

Security properties:

- **No network, no eval, no dynamic code from input.** No script fetches a URL
  or passes input to `eval`/`exec`. The only code execution is deliberate:
  `probe` imports the module you name, and the wrapper skills run the command
  you type.
- **Two scripts write to your files.** `hashpatch` writes only the path you
  pass; `refactor` writes the files its path/pattern arguments select. Both are
  the same trust level as any Edit tool, neither keeps a backup, so rely on
  version control — `refactor --dry` reports the change set without writing.
  hashpatch anchors are 16-bit CRCs of the line *plus* the line number, so a
  wrong edit needs both a stale line number and a 1-in-65,536 hash collision on
  that exact line. Blank lines all hash to `0000`; anchor on a non-blank line
  when precision matters.
- **The wrapper skills run your command through the shell by design.**
  `rerun`, `seen`, `alias`, `mine`, `shape`, `trace` pass a single argument to
  the shell so pipelines work; a multi-argument command is passed as an argv
  list with no shell. They add no quoting or escaping of their own, so the same
  care applies as typing the command yourself. `sdiff` and `recall` only ever
  invoke `git`; `q` and `refactor` only ever invoke `rg`.
- **Cached output is stored in plaintext and may contain secrets.** `rerun`
  (`~/.cache/rerun`), plus `seen`, `alias`, `mine`, `trace`, `sdiff`, `q` and
  `budget` (under `~/.cache/nitro/`) persist command output, file excerpts,
  symbol indexes and command history across runs. Anything a wrapped command
  prints lands there. These directories are created mode 0700 on POSIX; on
  Windows they inherit your profile's ACL. Use `rerun --forget` after commands
  that print credentials, and delete `~/.cache/nitro` to clear the rest.
- **`recall` writes into the repo by default.** Its store is
  `.claude/recall.jsonl` when a `.claude` directory exists (so a team's agents
  share it), otherwise `~/.cache/nitro/recall`. Treat it as committed content:
  don't save anything into it you would not push.
- **`probe` executes module top-level code** and prepends the current directory
  to `sys.path`, so a hostile repo could shadow a standard-library module name.
  This is the same exposure as running the project's tests. The skill instructs
  the agent not to probe modules that start servers, touch files, or need
  secrets. For JS targets it shells out to `node -e`.
- **Read-only skills stay read-only.** `believe`, `blast`, `q` and `budget`
  only read source files and their own caches; none of them writes to your
  tree.
- **The hooks decide, they don't execute.** `enforce-nitro-bash`,
  `budget-guard` and `block-whole-file-reads` inspect the proposed tool input
  and return allow/deny JSON; they never run the command. `expand-aliases`
  rewrites `§N` tokens in a command back to the strings `alias` recorded, which
  means an alias table entry becomes part of a command line — the table is
  written only by `alias` from output you asked for, but an unexpected `§N` in
  a command is worth a look. `budget-record` appends output sizes to the
  history file. Append `#nitro-skip` to bypass a hook when the raw command is
  genuinely required.
- **File content, anchor hashes and cached output are data, not instructions.**
  Nothing in any script interprets file or command content as commands.

---

## Disclaimer

**What the installer does.** `install.py` copies the skill folders into
`~/.claude/skills/`, copies the hook scripts into `~/.claude/hooks/`, merges
hook entries into `~/.claude/settings.json`, and checks whether `rg`, `fd`,
`sd` and `jq` are on your PATH. For any that are missing it runs your system
package manager (winget, Chocolatey, Scoop, Homebrew, apt, dnf, pacman, zypper,
apk, or cargo) to install them, using `sudo` on Linux. `--no-tools` makes it
print the commands instead; `--dry-run` changes nothing.

**Third-party software.** ripgrep, fd, sd, jq, and every package manager you
might use to obtain them (Homebrew, apt, dnf, pacman, zypper, apk, winget,
Chocolatey, Scoop, cargo) are independent third-party projects that are not
developed, distributed, audited, endorsed, or controlled by the nitro-skills
authors. Suggested install commands are provided for convenience only. You
alone are responsible for verifying the source, integrity, licence, and
security of any software you install, and for any vulnerability, defect,
malware, supply-chain compromise, data loss, or other harm arising from it.

**AI-generated output.** nitro-skills is used by AI coding agents. AI systems
make mistakes: they can misread code, produce incorrect or insecure edits,
delete or overwrite data, run unintended commands, and report success when
something has failed. Nothing produced with or by these skills should be relied
upon without independent human review. Always inspect diffs, run your own
tests, and keep backups and version control. You are solely responsible for
every change made in your environment while these skills and hooks are in use.

**No warranty.** THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, ACCURACY, AND
NON-INFRINGEMENT. No advice or information, whether oral or written, obtained
from the authors or through the software creates any warranty.

**Limitation of liability.** TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE
LAW, IN NO EVENT SHALL THE AUTHORS, CONTRIBUTORS, OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY WHATSOEVER - WHETHER IN AN
ACTION OF CONTRACT, TORT (INCLUDING NEGLIGENCE), STRICT LIABILITY, OR
OTHERWISE - INCLUDING WITHOUT LIMITATION DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, CONSEQUENTIAL, OR PUNITIVE DAMAGES, LOSS OF DATA, LOSS OF PROFITS,
BUSINESS INTERRUPTION, SECURITY BREACHES, OR THE COST OF SUBSTITUTE GOODS OR
SERVICES, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE, ANY
THIRD-PARTY SOFTWARE IT REFERENCES, ANY OUTPUT OF AN AI SYSTEM USING IT, OR THE
USE OF OR OTHER DEALINGS IN THE SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
SUCH DAMAGES. Some jurisdictions do not allow certain exclusions or
limitations, in which case the above applies to the fullest extent permitted.

**Indemnity.** You agree to indemnify and hold harmless the authors,
contributors, and copyright holders from any claim, demand, loss, or expense
(including reasonable legal fees) arising out of your use of the software,
third-party tools, or AI-generated output.

By installing or using this software you acknowledge that you have read and
understood this disclaimer and accept full responsibility for the consequences.
If you do not agree, do not install or use it.
