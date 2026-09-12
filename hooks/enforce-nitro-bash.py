#!/usr/bin/env python3
"""
Optional PreToolUse hook for Bash/PowerShell: the shell is the usual way an
agent routes around the skills (cat/sed -n instead of hashpatch view, sed -i or
an inline python script instead of hashpatch apply, a bare test command instead
of rerun, grep instead of ripgrep, find instead of fd, sed instead of sd). This
hook denies those commands and names the tool or skill to use instead. Append
`#nitro-skip` to a command to let it through.

Install (project-level, in .claude/settings.json):

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
        }
      ]
    }
  }

Rules, first match wins:
  1. grep/egrep/fgrep/findstr/Select-String at command position -> use rg.
  2. `cmd | rg PATTERN` with no explicit `-` argument -> on some builds rg
     ignores the pipe and searches the working tree; pass `-` or a file.
  3. find / ls -R / tree / Get-ChildItem -Recurse -> use fd (gitignore-aware,
     far less output) or `q` for symbols.
  4. cat/type/Get-Content/sed -n/head/tail dumping more than LINES lines of an
     existing file, not piped onward -> hashpatch outline/grep/view, or probe.
  5. In-place edits of an existing file (sed -i, perl -i, sd with file args,
     > or >> redirection, tee, Set-Content/Out-File/Add-Content, python -/-c or
     node -e that writes a file) -> hashpatch apply or refactor. Redirecting
     into a new file is allowed.
  6. sed used as a stream transform (no -n, no -i) -> use sd: `cmd | sd 'a' 'b'`.
  7. `jq .` / `jq` with no filter (a whole-document dump) -> shape, then
     `--path` or a narrowing jq filter.
  8. A test/build/lint command not wrapped in rerun (rr.py) -> rerun.
"""
import json
import os
import re
import sys

LINES = 60
SKIP = "#nitro-skip"
# Command-position prefix: start of string, or after a separator/subshell.
POS = r"(?:^|[\n;|&(`]|\$\()\s*(?:sudo\s+|xargs\s+(?:-\S+\s+)*)?"
GREP = re.compile(POS + r"(grep|egrep|fgrep|findstr|Select-String|sls)\b", re.I)
PIPED_RG = re.compile(r"\|\s*rg\b((?:'[^']*'|\"[^\"]*\"|[^|;&\n'\"])*)")
FIND = re.compile(POS + r"(find\s+\S|ls\s+-[a-zA-Z]*R|tree\b|Get-ChildItem\b[^|;&\n]*-Recurse|gci\b[^|;&\n]*-Recurse)", re.I)
DUMP = re.compile(POS + r"(cat|type|Get-Content|gc|sed|head|tail)\b([^|;&\n>]*)", re.I)
EDIT = re.compile(POS + r"(?:sed\s+(?:-\S+\s+)*-i|sed\s+-[a-zA-Z]*i|perl\s+-[a-zA-Z]*i|tee\b|Set-Content\b|Out-File\b|Add-Content\b)", re.I)
SED_STREAM = re.compile(POS + r"sed\b([^|;&\n]*)", re.I)
SD = re.compile(POS + r"sd\b([^|;&\n]*)")
JQ_DUMP = re.compile(POS + r"jq(?:\s+-[a-zA-Z]+)*(?:\s+(?:'\.'|\"\.\"|\.))?\s*(?:$|[|;&\n]|\s+\S+\.json\b)", re.M)
REDIRECT = re.compile(r"(?<![0-9&<])>{1,2}\s*([^\s|;&>]+)")
INLINE = re.compile(POS + r"(?:python3?|py|node)\s+(?:-\S+\s+)*(?:-c|-e|-)(?=\s|$)", re.I)
WRITES = re.compile(r"open\([^)]*['\"][wa]\+?b?['\"]|\.write_(?:text|bytes)\(|writeFileSync|writeFile\(|Set-Content|Out-File")
RUNNER = re.compile(POS + r"(?:(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:test|build|lint|check|typecheck|verify)\S*|npx\s+(?:jest|vitest|mocha|tsc|eslint|playwright|prettier)\b|pytest\b|python3?\s+-m\s+pytest\b|cargo\s+(?:test|build|check|clippy)\b|go\s+(?:test|build|vet)\b|make\b|node\s+--test\b|dotnet\s+(?:test|build)\b|mvn\b|gradle\b)", re.I)
SD_VALUE_FLAGS = {"-f", "--flags", "-n", "--max-replacements"}


def sd_targets(args):
    """Positional args after flags: >2 means sd is editing files in place."""
    toks, out, skip = args.split(), [], False
    for t in toks:
        if skip:
            skip = False
            continue
        if t in SD_VALUE_FLAGS:
            skip = True
            continue
        if t.startswith("-") and len(t) > 1:
            continue
        out.append(t)
    return out


def deny(reason):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": reason + f" If this exact command is genuinely required, append {SKIP} to it."}}))
    return 0


