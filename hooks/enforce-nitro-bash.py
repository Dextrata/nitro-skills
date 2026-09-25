#!/usr/bin/env python3
"""
PreToolUse hook for Bash/PowerShell. Three jobs, in this order:

  1. Expand the short skill form. `nitro hp view FILE 40-80` becomes
     `python "<skills>/hashpatch/scripts/hp.py" view FILE 40-80`. Names: hp rr fails probe rf
     mine shape sdiff q scout why rc budget sessions, plus the long skill names. A real `nitro`
     binary is untouched unless the next word is one of those names. Measured over 642 real
     sessions, the long path form plus the VAR="python ..." definitions it invites cost ~560k
     output tokens.
  2. Rewrite instead of deny when the nitro equivalent is exact: `sed -n A,Bp F`, `head -N F`,
     `tail -N F` and `cat F` (over LINES lines) -> hashpatch view/outline; simple `grep` -> `rg`;
     `cmd | rg PAT` -> `cmd | rg PAT -`; `find DIR -name G` / `ls -R` / `tree` -> `fd`; `jq . F`
     -> shape; tests, linters and type checkers -> fails; builds -> rerun; and a leading
     `cd CWD &&` when CWD is already the working directory. The rewritten command starts with
     `echo '[nitro: ...]'` so the transcript shows what ran. A deny-and-retry round trip costs
     ~140 tokens (measured); a rewrite costs the echo line. Read-only rewrites are returned as
     `allow`; anything that runs or writes keeps the normal permission flow.
  3. Deny what has no exact rewrite and name the skill: grep flags rg cannot map, in-place edits
     (sed -i, perl -i, sd FILE, > FILE, tee, Set-Content, inline python/node that writes), sed as
     a stream transform (use sd), dumps with extra arguments.

Append `#nitro-skip` to a command to let it through untouched.

Install (project-level, in .claude/settings.json):
  {"hooks": {"PreToolUse": [{"matcher": "Bash|PowerShell", "hooks": [
      {"type": "command", "command": "python /path/to/nitro-skills/hooks/enforce-nitro-bash.py"}]}]}}
"""
import json
import os
import re
import shlex
import sys

LINES = 60
SKIP = re.compile(r"(?:^|\s)#nitro-skip\s*$", re.M)   # only as the last thing on a line, never inside a pattern or a body
HEREDOC = re.compile(r"<<-?\s*['\"]?\w+['\"]?[^\n]*\n")
HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = {"hp": ("hashpatch", "hp.py"), "hashpatch": ("hashpatch", "hp.py"), "rr": ("rerun", "rr.py"), "rerun": ("rerun", "rr.py"),
          "fails": ("fails", "fails.py"), "probe": ("probe", "probe.py"), "rf": ("refactor", "rf.py"), "refactor": ("refactor", "rf.py"),
          "mine": ("mine", "mine.py"), "shape": ("shape", "shape.py"), "sdiff": ("sdiff", "sdiff.py"), "q": ("q", "q.py"),
          "scout": ("scout", "scout.py"), "why": ("why", "why.py"), "rc": ("recall", "recall.py"), "recall": ("recall", "recall.py"),
          "budget": ("budget", "budget.py"), "sessions": ("budget", "sessions.py")}
