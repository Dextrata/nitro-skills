# Nitro Skills by Dextrata

Skills that cut the number of tokens an AI coding agent burns while working. Each one is a short `SKILL.md` (the only part that ever enters the model's context) plus a script that gets *executed*, never read. That is the trick: the clever logic costs zero tokens no matter how many times it is reused.

## Install

Copy each folder into `~/.claude/skills/` (global) or `.claude/skills/` (per project):

```
hashpatch/   SKILL.md  scripts/hp.py
rerun/       SKILL.md  scripts/rr.py
probe/       SKILL.md  scripts/probe.py
```

Requires Python 3. `probe js` also needs Node.

**ripgrep is required.** The skills and the hooks assume `rg` is the only
search tool in use; grep, findstr and Select-String are blocked once the hook
below is installed. Install it with your package manager:

```
winget install BurntSushi.ripgrep.MSVC     # Windows
choco install ripgrep                      # Windows (Chocolatey)
scoop install ripgrep                      # Windows (Scoop)
brew install ripgrep                       # macOS
sudo apt install ripgrep                   # Debian/Ubuntu
sudo dnf install ripgrep                   # Fedora
cargo install ripgrep                      # anywhere with Rust
```

Binaries for every platform: https://github.com/BurntSushi/ripgrep/releases.
Check with `rg --version`. One quirk to know: on some builds `cmd | rg PATTERN`
ignores the pipe and silently searches the working tree instead, so always pipe
with an explicit dash (`cmd | rg PATTERN -`) or redirect to a file and search
that. The Bash hook enforces this.

Installing the skills only makes them *available* — the agent still decides
whether to use them. To make usage consistent, add rules to your project's
`CLAUDE.md` telling the agent when each skill is required (not optional). See
[CLAUDE.md](CLAUDE.md) in this repo for a working example you can adapt.

## Hooks (optional, enforce instead of request)

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
  rg PATTERN` without an explicit `-`; `cat`/`sed -n`/`head`/`tail`/`Get-Content`
  dumping more than 60 lines of an existing file into context; in-place edits of
  an existing file (`sed -i`, `perl -i`, `>`/`>>` redirection, `tee`,
  `Set-Content`, inline `python -`/`node -e` scripts that write); and
  test/build/lint commands not wrapped in rerun. Creating a new file by
  redirection and piping a dump onward are allowed. Append `#nitro-skip` to a
  command that genuinely needs to bypass it.

The Read hook alone is not enough: an agent told to prefer the shell never
calls Read, so the Bash hook is the one that closes the gap. `python
tests_hook.py` runs the 35-case suite for it.

---

## hashpatch (explain like I'm 5)

Imagine you want your friend to fix one sentence in a book. The old way: you read them the *whole book*, then read the sentence out loud *again* so they know which one, then say the new sentence. That's three copies of a lot of words.

hashpatch gives every line in the book a tiny sticker, like `42:ab3f`. Now you just say "replace sticker 42:ab3f with this new sentence." No re-reading. And if someone changed the book since you looked, the sticker won't match and nothing happens, so it is safe.

It also lets you look at just the *chapter titles* (`outline`), or just the lines with a word you care about (`grep`), instead of the whole book.

## rerun (explain like I'm 5)

You run your tests. They print 300 lines. You fix one thing and run again. They print 300 lines again, and 299 of them are exactly the same as before.

rerun remembers what the tests said last time and only tells you *what's different*. If nothing changed, it says "nothing changed" in one line. It also ignores stuff that always looks different but doesn't matter, like the time on the clock or how many milliseconds something took.

## probe (explain like I'm 5)

You want to know what buttons are on a remote control. The old way: read the entire instruction manual. probe just *picks up the remote and looks at it*. It imports the module and asks the running program "what functions do you have, and what do they take?" You get one line per function instead of the whole file. It even sees buttons the manual forgot to mention.

---

## How many tokens does this save?

Measured on real inputs (Python's `json/encoder.py`, ~4,200 tokens) and simulated test loops. Tokens approximated as characters / 4. Both the generous and the fair baseline are shown, because the answer depends heavily on what the agent would have done otherwise.

| Task | Baseline | With skill | Saved |
|---|---|---|---|
| Edit one function in a 4k-token file | Read whole file + Edit (old + new text) | outline + view slice + patch | **82%** |
| Same edit | Read a 60-line range + Edit | outline + view slice + patch | **~0%** |
| Learn a module's API | Read whole file | probe one-liners | **93%** |
| 4-run edit/test loop, 10-line output | full output every run | baseline + diffs | **47%** |
| 4-run edit/test loop, 300-line output | full output every run | baseline + diffs | **73%** |

What that table says honestly:

- **hashpatch** pays off when the alternative is a whole-file read (the default Read behaviour), and on the *second and later* edits to the same file, because the post-apply report replaces a re-read. On one surgical edit with a disciplined ranged read, it is a wash. Its unique value there is safety, not tokens: stale anchors are rejected instead of silently mis-editing.
- **probe** is the biggest single win and it is consistent. The output is a fixed small size regardless of how big the source is.
- **rerun** scales with output size. The bigger and noisier the test suite, the more it saves, because diffs stay small while full output grows.

**Estimated blended saving with all three skills together: roughly 25 to 40% of total session tokens** on typical edit-test-iterate work in an existing codebase. Assumptions:

- Tool traffic (reads, edits, command output) is 60 to 80% of a session. System prompt, conversation, and reasoning are untouched.
- Reads and edits are about half of tool traffic, cut by ~50% on a realistic mix of whole-file and ranged habits.
- Command output is about a third, cut by ~60% (weighted toward real suites, not 10-line toys).
- The remainder (git, listings, one-off commands) is unchanged.
- The three SKILL.md files cost ~500 tokens per session.

An earlier draft of this README claimed 45 to 60%. That number assumed every read was a whole-file read; the fair-baseline measurement above corrected it. Savings are smallest on greenfield work and largest on maintenance work with big files and noisy test output.

One effect not in the table: everything an agent reads stays in context and is re-sent on every later turn. Cutting a 4k-token read to 300 tokens saves ~3.7k tokens *per subsequent turn*, so the compounding benefit over a long session is larger than the per-task numbers suggest.

## Correctness and security review

All three scripts were reviewed and run through a 19-case regression suite (edge cases: trailing blank lines in patch bodies, inserts inside replaced ranges, overlapping hunks, non-UTF-8 bytes, missing trailing newline, CRLF, file creation, malformed anchors, carriage returns in command output, timestamp/duration/temp-path churn, exit-code transitions, shell pipelines, Windows drive letters in module paths, missing modules). Bugs found and fixed during review: inserts inside a replaced range were silently swallowed; non-UTF-8 files crashed; the last blank line of a patch body was dropped; rerun swallowed the exit code on baseline runs and split lines on stray carriage returns; probe split `C:\path` on the drive colon.

Security properties:

- **No network, no eval, no dynamic code from input.** hashpatch and rerun only parse text. probe imports the module you name, which is its entire purpose.
- **hashpatch** writes only the path you pass, same trust level as any Edit tool. Anchors are 16-bit CRCs of the line *plus* the line number, so a wrong edit needs both a stale line number and a 1-in-65,536 hash collision on that exact line. Blank lines all hash to `0000`; anchor on a non-blank line when precision matters.
- **rerun** runs a single-argument command through the shell by design so pipelines work; multi-argument commands are passed as an argv list with no shell. Cached output is stored under `~/.cache/rerun` in plaintext, so anything a command prints (including secrets) lands there. The directory is created mode 0700 on POSIX; on Windows it inherits your profile's ACL. Use `--forget` after commands that print credentials.
- **probe** executes module top-level code and prepends the current directory to `sys.path`, so a hostile repo could shadow a standard-library module name. This is the same exposure as running the project's tests. The skill instructs the agent not to probe modules that start servers, touch files, or need secrets.
- **Anchor hashes and cached output are data, not instructions.** Nothing in any script interprets file or command content as commands.
