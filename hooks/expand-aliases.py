#!/usr/bin/env python3
"""PreToolUse hook (matcher Bash|PowerShell): rewrite §N alias tokens in the
command back to the strings recorded by the alias skill for this workspace.

  {"matcher": "Bash|PowerShell", "hooks": [{"type": "command",
    "command": "python /path/to/nitro-skills/hooks/expand-aliases.py"}]}
"""
import json, os, re, sys, hashlib

def main():
    data = json.load(sys.stdin)
    cmd = data.get("tool_input", {}).get("command", "")
    if "§" not in cmd:
        return 0
    cwd = data.get("cwd") or os.getcwd()
    tab = os.path.join(os.path.expanduser("~"), ".cache", "nitro", "alias",
                       hashlib.md5(os.path.normcase(os.path.abspath(cwd)).lower().encode()).hexdigest()[:8], "table.json")
    try:
        t = json.load(open(tab, encoding="utf-8"))
    except Exception:
        return 0
    t2s = {v: k for k, v in t["s2t"].items()}
    new = re.sub(r"§(\d+)", lambda m: t2s.get(int(m.group(1)), m.group(0)), cmd)
    if new != cmd:
        ti = dict(data["tool_input"]); ti["command"] = new
        sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                         "permissionDecision": "allow", "updatedInput": ti}}))
    return 0

if __name__ == "__main__":
    sys.exit(main())
