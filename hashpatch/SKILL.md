---
name: hashpatch
description: Token-frugal code viewing and editing. Use whenever editing an existing file. Replaces Read+Edit with hash-anchored line ops so you never re-transmit code you already saw.
---

# hashpatch

Edit files by *pointing* at lines, not by quoting them. Every line is shown as `N:HHHH|text`; you edit by citing `N:HHHH`. The hash proves the anchor is current, so stale edits are rejected atomically. Do not Read a file whole and do not use Edit with an old_string. Use these:

`HP="python ~/.claude/skills/hashpatch/scripts/hp.py"`

## Locate (cheap)
- `$HP outline FILE` - only def/class/function/export lines. Start here, not with a full read.
- `$HP grep FILE REGEX [CTX]` - matching lines, optional context lines.
- `$HP view FILE A-B` - a slice. Widen only if you genuinely need more.

## Edit
```
$HP apply FILE <<'EOF'
@@
@42:ab3f-44:c1d0
    replacement lines (verbatim, no prefix)
@@
@57:9e1a+
    inserted after line 57
@@
@12:77e0
@@
EOF
```
- `@N:H` replace one line; `@N:H-M:H` replace range; empty body = delete.
- `@N:H+` insert after; `@N:H^` insert before; `@0+` insert at top / create file.
- Line numbers are from the ORIGINAL file. Put several hunks in one call; the tool handles offsets.
- Body lines are verbatim. A body may not contain a bare `@@` line.
- On success the tool prints fresh `N:HHHH` anchors for each touched region. Trust them and do not re-view.
- `$HP apply FILE --dry` validates anchors without writing.

## Rules
1. Anchor hashes come only from tool output in this conversation. Never guess or fabricate one.
2. If apply says REJECTED, re-`view` the cited lines and retry. Nothing was written.
3. For brand-new files or total rewrites, plain Write is fine. hashpatch is for surgery.
