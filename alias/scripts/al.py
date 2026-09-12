#!/usr/bin/env python3
"""alias: session symbol table. Long strings that recur in tool output (deep
paths, hashes, UUIDs, long identifiers) are replaced with short tokens like
§3; a legend prints once. Executed, never read.

  al.py CMD...           run CMD, alias its output, print legend of NEW aliases + output
  al.py --stdin          filter stdin
  al.py x TEXT...        expand §N tokens in TEXT and print it
  al.py --legend         print the whole table
  al.py --reset          forget the table for this workspace

Only strings >= MINLEN chars that appear >= MINOCC times (in this output or
across the session) are aliased. Companion hook: hooks/expand-aliases.py
rewrites §N inside Bash/PowerShell commands back to the real string.
"""
import sys, os, re, subprocess, hashlib, json

MINLEN, MINOCC = 18, 2
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.join(os.path.expanduser("~"), ".cache", "nitro", "alias",
                    hashlib.md5(os.path.normcase(os.path.abspath(os.getcwd())).lower().encode()).hexdigest()[:8])
os.makedirs(ROOT, mode=0o700, exist_ok=True)
TAB = os.path.join(ROOT, "table.json")
# candidate strings: path-like runs, hex/uuid ids, dotted/long identifiers
CAND = re.compile(r"(?:[A-Za-z]:)?(?:[\w.@-]+[\/]){2,}[\w.@-]+"      # paths with 2+ separators
                  r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
                  r"|\b[0-9a-f]{16,}\b"
                  r"|\b(?:[A-Za-z_]\w*\.){2,}[A-Za-z_]\w*\b"           # a.b.c.d dotted names
                  r"|\b[A-Za-z_][A-Za-z0-9_]{24,}\b")
TOK = re.compile(r"§(\d+)")

def load():
    try:
        return json.load(open(TAB, encoding="utf-8"))
    except Exception:
        return {"next": 1, "s2t": {}, "seen": {}}

def save(t):
    json.dump(t, open(TAB, "w", encoding="utf-8"))

def run(argv):
    if len(argv) == 1:
        p = subprocess.run(argv[0], shell=True, capture_output=True)
    else:
        p = subprocess.run(argv, capture_output=True)
    return (p.stdout + p.stderr).decode("utf-8", "replace"), p.returncode

def compress(text, t):
    counts = {}
    for m in CAND.finditer(text):
        s = m.group(0)
        if len(s) >= MINLEN:
            counts[s] = counts.get(s, 0) + 1
    new = []
    for s, c in counts.items():
        t["seen"][s] = t["seen"].get(s, 0) + c
        if s not in t["s2t"] and t["seen"][s] >= MINOCC:
            t["s2t"][s] = t["next"]; t["next"] += 1; new.append(s)
    # longest first so nested strings resolve to the longest alias
    for s in sorted(t["s2t"], key=len, reverse=True):
        if s in text:
            text = text.replace(s, f"§{t['s2t'][s]}")
    return text, new

def expand(text, t):
    t2s = {v: k for k, v in t["s2t"].items()}
    return TOK.sub(lambda m: t2s.get(int(m.group(1)), m.group(0)), text)

def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 0
    t = load()
    if a[0] == "--reset":
        save({"next": 1, "s2t": {}, "seen": {}}); print("alias: reset"); return 0
    if a[0] == "--legend":
        for s, n in sorted(t["s2t"].items(), key=lambda kv: kv[1]):
            print(f"§{n} = {s}")
        return 0
    if a[0] == "x":
        print(expand(" ".join(a[1:]), t)); return 0
    if a[0] == "--stdin":
        text, code = sys.stdin.read(), 0
    else:
        text, code = run([expand(x, t) for x in a])
    body, new = compress(text, t)
    save(t)
    for s in new:
        print(f"§{t['s2t'][s]} = {s}")
    if new:
        print("--")
    sys.stdout.write(body if body.endswith("\n") else body + "\n")
    print(f"[alias: exit {code}, {len(new)} new, {len(t['s2t'])} total]")
    return code

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