def line_count(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return -1


def resolve(cwd, tok):
    tok = tok.strip("'\"")
    if not tok or tok.startswith("-") or tok.startswith("$") or tok in ("/dev/null", "NUL"):
        return None
    return tok if os.path.isabs(tok) else os.path.join(cwd, tok)


def dump_size(name, args):
    """Lines a cat/sed -n/head/tail invocation would print, and the file."""
    toks = args.split()
    files = [t for t in toks if not t.startswith("-") and not re.match(r"^\d+(,\d+)?p?$|^'\d+,\d+p'$|^\"\d+,\d+p\"$", t)]
    if name.lower() == "sed":
        if "-n" not in toks:
            return 0, None
        m = re.search(r"['\"]?(\d+),(\d+)p['\"]?", args)
        return (int(m.group(2)) - int(m.group(1)) + 1 if m else 10**9), (files[-1] if files else None)
    if name.lower() in ("head", "tail"):
        m = re.search(r"-n\s*(\d+)|-(\d+)\b", args)
        return (int(m.group(1) or m.group(2)) if m else 10), (files[-1] if files else None)
    return 10**9, (files[-1] if files else None)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    cmd = payload.get("tool_input", {}).get("command") or ""
    cwd = payload.get("cwd") or os.getcwd()
    if not cmd or SKIP in cmd:
        return 0

    m = GREP.search(cmd)
    if m:
        return deny(f"`{m.group(1)}` is blocked: use ripgrep (`rg -n PATTERN PATH`, `-l` for filenames, "
                    "`-g '!**/node_modules/**'` to exclude) or the Grep tool.")

    for m in PIPED_RG.finditer(cmd):
        if not re.search(r"(?:^|\s)-(?:\s|$)", m.group(1)):
            return deny("`cmd | rg PATTERN` needs an explicit `-`: on this build rg ignores the pipe and silently "
                        "searches the working tree instead. Use `cmd | rg PATTERN -`, or redirect to a file and search that.")

    m = FIND.search(cmd)
    if m:
        return deny(f"`{m.group(1).split()[0]}` is blocked: use fd (`fd PATTERN [DIR]`, `-e py` by extension, "
                    "`-t f` files only; it skips .gitignore'd and hidden paths) or the q skill for symbols.")

    for m in DUMP.finditer(cmd):
        rest = cmd[m.end():]
        if rest.lstrip().startswith("|"):
            continue  # feeding a pipeline, not dumping into context
        n, f = dump_size(m.group(1), m.group(2))
        path = resolve(cwd, f or "")
        if not path or not os.path.isfile(path):
            continue
        total = line_count(path)
        if min(n, total) > LINES:
            return deny(f"Dumping {min(n, total)} lines of {f} into context is blocked. Use the hashpatch skill: "
                        "`outline` for structure, `grep` for a pattern, `view A-B` for a range; or the probe skill "
                        "if you only need a module's API.")

    if EDIT.search(cmd):
        return deny("In-place shell edits (sed -i, perl -i, tee, Set-Content, Out-File) are blocked. Use the hashpatch "
                    "skill: `grep`/`view` to get anchors, then `apply` with hunks; or the refactor skill for rename/regex across files.")
    for m in SD.finditer(cmd):
        if len(sd_targets(m.group(1))) > 2:
            return deny("`sd` editing files in place is blocked: the edit is unanchored and unreviewable. Use the refactor skill "
                        "(`rf.py replace PATTERN REPL [PATH...]`) or hashpatch `apply`. `cmd | sd 'a' 'b'` as a stream transform is fine.")
    for m in SED_STREAM.finditer(cmd):
        if not re.search(r"(?:^|\s)-n\b", m.group(1)):
            return deny("`sed` as a stream transform is blocked: use sd, which needs no escaping and uses plain regex "
                        "(`cmd | sd 'old' 'new'`, `$1` for groups, `-s` for literal). For file edits use the refactor or hashpatch skill.")
    if JQ_DUMP.search(cmd):
        return deny("`jq .` dumps the whole document into context. Use the shape skill (`$SHAPE CMD` / `$SHAPE --file F`), "
                    "then `--path a.b[0]` or a narrowing jq filter (`jq -c '.items[] | .id'`).")
    for m in REDIRECT.finditer(cmd):
        path = resolve(cwd, m.group(1))
        if path and os.path.isfile(path):
            return deny(f"Overwriting or appending to the existing file {m.group(1)} by redirection is blocked. "
                        "Use the hashpatch skill (`apply`) so the edit is anchored and reviewable.")
    if INLINE.search(cmd) and WRITES.search(cmd):
        return deny("An inline script that writes files is blocked. Use the hashpatch skill (`apply`) for edits; "
                    "plain Write is fine for a brand-new file.")

    if RUNNER.search(cmd) and "rr.py" not in cmd:
        return deny("Test/build/lint commands go through the rerun skill so repeat runs print only the diff: "
                    "`python $HOME/.claude/skills/rerun/scripts/rr.py \"<command>\"` (quote a command that has pipes; use $HOME, not ~, so PowerShell expands it).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