DATA_EXT = (".json", ".csv", ".tsv", ".log", ".lock", ".ndjson", ".jsonl")   # budget-guard owns dumps of these
# Command-position prefix: start of string, or after a separator/subshell.
POS = r"(?:^|[\n;|&(`]|\$\()\s*(?:sudo\s+|xargs\s+(?:-\S+\s+)*)?"
NITRO = re.compile(r"(^|[\s;|&(`]|\$\()nitro\s+(" + "|".join(sorted(SKILLS, key=len, reverse=True)) + r")\b")
GREP = re.compile("(" + POS + r")(grep|egrep|fgrep|findstr|Select-String|sls)\b([^|;&\n]*)", re.I)
PIPED_RG = re.compile(r"\|\s*rg\b((?:'[^']*'|\"[^\"]*\"|[^|;&\n'\"])*)")
FIND = re.compile("(" + POS + r")(find\s+[^|;&\n]*|ls\s+-[a-zA-Z]*R[a-zA-Z]*(?:\s+[^|;&\n]*)?|tree\b[^|;&\n]*|Get-ChildItem\b[^|;&\n]*-Recurse[^|;&\n]*|gci\b[^|;&\n]*-Recurse[^|;&\n]*)", re.I)
DUMP = re.compile("(" + POS + r")(cat|type|Get-Content|gc|sed|head|tail)\b([^|;&\n>]*)", re.I)
EDIT = re.compile(POS + r"(?:sed\s+(?:-\S+\s+)*-i|sed\s+-[a-zA-Z]*i|perl\s+-[a-zA-Z]*i|tee\b|Set-Content\b|Out-File\b|Add-Content\b)", re.I)
SED_STREAM = re.compile(POS + r"sed\b([^|;&\n]*)", re.I)
SD = re.compile(POS + r"sd\b([^|;&\n]*)")
JQ_DUMP = re.compile(POS + r"jq(?:\s+-[a-zA-Z]+)*(?:\s+(?:'\.'|\"\.\"|\.))?\s*(?:$|[|;&\n]|\s+\S+\.json\b)", re.M)
JQ_SEG = re.compile("(" + POS + r")jq\b([^|;&\n]*)")
REDIRECT = re.compile(r"(?<![0-9&<])>{1,2}\s*([^\s|;&>]+)")
INLINE = re.compile(POS + r"(?:python3?|py|node)\s+(?:-\S+\s+)*(?:-c|-e|-)(?=\s|$)", re.I)
WRITES = re.compile(r"open\([^)]*['\"][wa]\+?b?['\"]|\.write_(?:text|bytes)\(|writeFileSync|writeFile\(|Set-Content|Out-File")
RUNNER = re.compile(POS + r"(?:(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:test|build|lint|check|typecheck|verify)\S*|npx\s+(?:jest|vitest|mocha|tsc|eslint|playwright|prettier)\b|pytest\b|python3?\s+-m\s+(?:pytest|unittest|mypy|ruff|flake8|pylint)\b|cargo\s+(?:test|build|check|clippy)\b|go\s+(?:test|build|vet)\b|make\b|node\s+--test\b|dotnet\s+(?:test|build)\b|mvn\b|gradle\b|ruff\s+(?:check|format)\b|mypy\b|pyright\b|flake8\b|pylint\b|eslint\b|tsc\b|jest\b|vitest\b|mocha\b)", re.I)
TESTY = re.compile(r"test|lint|check|typecheck|verify|pytest|unittest|jest|vitest|mocha|tsc\b|eslint|ruff|mypy|pyright|flake8|pylint|clippy|\bvet\b", re.I)
CD = re.compile(r"^\s*cd\s+(\"[^\"]*\"|'[^']*'|\S+)\s*(?:&&|;)\s*")
SD_VALUE_FLAGS = {"-f", "--flags", "-n", "--max-replacements"}
GREP_MAP = {"n": "-n", "i": "-i", "l": "-l", "w": "-w", "v": "-v", "c": "-c", "F": "-F", "h": "-I", "o": "-o", "s": "--no-messages", "L": "--files-without-match"}
GREP_DROP = {"r", "R", "E", "H"}
SAFE_SEG = re.compile(r"^\s*(?:echo\s+'\[nitro:[^']*\]'|python\s+\"[^\"]*[/\\](?:hashpatch[/\\]scripts[/\\]hp|scout[/\\]scripts[/\\]scout|why[/\\]scripts[/\\]why|sdiff[/\\]scripts[/\\]sdiff|q[/\\]scripts[/\\]q|budget[/\\]scripts[/\\]\w+)\.py\"(?!\s+apply\b)[^|;&]*"
                      r"|python\s+\"[^\"]*[/\\](?:shape[/\\]scripts[/\\]shape|mine[/\\]scripts[/\\]mine)\.py\"\s+--(?:file|stdin)\b[^|;&]*|python\s+\"[^\"]*recall[/\\]scripts[/\\]recall\.py\"\s+(?:ask|list)\b[^|;&]*"
                      r"|rg\b[^|;&]*|fd\b[^|;&]*|git\s+(?:status|diff|log|show|blame|rev-parse|branch)\b[^|;&]*|(?:ls|pwd|wc|head|tail|cat|sort|uniq|echo|true)\b[^|;&]*)\s*$")


