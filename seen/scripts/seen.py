#!/usr/bin/env python3
"""seen: run a command and collapse any block of lines the model has already
been shown in this workspace. Executed, never read.

  seen.py CMD...             run CMD, print output with already-seen blocks folded
  seen.py --stdin            filter stdin the same way
  seen.py --show ID A-B      reprint lines A-B of an earlier output ID
  seen.py --reset            forget everything for this workspace

A block is folded when >= MIN consecutive lines, in the same order, appeared in
an earlier output. Folded blocks print as  [seen #ID L12-40, 29 lines].
"""
import sys, os, re, subprocess, hashlib, json

MIN = 4
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.join(os.path.expanduser("~"), ".cache", "nitro", "seen",
                    hashlib.md5(os.path.normcase(os.path.abspath(os.getcwd())).lower().encode()).hexdigest()[:8])
os.makedirs(ROOT, mode=0o700, exist_ok=True)
IDX = os.path.join(ROOT, "index.json")
NOISE = [(re.compile(r"\x1b\[[0-9;]*[A-Za-z]"), ""), (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*"), "<ts>"),
         (re.compile(r"\b\d+(\.\d+)?\s?(ms|s|sec|secs)\b"), "<dur>")]

def norm(line):
    for rx, rep in NOISE:
        line = rx.sub(rep, line)
    return line.rstrip()

def h(lines):
    return hashlib.blake2b("\n".join(lines).encode(), digest_size=6).hexdigest()

def load():
    try:
        return json.load(open(IDX, encoding="utf-8"))
    except Exception:
        return {"next": 1, "win": {}}

def save(idx):
    json.dump(idx, open(IDX, "w", encoding="utf-8"))

def run(argv):
    if len(argv) == 1:
        p = subprocess.run(argv[0], shell=True, capture_output=True)
    else:
        p = subprocess.run(argv, capture_output=True)
    return (p.stdout + p.stderr).decode("utf-8", "replace"), p.returncode

def fold(text, idx):
    lines = text.replace("\r", "").split("\n")
    nl = [norm(l) for l in lines]
    win = idx["win"]
    my_id = idx["next"]
    out, i, n, folded = [], 0, len(lines), 0
    while i < n:
        key = h(nl[i:i + MIN]) if i + MIN <= n and any(nl[i:i + MIN]) else None
        hit = win.get(key) if key else None
        if hit:
            src_id, src_line = hit
            # extend while the next windows continue the same source run
            j = i + MIN
            while j + 1 <= n:
                k2 = h(nl[j - MIN + 1:j + 1])
                nxt = win.get(k2)
                if nxt and nxt[0] == src_id and nxt[1] == src_line + (j - MIN + 1 - i):
                    j += 1
                else:
                    break
            length = j - i
            out.append(f"[seen #{src_id} L{src_line + 1}-{src_line + length}, {length} lines]")
            folded += length
            i = j
        else:
            out.append(lines[i]); i += 1
    # register this output's windows (without overwriting earlier origins)
    for i in range(0, n - MIN + 1):
        if any(nl[i:i + MIN]):
            win.setdefault(h(nl[i:i + MIN]), [my_id, i])
    idx["next"] = my_id + 1
    with open(os.path.join(ROOT, f"{my_id}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return "\n".join(out), my_id, folded, n

def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 0
    if a[0] == "--reset":
        for f in os.listdir(ROOT): os.remove(os.path.join(ROOT, f))
        print("seen: reset"); return 0
    if a[0] == "--show":
        sid, rng = a[1], a[2]
        lo, hi = (int(x) for x in rng.split("-"))
        ls = open(os.path.join(ROOT, f"{sid}.txt"), encoding="utf-8").read().split("\n")
        print("\n".join(ls[lo - 1:hi])); return 0
    idx = load()
    if a[0] == "--stdin":
        text, code = sys.stdin.read(), 0
    else:
        text, code = run(a)
    body, my_id, folded, n = fold(text, idx)
    save(idx)
    print(body)
    tag = f"[seen: output #{my_id}, {n} lines, {folded} folded, exit {code}]"
    print(tag)
    return code

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
