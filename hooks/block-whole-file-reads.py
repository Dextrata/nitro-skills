#!/usr/bin/env python3
"""
Optional PreToolUse hook: nudges the agent to use nitro-skills instead of a
raw whole-file Read.

Install (project-level, in .claude/settings.json):

  {
    "hooks": {
      "PreToolUse": [
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

Behavior: if Read targets an existing text file above SIZE_THRESHOLD_LINES
and no offset/limit was given (i.e. a whole-file read), the hook exits 2,
which blocks the tool call and shows the agent a message telling it to use
hashpatch outline/view or probe instead. Small files, explicit ranged reads,
and non-existent files (new file creation flows) are left alone.

This is intentionally aggressive. Only install it if you want the rule in
CLAUDE.md enforced mechanically instead of left to the model's judgment.
"""
import json
import sys

SIZE_THRESHOLD_LINES = 60


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path")
    if not file_path:
        return 0

    # A ranged read is already token-frugal; let it through.
    if tool_input.get("offset") or tool_input.get("limit"):
        return 0

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            line_count = sum(1 for _ in f)
    except OSError:
        return 0  # file doesn't exist yet, or unreadable - not our concern

    if line_count <= SIZE_THRESHOLD_LINES:
        return 0

    sys.stderr.write(
        f"Blocked: whole-file Read of {file_path} ({line_count} lines). "
        "Use the hashpatch skill instead: `outline` for structure, `grep` "
        "for a pattern, `view A-B` for a specific range. If you only need "
        "a module's API (not its implementation), use the probe skill "
        "instead of reading source at all.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