def skill_path(name):
    skill, script = SKILLS[name]
    for base in (os.path.dirname(HERE), os.path.join(os.path.expanduser("~"), ".claude", "skills")):
        p = os.path.join(base, skill, "scripts", script)
        if os.path.isfile(p):
            return p.replace("\\", "/")
    return os.path.join(os.path.expanduser("~"), ".claude", "skills", skill, "scripts", script).replace("\\", "/")


def call(name):
    return f'python "{skill_path(name)}"'


def q(s):
    return shlex.quote(s)


def positional(args, value_flags=()):
    """Positional tokens of a segment, honouring quotes."""
    try:
        toks = shlex.split(args)
    except ValueError:
        toks = args.split()
    out, skip = [], False
    for t in toks:
        if skip:
            skip = False
            continue
        if t in value_flags:
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
    m = re.match(r"^/([a-zA-Z])/(.*)$", tok)          # Git Bash drive form
    if m and os.name == "nt":
        tok = f"{m.group(1).upper()}:/{m.group(2)}"
    return tok if os.path.isabs(tok) else os.path.join(cwd, tok)


def same_dir(a, b):
    return os.path.normcase(os.path.normpath(os.path.abspath(a))) == os.path.normcase(os.path.normpath(os.path.abspath(b)))


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


def translate_grep(kind, args, piped):
    try:
        toks = shlex.split(args)
    except ValueError:
        return None
    out = ["rg"] + (["-F"] if kind == "fgrep" else [])
    pat, paths, i = None, [], 0
    while i < len(toks):
        t = toks[i]
        if t == "--":
            paths += toks[i + 1:]
            break
        if t.startswith("--include="):
            out += ["-g", q(t.split("=", 1)[1])]
        elif t.startswith("--exclude-dir="):
            out += ["-g", q("!**/" + t.split("=", 1)[1].strip("/") + "/**")]
        elif t.startswith("--exclude="):
            out += ["-g", q("!" + t.split("=", 1)[1])]
        elif t in ("--color=never", "--no-color", "--color=auto"):
            pass
        elif re.fullmatch(r"-[a-zA-Z]+", t):
            for c in t[1:]:
                if c in GREP_MAP:
                    out.append(GREP_MAP[c])
                elif c not in GREP_DROP:
                    return None
        elif t in ("-A", "-B", "-C", "-m") and i + 1 < len(toks) and toks[i + 1].isdigit():
            out += [t, toks[i + 1]]
            i += 1
        elif re.fullmatch(r"-[ABCm]\d+", t):
            out.append(t)
        elif t == "-e" and i + 1 < len(toks):
            out += ["-e", q(toks[i + 1])]
            pat = pat or toks[i + 1]
            i += 1
        elif t.startswith("-"):
            return None
        elif pat is None:
            pat = t
            out.append(q(t))
        else:
            paths.append(t)
        i += 1
    if pat is None:
        return None
    out += [q(p) for p in paths]
    if piped and not paths:
        out.append("-")
    return " ".join(out)


def translate_find(seg):
    try:
        toks = shlex.split(seg)
    except ValueError:
        return None
    if not toks:
        return None
    head = toks[0].lower()
    if head in ("tree", "ls"):
        dirs = [t for t in toks[1:] if not t.startswith("-")]
        return "fd -t f . " + " ".join(q(d) for d in dirs) if dirs else "fd -t f"
    if head != "find":
        return None
    dirs, glob, ftype, i = [], None, None, 1
    while i < len(toks):
        t = toks[i]
        if t in ("-name", "-iname") and i + 1 < len(toks):
            glob = toks[i + 1]
            i += 2
            continue
        if t == "-type" and i + 1 < len(toks) and toks[i + 1] in ("f", "d"):
            ftype = toks[i + 1]
            i += 2
            continue
        if t.startswith("-"):
            return None
        dirs.append(t)
        i += 1
    out = ["fd"] + (["-t", ftype] if ftype else []) + (["-g", q(glob)] if glob else ["."]) + [q(d) for d in dirs]
    return " ".join(out)


