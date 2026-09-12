#!/usr/bin/env python3
"""PreToolUse hook (matcher Bash|PowerShell): deny commands predicted to flood
context. Two signals, first match wins:

  1. History: budget-record.py saw this command shape produce > CAP lines
     before, and it is not wrapped in a shaping skill (seen, alias, mine,
     shape, trace, rerun, sdiff) or bounded (| head, --max-count, -n N, --stat).
  2. Known floods with no bound: git log without -n/--oneline, find/ls -R,
     tree, pip freeze/list, npm ls, du, env/printenv, curl without shaping,
     cat of a .json/.csv/.log file, jq . on a file, docker logs, journalctl,
     kubectl get -o json.

Append #nitro-skip to run the exact command anyway.

  {"matcher": "Bash|PowerShell", "hooks": [{"type": "command",
    "command": "python /path/to/nitro-skills/hooks/budget-guard.py"}]}
"""
import json, os, re, sys, importlib.util

CAP = 120
SKIP = "#nitro-skip"
HERE = os.path.dirname(os.path.abspath(__file__))
BP = os.path.join(os.path.dirname(HERE), "budget", "scripts", "budget.py")
SHAPED = re.compile(r"(seen|al|mine|shape|trace|rr|sdiff|hp|q|blast)\.py\b")
BOUNDED = re.compile(r"\|\s*(head|tail|wc|rg|sd|sort\s+.*\|\s*head)\b|\|\s*jq\s+(?!['\"]?\.['\"]?\s*($|[|;&]))|--max-count|\s-m\s*\d|--oneline|--stat\b|\s-n\s*\d+|--limit|-\-json\s+\S+\s*\|", re.I)
POS = r"(?:^|[\n;|&(`]|\$\()\s*(?:sudo\s+)?"
FLOODS = [
    (re.compile(POS + r"git\s+log\b(?!.*(-n\s*\d|-\d|--oneline|--max-count|-p\s+\S))", re.I), "git log without a bound", "`$SEEN git log --oneline -20`"),
    (re.compile(POS + r"(find\s+\S|ls\s+-[a-zA-Z]*R|tree\b|Get-ChildItem\s+.*-Recurse)", re.I), "recursive listing", "`fd PATTERN` (gitignore-aware; `-e EXT`, `-t f`) or `q` for symbols"),
    (re.compile(POS + r"(pip\s+(freeze|list)|npm\s+(ls|list)|pnpm\s+list|yarn\s+list|cargo\s+tree|du\s|env\b|printenv\b|Get-ChildItem\s+env:)", re.I), "environment/dependency dump", "`$SHAPE CMD` or `rg PATTERN -` on it"),
    (re.compile(POS + r"(curl|wget|http|Invoke-WebRequest|Invoke-RestMethod|gh\s+api|aws\s+\S+\s+\S+|kubectl\s+get\b.*-o\s*(json|yaml))", re.I), "API/JSON payload", "`$SHAPE CMD` then `--path`, or pipe into a narrowing `jq` filter"),
    (re.compile(POS + r"(cat|type|Get-Content|jq\s+(?:-\S+\s+)*['\"]?\.['\"]?)\s+[^|;&>]*\.(json|csv|tsv|log|lock|ndjson)\b", re.I), "structured/log file dump", "`$SHAPE --file F` or `$MINE --file F`"),
    (re.compile(POS + r"(docker\s+(compose\s+)?logs|journalctl|kubectl\s+logs)\b(?!.*(--tail|-n\s*\d))", re.I), "log stream", "`$MINE CMD --keep error`"),
]


def deny(reason):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                     "permissionDecisionReason": reason + f" Append {SKIP} if the raw output is genuinely required."}}))
    return 0


def main():
    data = json.load(sys.stdin)
    cmd = data.get("tool_input", {}).get("command", "") or ""
    if not cmd or SKIP in cmd or SHAPED.search(cmd) or BOUNDED.search(cmd):
        return 0
    try:
        spec = importlib.util.spec_from_file_location("budget", BP)
        b = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(b)
        n, why = b.predict(cmd, data.get("cwd") or os.getcwd())
    except Exception:
        n = None
    if n is not None and n > CAP:
        return deny(f"budget: this command shape produced {n} lines last time (cap {CAP}). "
                    "Route it through seen/mine/shape/trace/rerun, or bound it with | head / -n.")
    for rx, what, fix in FLOODS:
        if rx.search(cmd):
            return deny(f"budget: {what} is an unbounded flood. Use {fix}.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
