#!/usr/bin/env python3
"""PreToolUse hook (matcher Bash|PowerShell): stop commands predicted to flood context.
Two signals, first match wins:

  1. History: budget-record.py saw this command shape produce > CAP lines before, and it
     is not wrapped in a shaping skill (mine, shape, fails, rerun, sdiff, why, scout) or
     bounded (| head, --max-count, -n N, --stat). Denied; the message names the shaper.
  2. Known floods with no bound. Those with an exact nitro equivalent are REWRITTEN
     (the command starts with `echo '[nitro: ...]'` so the transcript shows it):
       git log (unbounded)            -> git log --oneline -20
       git blame FILE (no -L)         -> why --blame FILE
       cat/type FILE.json|csv|tsv     -> shape --file FILE
       cat/type FILE.log|ndjson|jsonl -> mine --file FILE
       curl/wget/http/gh api/kubectl -o json -> shape "CMD"
       docker logs / journalctl / kubectl logs -> mine "CMD"
     pip list / npm ls / env dumps are denied (shape or rg the output yourself).
  The enforce-nitro-bash hook owns grep, find, code dumps, jq and test runners, so this
  hook never touches those shapes.

Append #nitro-skip to run the exact command anyway.

  {"matcher": "Bash|PowerShell", "hooks": [{"type": "command",
    "command": "python /path/to/nitro-skills/hooks/budget-guard.py"}]}
"""
import json, os, re, sys, shlex, importlib.util

CAP = 120
SKIP = re.compile(r"(?:^|\s)#nitro-skip\s*$", re.M)
HERE = os.path.dirname(os.path.abspath(__file__))
BP = os.path.join(os.path.dirname(HERE), "budget", "scripts", "budget.py")
SHAPED = re.compile(r"(mine|shape|fails|rr|sdiff|hp|q|scout|why|probe|rf|recall|budget|sessions)\.py\b|\bnitro\s+(hp|rr|fails|probe|rf|mine|shape|sdiff|q|scout|why|rc|budget|sessions)\b")
BOUNDED = re.compile(r"\|\s*(head|tail|wc|rg|sd|sort\s+.*\|\s*head)\b|\|\s*jq\s+(?!['\"]?\.['\"]?\s*($|[|;&]))|--max-count|\s-m\s*\d|--oneline|--stat\b|\s-n\s*\d+|--limit|-\-json\s+\S+\s*\|", re.I)
OWNED = re.compile(r"(?:^|[\n;|&(`])\s*(grep|egrep|fgrep|find|tree|ls\s+-R|jq|pytest|npm|pnpm|yarn|bun|cargo|go\s+(test|build|vet)|make|dotnet|mvn|gradle|ruff|mypy|pyright|eslint|tsc|jest|vitest|mocha|nitro)\b", re.I)
DUMPS = re.compile(r"(?:^|[\n;|&(`])\s*(cat|type|Get-Content|sed|head|tail)\b", re.I)
POS = r"(?:^|[\n;|&(`]|\$\()\s*(?:sudo\s+)?"
FLOODS = [
    (re.compile("(" + POS + r")(git\s+log\b(?![^\n;|&]*(-n\s*\d|-\d|--oneline|--max-count|-p\s+\S))[^\n;|&]*)", re.I), "git log without a bound",
     "`git log --oneline -20`, or the why skill for one file's history (`nitro why FILE`, `nitro why FILE:A-B`)", "gitlog"),
    (re.compile("(" + POS + r")(git\s+blame\b(?![^\n;|&]*\s-L\s*\d)[^\n;|&]*)", re.I), "whole-file blame",
     "the why skill: `nitro why --blame FILE:A-B` or `nitro why FILE:A-B`", "blame"),
    (re.compile(POS + r"(pip\s+(freeze|list)|npm\s+(ls|list)|pnpm\s+list|yarn\s+list|cargo\s+tree|du\s|env\b|printenv\b|Get-ChildItem\s+env:)", re.I), "environment/dependency dump",
     "`nitro shape CMD` or `rg PATTERN -` on it", None),
    (re.compile("(" + POS + r")((?:curl|wget|http|Invoke-WebRequest|Invoke-RestMethod|gh\s+api|aws\s+\S+\s+\S+|kubectl\s+get\b.*-o\s*(?:json|yaml))\b[^\n;|&]*)", re.I), "API/JSON payload",
     "`nitro shape CMD` then `--path`, or pipe into a narrowing `jq` filter", "shape"),
    (re.compile("(" + POS + r")((?:cat|type|Get-Content)\s+[^|;&>\n]*\.(?:json|csv|tsv|lock|ndjson|jsonl|log)\b[^|;&>\n]*)", re.I), "structured/log file dump",
     "`nitro shape --file F` or `nitro mine --file F`", "data"),
    (re.compile("(" + POS + r")((?:docker\s+(?:compose\s+)?logs|journalctl|kubectl\s+logs)\b(?![^\n;|&]*(--tail|-n\s*\d))[^\n;|&]*)", re.I), "log stream",
     "`nitro mine CMD --keep error`", "mine"),
]