def check(cmd, cwd):
    """('allow',) | ('deny', reason) | ('rewrite', new_cmd, note)"""
    def swap(m, new):
        return cmd[:m.start()] + m.group(1) + new + cmd[m.end():]

    for m in GREP.finditer(cmd):
        kind = m.group(2).lower()
        if kind in ("grep", "egrep", "fgrep"):
            new = translate_grep(kind, m.group(3), "|" in m.group(1))
            if new:
                return ("rewrite", swap(m, new), f"{kind} -> rg")
        return ("deny", f"`{m.group(2)}` is blocked: use ripgrep (`rg -n PATTERN PATH`, `-l` for filenames, "
                        "`-g '!**/node_modules/**'` to exclude) or the Grep tool.")

    for m in PIPED_RG.finditer(cmd):
        if not re.search(r"(?:^|\s)-(?:\s|$)", m.group(1)):
            new = cmd[:m.end()].rstrip() + " -" + cmd[m.end():]
            return ("rewrite", new, "rg reads the pipe only with an explicit -")

    m = FIND.search(cmd)
    if m:
        new = translate_find(m.group(2))
        if new:
            return ("rewrite", swap(m, new), f"{m.group(2).split()[0]} -> fd (gitignore-aware)")
        return ("deny", f"`{m.group(2).split()[0]}` is blocked: use fd (`fd PATTERN [DIR]`, `-e py` by extension, "
                        "`-t f` files only; it skips .gitignore'd and hidden paths) or the q skill for symbols.")

    for m in DUMP.finditer(cmd):
        rest = cmd[m.end():]
        if rest.lstrip().startswith("|"):
            continue  # feeding a pipeline, not dumping into context
        name, args = m.group(2), m.group(3)
        n, f = dump_size(name, args)
        path = resolve(cwd, f or "")
        if not path or not os.path.isfile(path) or path.lower().endswith(DATA_EXT):
            continue
        total = line_count(path)
        if min(n, total) <= LINES:
            continue
        pos = positional(args, ("-n",))
        low = name.lower()
        if low in ("cat", "type", "get-content", "gc") and pos == [f]:
            return ("rewrite", swap(m, f"{call('hp')} outline {q(f)}"), f"{name} {f} -> hp outline (view A-B or grep for lines)")
        if low == "sed" and pos == [f]:
            r = re.search(r"['\"]?(\d+),(\d+)p['\"]?", args)
            if r:
                return ("rewrite", swap(m, f"{call('hp')} view {q(f)} {r.group(1)}-{r.group(2)}"), f"sed -n -> hp view {r.group(1)}-{r.group(2)}")
        if low == "head" and pos == [f]:
            return ("rewrite", swap(m, f"{call('hp')} view {q(f)} 1-{n}"), f"head -> hp view 1-{n}")
        if low == "tail" and pos == [f]:
            a = max(1, total - n + 1)
            return ("rewrite", swap(m, f"{call('hp')} view {q(f)} {a}-{total}"), f"tail -> hp view {a}-{total}")
        return ("deny", f"Dumping {min(n, total)} lines of {f} into context is blocked. Use the hashpatch skill: "
                        "`outline` for structure, `grep` for a pattern, `view A-B` or `view SYMBOL` for a slice; or the probe skill "
                        "if you only need a module's API.")

    if EDIT.search(cmd):
        return ("deny", "In-place shell edits (sed -i, perl -i, tee, Set-Content, Out-File) are blocked. Use the hashpatch "
                        "skill: `view`/`grep` to get a lease or anchors, then `apply`; or the refactor skill for rename/regex across files.")
    for m in SD.finditer(cmd):
        if len(positional(m.group(1), SD_VALUE_FLAGS)) > 2:
            return ("deny", "`sd` editing files in place is blocked: the edit is unanchored and unreviewable. Use the refactor skill "
                            "(`rf.py replace PATTERN REPL [PATH...]`) or hashpatch `apply`. `cmd | sd 'a' 'b'` as a stream transform is fine.")
    for m in SED_STREAM.finditer(cmd):
        if not re.search(r"(?:^|\s)-n\b", m.group(1)):
            return ("deny", "`sed` as a stream transform is blocked: use sd, which needs no escaping and uses plain regex "
                            "(`cmd | sd 'old' 'new'`, `$1` for groups, `-s` for literal). For file edits use the refactor or hashpatch skill.")
    if JQ_DUMP.search(cmd):
        m = JQ_SEG.search(cmd)
        files = [t for t in positional(m.group(2)) if t.lower().endswith(".json")]
        if files:
            return ("rewrite", swap(m, f"{call('shape')} --file {q(files[-1])}"), f"jq . {files[-1]} -> shape --file (then --path)")
        if "|" in m.group(1):
            return ("rewrite", swap(m, f"{call('shape')} --stdin"), "jq . -> shape --stdin (then --path)")
        return ("deny", "`jq .` dumps the whole document into context. Use the shape skill (`nitro shape CMD` / `nitro shape --file F`), "
                        "then `--path a.b[0]` or a narrowing jq filter (`jq -c '.items[] | .id'`).")
    for m in REDIRECT.finditer(cmd):
        path = resolve(cwd, m.group(1))
        if path and os.path.isfile(path):
            return ("deny", f"Overwriting or appending to the existing file {m.group(1)} by redirection is blocked. "
                            "Use the hashpatch skill (`apply`) so the edit is anchored and reviewable.")

    if RUNNER.search(cmd) and "rr.py" not in cmd and "fails.py" not in cmd:
        if ("\n" in cmd or "<<" in cmd) or ('"' in cmd and "'" in cmd):
            return ("deny", "Tests, linters and type checks go through the fails skill (`nitro fails \"<command>\"`) and builds through rerun "
                            "(`nitro rr \"<command>\"`); this command mixes quotes or has a heredoc, so wrap it yourself.")
        wrap = "fails" if TESTY.search(cmd) else "rr"
        qc = f"'{cmd.strip()}'" if '"' in cmd else f'"{cmd.strip()}"'
        return ("rewrite", f"{call(wrap)} {qc}", f"{'tests/lint' if wrap == 'fails' else 'build'} wrapped in {wrap}")
    return ("allow",)


