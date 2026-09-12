#!/usr/bin/env python3
"""PostToolUse hook (matcher Bash|PowerShell): record how many lines and chars
each command produced, keyed by command shape, so budget-guard.py can predict
and deny the next oversized run.

  {"matcher": "Bash|PowerShell", "hooks": [{"type": "command",
    "command": "python /path/to/nitro-skills/hooks/budget-record.py"}]}
"""
import json, os, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
BP = os.path.join(os.path.dirname(HERE), "budget", "scripts", "budget.py")


def main():
    data = json.load(sys.stdin)
    cmd = data.get("tool_input", {}).get("command", "")
    if not cmd:
        return 0
    resp = data.get("tool_response", "")
    if isinstance(resp, dict):
        text = str(resp.get("stdout", "")) + str(resp.get("stderr", ""))
        if not text.strip():
            text = json.dumps(resp)
    elif isinstance(resp, list):
        text = "".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in resp)
    else:
        text = str(resp)
    spec = importlib.util.spec_from_file_location("budget", BP)
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    b.record(cmd, text.count("\n") + 1, len(text), data.get("cwd") or os.getcwd())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