def skill(name):
    for base in (os.path.dirname(HERE), os.path.join(os.path.expanduser("~"), ".claude", "skills")):
        p = os.path.join(base, name, "scripts", name + ".py")
        if os.path.isfile(p):
            return f'python "{p.replace(chr(92), "/")}"'
    return f'python "{os.path.join(os.path.expanduser("~"), ".claude", "skills", name, "scripts", name + ".py").replace(chr(92), "/")}"'


def deny(reason):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                     "permissionDecisionReason": reason + f" Append {SKIP} if the raw output is genuinely required."}}))
    return 0


def rewrite(ti, cmd, note, safe):
    ti = dict(ti)
    ti["command"] = "echo '[nitro: " + note.replace("'", '"') + "]'; " + cmd
    out = {"hookEventName": "PreToolUse", "updatedInput": ti}
    if safe:
        out["permissionDecision"] = "allow"
        out["permissionDecisionReason"] = "nitro: read-only rewrite"
    sys.stdout.write(json.dumps({"hookSpecificOutput": out}))
    return 0


def fix(kind, m, cmd):
    """Exact nitro equivalent of the matched segment, or None. Returns (new_cmd, note, safe)."""
    seg = m.group(2)
    swap = lambda new: cmd[:m.start()] + m.group(1) + new + cmd[m.end():]
    if kind == "gitlog":
        return swap(seg.rstrip() + " --oneline -20"), "git log bounded to --oneline -20; nitro why FILE for one file's history", True
    if kind == "blame":
        try:
            toks = shlex.split(seg)
        except ValueError:
            return None
        files = [t for t in toks[2:] if not t.startswith("-")]
        if len(files) == 1 and len(toks) <= 4:
            return swap(f"{skill('why')} --blame {shlex.quote(files[0])}"), "git blame -> why --blame (sha/date/author per run of lines)", True
        return None
    if kind == "data":
        try:
            toks = shlex.split(seg)
        except ValueError:
            return None
        files = [t for t in toks[1:] if not t.startswith("-")]
        if len(files) != 1 or len(toks) != 2:
            return None
        f = files[0]
        if f.lower().endswith((".log", ".ndjson", ".jsonl")):
            return swap(f"{skill('mine')} --file {shlex.quote(f)}"), f"cat {f} -> mine --file (templates with counts; --keep error)", True
        return swap(f"{skill('shape')} --file {shlex.quote(f)}"), f"cat {f} -> shape --file (schema + samples; --path to descend)", True
    if kind in ("shape", "mine"):
        if '"' in cmd or "\n" in cmd or "<<" in cmd or cmd.strip() != seg.strip():
            return None
        return f"{skill(kind)} \"{seg.strip()}\"", f"wrapped in {kind}" + (" (schema + samples; --path to descend)" if kind == "shape" else " (templates with counts; --keep error)"), False
    return None


def main():
    data = json.load(sys.stdin)
    ti = data.get("tool_input", {}) or {}
    cmd = ti.get("command", "") or ""
    if not cmd or SKIP.search(cmd) or SHAPED.search(cmd) or BOUNDED.search(cmd):
        return 0
    if OWNED.search(cmd):
        return 0   # the enforce-nitro-bash hook rewrites or denies these shapes
    for rx, what, hint, kind in FLOODS:
        m = rx.search(cmd)
        if not m:
            continue
        fixed = fix(kind, m, cmd) if kind else None
        if fixed:
            return rewrite(ti, *fixed)
        return deny(f"budget: {what} is an unbounded flood. Use {hint}.")
    if DUMPS.search(cmd):
        return 0   # big code dumps are rewritten by enforce-nitro-bash; data files were handled above
    try:
        spec = importlib.util.spec_from_file_location("budget", BP)
        b = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(b)
        n, why = b.predict(cmd, data.get("cwd") or os.getcwd())
    except Exception:
        n = None
    if n is not None and n > CAP:
        return deny(f"budget: this command shape produced {n} lines last time (cap {CAP}). "
                    "Route it through mine/shape/fails/rerun/why, or bound it with | head / -n.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
