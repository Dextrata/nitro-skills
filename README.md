# Nitro Skills by Dextrata
[nitroskills.com](https://nitroskills.com) - a gift to the community from [Dextrata](https://dextrata.com)

**Measured, not estimated: nitro-skills removes about 23% of the tool traffic a session sends to the model, which is about 7% of all its tokens.** Per operation the skills save 60 to 100% (see the benchmark table), but tool traffic is only 30% of a prompt. 436 real sessions on one machine show 9% less tool traffic per API call with the previous release; the changes in this release replay to a further 15% on the same sessions. Method and caveats in [Where the tokens actually go](#where-the-tokens-actually-go-642-real-sessions).

Skills that cut the number of tokens [Claude Code](https://claude.com/claude-code) burns while working. Each one is a short `SKILL.md` (the only part that ever enters Claude's context) plus a script that gets *executed*, never read. That is the trick: the clever logic costs zero tokens no matter how many times it is reused.

> **Claude Code only.** nitro-skills is built for Claude Code and nothing else.
> Every skill is loaded through Claude Code's `~/.claude/skills/` folder, and the
> enforcement that makes the savings reliable comes from Claude Code's
> `PreToolUse`/`PostToolUse` hooks in `~/.claude/settings.json`. Other AI coding
> tools (Cursor, GitHub Copilot, Codex, Gemini CLI, Aider, Windsurf and the rest)
> have no `SKILL.md` loader and no equivalent hook contract, so dropping this
> repo into one of them does nothing. The scripts underneath are plain stdlib
> Python and you can run them by hand anywhere, but the token savings only
> materialise when Claude invokes them for you.
>
> **Dextrata Agent** is the one exception: it implements the same `SKILL.md` loader
> and the same `PreToolUse`/`PostToolUse` hook contract (exit 2 + stderr, or
> `hookSpecificOutput.permissionDecision` / `updatedInput` on stdout), so this repo
> works there unchanged. Settings › Skills & MCP › nitro-skills clones it, runs
> `install.py` for you, wires the hooks, and keeps the checkout fast-forwarded.

Three core skills (`hashpatch`, `rerun`, `probe`) shrink reads, edits and repeated command output. `fails` turns a test, lint or type-check run into its failures plus a new/still/fixed delta. `scout` replaces the manifest-and-README reads at the start of a session. `why` replaces `git log -p` and `git blame`. The rest (`refactor`, `mine`, `shape`, `sdiff`, `q`, `recall`, `budget`) attack mechanical edits, logs, payloads, diffs, search hops and callers, re-derived facts, and unbounded floods. Every skill is invoked as `nitro <skill> ...`; the hook expands that to the script path. See [Skill reference](#skill-reference) below, and [Where the tokens actually go](#where-the-tokens-actually-go-642-real-sessions) for what 642 real sessions measured.

## Automatic install

```
python install.py
```

This installs everything into the global Claude directory (`~/.claude`), and
works unchanged on Windows, Linux, and macOS:

- Copies all 13 skill folders into `~/.claude/skills/`, and removes the five
  retired ones (`seen`, `alias`, `believe`, `trace`, `blast`) if an earlier
  install left them there.
- Copies all 4 hooks into `~/.claude/hooks/` and deletes the retired
  `expand-aliases.py` (and its `settings.json` entry).
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

Requires Claude Code plus Python 3 (already a dependency of every skill).
Restart Claude
Code, or start a new session, after installing so it picks up the new
`settings.json`.

You should also add rules to your project's `CLAUDE.md` to document when each
skill is required — installing/enforcing the hooks makes usage *mechanical*,
but a `CLAUDE.md` makes it *legible* to the agent. See [CLAUDE.md](CLAUDE.md)
in this repo for a working example you can adapt.

## Manual install

If you'd rather install by hand, or per-project instead of globally, copy
each folder into `~/.claude/skills/` (global) or `.claude/skills/` (per
project). With the hooks installed, skills are invoked as `nitro hp`,
`nitro fails`, `nitro q` and so on, and the hook expands the short form to the
script path. Without hooks, each SKILL.md gives the fallback path
`$HOME/.claude/skills/...` (works on macOS, Linux, and Windows) rather than
`~` because PowerShell does not expand `~` inside quoted arguments:

```
hashpatch/   SKILL.md  scripts/hp.py
rerun/       SKILL.md  scripts/rr.py
fails/       SKILL.md  scripts/fails.py
probe/       SKILL.md  scripts/probe.py
refactor/    SKILL.md  scripts/rf.py
mine/        SKILL.md  scripts/mine.py
shape/       SKILL.md  scripts/shape.py
sdiff/       SKILL.md  scripts/sdiff.py
q/           SKILL.md  scripts/q.py
scout/       SKILL.md  scripts/scout.py
why/         SKILL.md  scripts/why.py
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
| **fd** | find, ls -R, tree, Get-ChildItem -Recurse | required; skips .gitignore'd/hidden paths so listings are short. Backs file discovery in `q`, `scout`, `refactor` |
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

Installing the skills only makes them *available* - Claude still decides
whether to use them. **To make usage consistent and enforce the skills, you must
install the PreToolUse hooks** (see Hooks section below). Without them, Claude will
bypass the skills and use shell commands instead. You should also add rules to your
project's `CLAUDE.md` to document when each skill is required. See
[CLAUDE.md](CLAUDE.md) in this repo for a working example you can adapt.

## Hooks (required for skills to work)

Without the PreToolUse hooks, Claude will bypass the skills and use shell commands
instead (cat/sed -i for edits, bare test commands for runs, grep for searching).
Two `PreToolUse` hooks make skill usage mechanical: they expand the short `nitro <skill>` form, rewrite commands that have an exact skill equivalent, and deny the rest.

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

The rest add two optional hooks on the same `Bash|PowerShell` matcher.
`budget-guard.py` is `PreToolUse`; `budget-record.py` is `PostToolUse` (it
feeds the guard's predictions):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          { "type": "command", "command": "python /path/to/nitro-skills/hooks/enforce-nitro-bash.py" },
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
  `Bash|PowerShell`. Three jobs, in order. (1) Expands `nitro hp view F 1-9`
  to `python "<skills>/hashpatch/scripts/hp.py" view F 1-9` (names: hp rr
  fails probe rf mine shape sdiff q scout why rc budget sessions and the long
  skill names; a real `nitro` binary is untouched unless the next word is one
  of those). (2) Rewrites, via `updatedInput`, commands whose skill equivalent
  is exact: `sed -n A,Bp F`, `head -N F`, `tail -N F` and `cat F` over 60 lines
  become hashpatch view/outline; simple `grep` becomes `rg`; `cmd | rg PAT`
  gains its `-`; `find DIR -name G`, `ls -R` and `tree` become `fd`; `jq . F`
  becomes `shape`; tests, linters and type checkers get wrapped in `fails` and
  builds in `rerun`; a leading `cd DIR &&` is dropped when DIR is already the
  working directory. The rewritten command starts with `echo '[nitro: ...]'`
  so the transcript says what ran. Read-only rewrites carry
  `permissionDecision: allow`; anything that runs or writes keeps the normal
  permission flow (both forms verified live). (3) Denies what has no exact
  rewrite and names the skill: grep flags rg cannot map, in-place edits
  (`sed -i`, `perl -i`, `sd FILE`, `>`/`>>` redirection, `tee`, `Set-Content`,
  inline `python -`/`node -e` scripts that write), `sed` as a stream transform
  (use `sd`), dumps with extra arguments. Heredoc bodies are data and are never
  rewritten. Append `#nitro-skip` (as the last thing on the line) to a command
  that genuinely needs to bypass it.

The Read hook alone is not enough: an agent told to prefer the shell never
calls Read, so the Bash hook is the one that closes the gap.

- [hooks/budget-record.py](hooks/budget-record.py) - `PostToolUse`. Records
  lines and characters per command shape in `~/.cache/nitro/budget`.
- [hooks/budget-guard.py](hooks/budget-guard.py) - `PreToolUse`. Rewrites
  known floods that have an exact skill equivalent: unbounded `git log` gets
  `--oneline -20`, whole-file `git blame F` becomes `why --blame F`, `cat` of a
  `.json`/`.csv`/`.tsv` file becomes `shape --file`, of a `.log`/`.jsonl` file
  `mine --file`, raw `curl`/`gh api`/`kubectl -o json` gets wrapped in `shape`
  and `docker logs`/`journalctl` in `mine`. Denies `pip list`/`npm ls`/`env`
  dumps, and any command whose shape produced more than 120 lines last time
  unless it is routed through a skill or bounded (`| head`, `| sd`, a narrowing
  `| jq FILTER`, `-n`, `--oneline`, `--stat`). Shapes the enforce hook owns
  (grep, find, code dumps, jq, test runners) are left to it. `#nitro-skip`
  bypasses it.

## Skill reference

Each of these follows the same contract: a short `SKILL.md`, a stdlib-only
Python script, a one-line summary tag at the end of every output with the exit
code. All per-workspace state lives under `~/.cache/nitro/<skill>/<cwd-hash>`
(0700 on POSIX), except `recall`, which writes `.claude/recall.jsonl` in the
repo so it can be committed.

| skill | replaces | what it prints instead |
|---|---|---|
| **hashpatch** | `Read` then `Edit` on a file that already exists; reading a README, config or notebook to find a section; reading 60 lines to edit 5 | numbered lines under a lease (`view FILE SYMBOL` for one function, class or markdown section, or `view FILE A-B`); `outline` (code, markdown, YAML/TOML/JSON, Makefile, Dockerfile, SQL, notebooks) and `grep` with `N:HHHH` anchors; `apply` by bare line number under the lease; a two-line receipt back instead of the edited lines |
| **rerun** | re-running a build or script and re-reading the whole output | the first run as a baseline, then only the diff, or one `unchanged` line |
| **fails** | reading a test, lint or type-check run to find what failed, then reading it all again after the fix | the summary line, one block per failure (id, message, your frame), and `new / still / fixed` against the previous run |
| **probe** | reading a module's source just to learn its API | one signature per function and class, read off the imported module |
| **refactor** | one patch per file for rename / add-import / wrap / delete / move / regex | one line of intent in, one line per touched file out |
| **mine** | dumping or tailing a build/server log | Drain-style templates with counts and first/last line; `--keep error` for verbatim errors |
| **shape** | `cat data.json`, raw `curl`, `gh --json` | schema with types, cardinalities, min/max, 3 samples; `--path` to descend |
| **sdiff** | `git diff` | one row per changed symbol, classified ws / imports / comment / moved / real; `--hunk hN` on demand |
| **q** | 2-5 chained rg calls for a structural question; grepping for callers before an edit | one query over a cached symbol index (kind, name, span, params, calls, decorators); `q blast NAME` for def, callees, callers grouped by enclosing symbol, tests |
| **scout** | `cat package.json`, `cat pyproject.toml`, the README, `ls -R` at the start of a session | one screen: stack, test/build/lint/run commands, entry points, layout with sizes, CI, tooling, docs, biggest files |
| **why** | `git log -p -- FILE`, `git blame FILE`, `git show` | one row per commit that touched the file or the lines (sha, date, author, +/-, subject, refs); `--show SHA` for one hunk, `--blame` for runs of lines |
| **recall** | re-deriving "where is X handled" every session | the saved answer, each `file:line` ref re-validated by line hash (FRESH / STALE) |
| **budget** | discovering the flood after it happened; guessing where a session's tokens went | per-command token ledger; hooks rewrite or deny the next oversized run; `nitro sessions` measures every past session from the transcripts |

### hashpatch (explain like I'm 5)

Imagine you want your friend to fix one sentence in a book. The old way: you read them the *whole book*, then read the sentence out loud *again* so they know which one, then say the new sentence. That's three copies of a lot of words.

hashpatch shows you one chapter with numbered lines and a *seal* on the chapter: a short code computed from exactly those lines. You say "replace lines 42-44 with this new sentence, seal 3f9ac2". If anyone changed the chapter since you looked, the seal will not match and nothing happens, so it is safe. And it answers with a receipt ("lines 42-46 now, new seal 9b12e0"), not by reading your sentence back to you.

It also lets you ask for one chapter by name (`view FILE Pool.acquire`, or a README section by its heading), look at just the *chapter titles* (`outline`) - which works for a README's headings, a config file's keys, a Makefile's targets or a notebook's cells, not only code - or just the lines with a word you care about (`grep`), instead of the whole book.

### rerun (explain like I'm 5)

You run your build. It prints 300 lines. You fix one thing and run again. It prints 300 lines again, and 299 of them are exactly the same as before.

rerun remembers what the build said last time and only tells you *what's different*. If nothing changed, it says "nothing changed" in one line. It also ignores stuff that always looks different but doesn't matter, like the time on the clock or how many milliseconds something took.

### fails (explain like I'm 5)

The teacher hands back 300 graded tests. You do not want the 297 with a gold star; you want the 3 with red ink, the sentence that was wrong, and the page it was on. After you study, you want to know which of the 3 you fixed, which are still wrong, and whether you broke a new one. `fails` is that, for pytest, unittest, jest, vitest, mocha, go test, cargo test, dotnet test, tsc, eslint, ruff, mypy and pyright.

### probe (explain like I'm 5)

You want to know what buttons are on a remote control. The old way: read the entire instruction manual. probe just *picks up the remote and looks at it*. It imports the module and asks the running program "what functions do you have, and what do they take?" You get one line per function instead of the whole file. It even sees buttons the manual forgot to mention.

### refactor (explain like I'm 5)

"Rename Bob to Robert everywhere" is one sentence. It should not cost you rewriting every page that mentions Bob.

### mine (explain like I'm 5)

A log is the same five sentences with different numbers filled in. `mine` shows you the five sentences and how often each one happened.

### shape (explain like I'm 5)

You do not read a phone book to learn it has names and numbers. `shape` tells you the columns, how many rows, and shows you three.

### sdiff (explain like I'm 5)

"What changed?" should be answered "the login function, two lines", not by reading both versions.

### q (explain like I'm 5)

Instead of flipping through the whole book four times looking for every mention of a character, you ask the index. `q blast` is the same question asked before you rewrite the character: who talks to them, who they talk to, and which chapters test them.

### scout (explain like I'm 5)

New house. Instead of opening every cupboard, you get a note on the fridge: where the light switches are, how to turn on the heating, which rooms are big, and where the manual is. `scout` writes that note from the manifests, the Makefile, the CI config and the README, without printing any of them.

### why (explain like I'm 5)

"Why is this wall green?" is answered by three lines in a diary - who painted it, when, and what they wrote about it - not by re-reading every page. `why` follows a file or a few lines through git history and prints one line per change; `--blame` says who last touched each line without repeating the wall.

### recall (explain like I'm 5)

Yesterday you found where the keys are kept. Today you should not search the house again. `recall` writes it on the fridge, and checks the drawer is still there before trusting the note.

### budget (explain like I'm 5)

A grown-up who stops you before you pour the whole cereal box into the bowl, and tells you which cup to use instead.

### Composition

Shapers nest: `nitro mine nitro rr npm run build`, `nitro fails "pytest -q 2>&1"`, `nitro shape curl ...`. The last tag printed is the outermost skill's; every skill passes the inner exit code through.

---

## Test results

`python tests.py` builds throwaway repos/dirs in temp locations and exercises every script and hook (edit, rename, wrap, move, diff attribution, failure parsing and the new/still/fixed delta, repo orientation, line-range history, template mining, JSON/CSV shaping, doc/config/notebook outlines, memo staleness, budget deny/allow, fd/rg fallbacks, installer dry run). Five `unittest.TestCase` classes: `EnforceHookTests` (the enforce-nitro-bash hook, 53 allow/deny cases including the fd/sd/jq/fails rules), `CoreSkillTests` (hashpatch, rerun, probe - 14 cases), `SkillsTests` (the remaining skills, their hooks, `q blast`, and `q.list_files` agreement between `fd` and `os.walk`), `InstallerTests` (dry run prints the disclaimer and checks every tool without writing), and `BenchTests` (every `bench.py` scenario runs and yields a real measurement, and no skill is left without one).

Latest run:

```
Ran 35 tests in 10.7s

OK
```

All 35 tests pass. Run it yourself with:

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
| **hashpatch** | Edit one function in a 60-function file | Read whole file + Edit (old + new text) | outline + symbol view + lease patch + receipt | 3,548 | 1,064 | **70%** |
| **hashpatch-fair** | Same edit, disciplined ranged read | Read a 60-line range + Edit | symbol view + lease patch + receipt | 360 | 136 | **62%** |
| **hashpatch-docs** | Find a section in a 400-line README | Read the whole README | outline: headers with line numbers | 4,249 | 211 | **95%** |
| **probe** | Learn a module's API | Read whole module source | probe signatures | 3,525 | 159 | **95%** |
| **rerun** | Second run of a 300-line command | full 300-line output every run | diff vs stored baseline | 1,577 | 20 | **99%** |
| **fails** | 300-test suite, 3 failures, run twice | full pytest output, twice | failures once, then new/still/fixed | 828 | 283 | **66%** |
| **refactor** | Rename a symbol across 6 files | one patch per file (old + new per hit) | one line of intent, one line per file | 603 | 39 | **94%** |
| **mine** | A 4,000-line build log | dumping a 4,000-line build log | templates with counts | 58,918 | 94 | **100%** |
| **shape** | A 400-item JSON response | cat a 400-item JSON response | schema + 3 samples | 20,538 | 125 | **99%** |
| **sdiff** | Review a mixed change | git diff | one row per changed symbol, classified | 116 | 61 | **47%** |
| **q** | Structural question over 5 files | 4 chained rg calls with overlapping hits | 2 index queries | 4,780 | 37 | **99%** |
| **q-blast** | Find callers before an edit | rg -C 3 for every mention | q blast: def + callers grouped + callees | 782 | 586 | **25%** |
| **scout** | Orient in an unfamiliar repo | cat 6 manifests + README + file listing | one scout screen | 1,920 | 417 | **78%** |
| **why** | History behind 9 lines of a file | git log -p on the file | one row per commit touching the lines | 4,635 | 93 | **98%** |
| **recall** | Re-answer a past investigation | re-deriving the answer with rg + reads | saved answer, refs revalidated | 349 | 39 | **89%** |
| **budget** | Predict a flood before running it | running the command and flooding context | predicted size, denied before the flood | 58,918 | 4 | **100%** |

The scenarios are chosen to be the case the skill exists for, and they are not
all equally favourable. What the numbers actually say:

- **The shapers are the big, reliable wins.** `mine`, `shape`, `budget`, `q`,
  `why`, `rerun`, `probe` and the docs outline all clear 95%, because their
  output size is fixed by the *schema* of the answer, not by the size of the
  input. A 4,000-line log and a 400,000-line log both mine to about 20 lines;
  nine lines with 4 or 400 commits behind them print one row per commit.
- **The memory skills pay off on the second encounter**, not the first.
  `fails` (66%), `rerun` (99%) and `recall` (89%) measure the repeat, because
  the first run is the baseline they store. `fails` is measured against a
  compact `pytest -q` run with short tracebacks; verbose runners (jest, cargo,
  captured logs) push its number up, and its real value is the `new / still /
  fixed` line, which no text diff gives you.
- **`hashpatch` used to lose to a disciplined ranged read; now it wins both
  rows.** Against a whole-file read it saves 70%; against a 60-line ranged
  read plus `Edit` it saves 62%, where the previous release *cost* 38%. Three
  changes did it, each replayed on 642 real sessions before shipping (next
  section): `view FILE SYMBOL`, which shows the one function, class or
  markdown section you named instead of a 60-line window (only 12% of the
  lines in a pre-edit view used to end up near the edit); leased views, where
  one six-character hash covers the whole range instead of a hash on every
  line (8% of view output); and a two-line receipt after `apply` instead of
  echoing the edited region back (92% of apply output, the single biggest
  stream a skill ever admitted into context). Safety is unchanged in kind: a
  stale lease or anchor rejects the whole patch before anything is written.
  On a README, config or notebook the outline is the whole win (95%).
- **`scout` (78%) and `q blast` (25%) are the weakest**, and both are honest
  about it. `scout` prints roughly 400 tokens no matter how big the repo is,
  so it wins more on a real repo than on the fixture; `q blast` beats `rg -C
  3` mainly by not printing overlapping context windows, and it stays because
  it is the caller checklist before an edit, not a compression trick.
- **What was dropped, and why.** Earlier releases shipped `seen`, `alias`,
  `believe`, `trace` and `blast`. `alias` (42% in its best case, negative when
  strings do not repeat, plus a hook to maintain) and `blast` (25%,
  duplicating the `q` index) were the weakest rows. `believe`'s 98% was
  measured against a whole-file re-read that `hashpatch grep` already avoids,
  and it made the agent write a claims DSL to get there. `seen` overlapped
  `rerun` and hashpatch and only paid off when the agent guessed in advance
  that output would repeat. `trace`'s frame compaction now lives inside
  `fails`, where the traceback actually shows up. Fewer skills also means
  fewer `SKILL.md` descriptions competing for the agent's attention on every
  tool call.

**What a whole session saves is measured, not blended.** The per-scenario
percentages above measure only the tool traffic a skill touches. The next
section measures 642 real sessions and finds that tool traffic is about 30% of
every prompt, which bounds what any skill can do. The "25 to 40% of total
session tokens" estimate that used to sit here was too optimistic for the
prompt side and is withdrawn.

An earlier draft of this README claimed 45 to 60% and measured only hashpatch,
rerun and probe. The fair-baseline rows above corrected the number, and every
skill is now measured rather than asserted. Savings are smallest on greenfield
work and largest on maintenance work with big files and noisy output.

One effect the table cannot show: everything an agent reads stays in context and is re-sent on every later API call. The next section measures that residency directly.

### Where the tokens actually go (642 real sessions)

`nitro sessions` reads every Claude Code transcript on this machine (642
sessions of 50 KB or more, 67,100 API calls) and aggregates them. The numbers
below are from this machine; run it on yours. Prompt and output tokens come
from the API usage records in the transcripts; everything else is chars/4.

| what | measured |
|---|---|
| prompt tokens billed | 18.9 billion (99% cache reads), 281k per call on average |
| output tokens | 41.0 million, 66% of them reasoning that never enters the transcript |
| fixed part of every prompt (system prompt, tools, CLAUDE.md, skills) | 16% |
| tool results in the prompt | 19% |
| tool inputs the model wrote (commands, patches, Write bodies) | 11% |
| assistant prose and user text | 1% |
| the rest (harness-injected text, loaded tool schemas, in-turn thinking, chars/4 error) | ~52% |
| tool traffic older than 30 calls that is still re-sent | 26% of all prompt tokens |

**How the headline number was computed.** Sessions were bucketed by the share
of their file and shell tool calls (Bash, Read, Edit, Write, Grep, Glob) that
went through a nitro skill, excluding this repo's own sessions and anything
under 20 API calls. Per API call, sessions that used nitro for at least half
of those calls admitted 5% fewer tool-result tokens and wrote 15% fewer
tool-input tokens than sessions that never used it: 9% less tool traffic
together. Replaying this release's changes on the nitro sessions (receipts,
leases, the short form, dropped `cd`, rewrites instead of denials) removes a
further 15% of their tool traffic. Compounded that is 23% of tool traffic;
tool traffic is 30% of a prompt, so about 7% of all prompt tokens, and a
similar share of output tokens. This compares different sessions on different
tasks, so it is an estimate of the realized effect, not a controlled
experiment. It does not credit nitro for needing fewer calls per task (one `q`
instead of four `rg` calls), which per-call figures cannot see, and it does
not blame it for the much larger contexts of the nitro sessions (362k against
172k tokens per call), which come from longer sessions on bigger projects.
Reproduce it with `nitro sessions`.

| per API call | no nitro (185 sessions) | nitro for at least half of the calls (71 sessions) | change |
|---|---|---|---|
| tool-result tokens admitted | 311 | 295 | -5% |
| tool-input tokens written | 215 | 182 | -15% |
| tool traffic, both | 526 | 477 | -9% |
| this release, replayed on the nitro sessions | | | a further -15% of tool traffic |

Three findings follow, and they are the reasoning behind this release.

**1. Cost is residency, not admission.** With cache reads at a tenth of the
input price, prompt tokens are still about 91% of spend, because the whole
context is re-sent on every call. A tool result costs what it costs once, then
again on every later call until compaction. That is why every skill here
attacks admission (what enters context), and why the biggest lever of all,
dropping consumed tool traffic from context, is outside the skill layer: it is
a harness or API feature. 26% of every prompt is tool traffic older than 30
calls. No skill can pull that lever; this README says so rather than
pretending otherwise.

**2. hashpatch is optimal because it sits on the biggest admitted stream, and
that stream is now hashpatch's own output.** Of the 19 million tokens of tool
output admitted across these sessions, 43% came from hashpatch (19,587 calls,
417 tokens each), 17% from `cat`/`sed`/`head`/`tail`, 12% from `rg`, 6% from
the Read tool. Reads are two thirds of everything admitted. A skill that
shaves 5% off reads beats one that removes 95% of a stream nobody uses, which
is why `mine`'s 100% row matters less than `hashpatch`'s 70%, and why the only
skill-layer changes worth making were inside hashpatch and the hooks:

| change (replayed on the recorded outputs of those sessions) | tokens it would have saved |
|---|---|
| receipt instead of echoing the edited region after `apply` | 1,705,449 (92% of apply output) |
| leased views without a hash on every line | 332,107 (8% of view output) |
| `nitro <skill>` short form instead of `python $HOME/.claude/skills/...` and `VAR="python ..."` definitions | 562,739 output tokens (24,359 calls) |
| dropping `cd DIR &&` when DIR is the working directory | 216,035 output tokens |
| rewriting instead of denying (1,751 denials at 139 tokens per round trip) | 244,828 |

Symbol views cannot be replayed (the recordings hold the windows the agent
chose, not what it needed); the bound is that only 12% of the lines in a view
that preceded an edit were within three lines of that edit, and 29% of views
were never followed by an edit at all.

**3. The things that looked like levers and were not.** Repeated views (the
old `seen` idea) are 9% of hashpatch output: dedupe cannot pay. `rg` output
already shown in the same session is under 1%. Thinking is two thirds of
output tokens and no skill touches it. Skills reach at most the 30% of a
prompt that is tool traffic; the SKILL.md descriptions themselves are part of
the fixed 16%, which is one more reason the skill count went down, not up.

### Correctness and security review

All thirteen skills and the four hooks were reviewed and are covered by a
regression suite (`python tests.py`, 35 tests: hook allow/deny/rewrite behaviour, the
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
  `rerun`, `fails`, `mine` and `shape` pass a single argument to the shell so
  pipelines work; a multi-argument command is passed as an argv list with no
  shell. They add no quoting or escaping of their own, so the same care
  applies as typing the command yourself. `sdiff`, `why` and `recall` only
  ever invoke `git`; `q`, `scout` and `refactor` only ever invoke `rg`/`fd`.
- **Cached output is stored in plaintext and may contain secrets.** `rerun`
  (`~/.cache/rerun`), plus `fails`, `mine`, `sdiff`, `q` and `budget` (under
  `~/.cache/nitro/`) persist command output, file excerpts,
  symbol indexes and command history across runs. Anything a wrapped command
  prints lands there. These directories are created mode 0700 on POSIX; on
  Windows they inherit your profile's ACL. Use `rerun --forget` after commands
  that print credentials, and delete `~/.cache/nitro` to clear the rest.
- **`recall` writes into the repo by default.** Its store is
  `.claude/recall.jsonl` when a `.claude` directory exists (so a team's Claude
  sessions share it), otherwise `~/.cache/nitro/recall`. Treat it as committed
  content: don't save anything into it you would not push.
- **`probe` executes module top-level code** and prepends the current directory
  to `sys.path`, so a hostile repo could shadow a standard-library module name.
  This is the same exposure as running the project's tests. The skill instructs
  the agent not to probe modules that start servers, touch files, or need
  secrets. For JS targets it shells out to `node -e`.
- **Read-only skills stay read-only.** `q`, `scout`, `why` and `budget` only
  read source files, git metadata and their own caches; none of them writes
  to your tree.
- **The hooks decide or rewrite, they don't execute.** `enforce-nitro-bash`,
  `budget-guard` and `block-whole-file-reads` inspect the proposed tool input
  and return allow/deny JSON, or an `updatedInput` that swaps the command for
  its skill equivalent; they never run the command. A rewrite carries
  `permissionDecision: allow` only when every segment of the result is a
  read-only skill invocation, `rg`, `fd` or a read-only git command; anything
  that runs a test, a build, a network call or an edit goes through the normal
  permission flow. Heredoc bodies are never rewritten, and `#nitro-skip` only
  counts as the last thing on a line, so a pattern or a body that mentions it
  cannot disable the hook. `budget-record` appends output sizes to the
  history file.
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

**AI-generated output.** nitro-skills exists to be driven by Claude Code. AI systems
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