def read_only(cmd):
    if "<<" in cmd or "\n" in cmd.strip():
        return False
    segs = [s for s in re.split(r"[;&|]+", cmd) if s.strip()]
    return all(SAFE_SEG.match(s) for s in segs)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    ti = payload.get("tool_input", {}) or {}
    cmd = ti.get("command") or ""
    cwd = payload.get("cwd") or os.getcwd()
    if not cmd or SKIP.search(cmd):
        return 0
    if INLINE.search(cmd) and WRITES.search(cmd):
        return deny("An inline script that writes files is blocked. Use the hashpatch skill (`apply`) for edits; "
                    "plain Write is fine for a brand-new file.")
    # a heredoc body is data (a patch, a script, prose): expand and rewrite only the command head
    # (the parts before and after each body are processed; a body runs from the <<WORD line to the WORD line)
    parts, rest = [], cmd
    while True:
        hd = HEREDOC.search(rest)
        if not hd:
            parts.append([rest, False])
            break
        word = re.search(r"<<-?\s*['\"]?(\w+)", hd.group(0)).group(1)
        after = rest[hd.end():]
        end = re.search(r"^" + re.escape(word) + r"[ \t]*$", after, re.M)
        b_end = end.end() if end else len(after)
        parts.append([rest[:hd.end()], False])
        parts.append([after[:b_end], True])
        rest = after[b_end:]
    notes, changed = [], False
    for part in parts:
        if part[1] or not part[0].strip():
            continue
        seg = NITRO.sub(lambda m: m.group(1) + call(m.group(2)), part[0])
        m = CD.match(seg)
        if m:
            target = resolve(cwd, m.group(1))
            if target and same_dir(target, cwd):
                seg = seg[m.end():]
                notes.append("cwd is already that directory, cd dropped")
        for _ in range(4):
            res = check(seg, cwd)
            if res[0] == "deny":
                return deny(res[1])
            if res[0] == "allow":
                break
            seg, note = res[1], res[2]
            notes.append(note)
        else:
            return deny("nitro: this command needs more than four rewrites; split it up.")
        changed = changed or seg != part[0]
        part[0] = seg
    if not changed:
        return 0
    new = "".join(p[0] for p in parts)
    if notes:
        new = "echo '[nitro: " + "; ".join(notes).replace("'", '"') + "]'; " + new
    ti = dict(ti)
    ti["command"] = new
    out = {"hookEventName": "PreToolUse", "updatedInput": ti}
    if not any(p[1] for p in parts) and read_only(new):
        out["permissionDecision"] = "allow"
        out["permissionDecisionReason"] = "nitro: read-only skill invocation"
    sys.stdout.write(json.dumps({"hookSpecificOutput": out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
