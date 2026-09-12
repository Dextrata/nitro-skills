#!/usr/bin/env python3
"""trace: compress stack traces. Executed, never read.

  trace.py CMD...          run CMD; print its output with every stack trace compressed
  trace.py --stdin         filter stdin
  trace.py --file F        compress a saved log
  trace.py --show N        print trace #N of this workspace in full

Handles Python, Node/JS, Java/Kotlin, Go, Rust, .NET, Ruby traces. Vendored
frames (site-packages, node_modules, stdlib, <internal>) collapse to a count;
repeated frame runs (recursion) collapse to  frame (xN); identical traces seen
earlier in this workspace print as  [trace #N: same as before]  plus the message.
Non-trace lines pass through untouched.
"""
import sys, os, re, subprocess, hashlib, json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.join(os.path.expanduser("~"), ".cache", "nitro", "trace",
                    hashlib.md5(os.path.normcase(os.path.abspath(os.getcwd())).lower().encode()).hexdigest()[:8])
os.makedirs(ROOT, mode=0o700, exist_ok=True)
IDX = os.path.join(ROOT, "index.json")

VENDOR = re.compile(r"site-packages|dist-packages|node_modules|[\\/]\.venv[\\/]|[\\/]venv[\\/]|[\\/]lib[\\/]python\d|node:internal|<anonymous>|internal/|"
                    r"[\\/]vendor[\\/]|[\\/]\.cargo[\\/]|rustc[\\/]|[\\/]go[\\/]src[\\/]|java\.base|java\.lang|org\.junit|sun\.reflect|"
                    r"System\.|Microsoft\.|<frozen |importlib[\\/]", re.I)
# frame line shapes
FRAME = re.compile(r"^\s*(at\s+\S|File \"|#\d+\s|\S+\.(?:py|js|ts|tsx|jsx|go|rs|java|kt|rb|cs):\d+|"
                   r"\s+\S+\([^)]*\)\s*$|\s+\d+:\s+\S|from\s+\S+:\d+:in|goroutine \d+)")
PY_FILE = re.compile(r'^\s*File "([^"]+)", line (\d+), in (\S+)')
START = re.compile(r"^(Traceback \(most recent call last\)|\S*(Error|Exception|Panic|panic:)\b.*|thread '.*' panicked|goroutine \d+ \[|Unhandled|Caused by:|"
                   r"\s*at\s+\S+\s*\(|\s*File \".*\", line \d+)", re.I)


def load():
    try:
        return json.load(open(IDX, encoding="utf-8"))
    except Exception:
        return {"next": 1, "hashes": {}}


def save(i):
    json.dump(i, open(IDX, "w", encoding="utf-8"))


def run(argv):
    if len(argv) == 1:
        p = subprocess.run(argv[0], shell=True, capture_output=True)
    else:
        p = subprocess.run(argv, capture_output=True)
    return (p.stdout + p.stderr).decode("utf-8", "replace"), p.returncode


def is_frame(l):
    return bool(FRAME.match(l)) or bool(re.match(r"^\s{2,}\S", l)) and ("(" in l or ":" in l)


def compress(block, idx):
    """block: list of lines belonging to one trace."""
    frames, other = [], []
    for l in block:
        (frames if is_frame(l) and not START.match(l) or PY_FILE.match(l) or l.lstrip().startswith("at ") else other).append(l)
    # pair python 'File' lines with their following source line
    kept, vend, i = [], 0, 0
    merged = []
    while i < len(frames):
        l = frames[i]
        m = PY_FILE.match(l)
        if m:
            src = frames[i + 1].strip() if i + 1 < len(frames) and not PY_FILE.match(frames[i + 1]) and not frames[i + 1].lstrip().startswith("at ") else ""
            merged.append(f"{shortpath(m.group(1))}:{m.group(2)} {m.group(3)}()  {src}"[:160])
            i += 2 if src else 1
        else:
            merged.append(l.strip()[:160])
            i += 1
    for f in merged:
        if VENDOR.search(f):
            vend += 1
            if kept and kept[-1][0] == "vendor":
                kept[-1][1] += 1
            else:
                kept.append(["vendor", 1])
        else:
            if kept and kept[-1][0] == f:
                kept[-1][1] += 1
            else:
                kept.append([f, 1])
    msg = [l.strip() for l in other if l.strip() and not l.strip().startswith("Traceback")]
    core = "\n".join(k[0] for k in kept if k[0] != "vendor") + "\n" + "\n".join(msg[-2:])
    h = hashlib.blake2b(core.encode(), digest_size=6).hexdigest()
    out = []
    if h in idx["hashes"]:
        n = idx["hashes"][h]
        out.append(f"[trace #{n}: same as before] " + (msg[-1][:200] if msg else ""))
        return out, True
    n = idx["next"]
    idx["hashes"][h] = n
    idx["next"] = n + 1
    with open(os.path.join(ROOT, f"{n}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(block))
    out.append(f"[trace #{n}]")
    for k, c in kept:
        if k == "vendor":
            out.append(f"    … {c} library frame{'s' if c > 1 else ''}")
        else:
            out.append("    " + k + (f"  (x{c})" if c > 1 else ""))
    for m in msg[-3:]:
        out.append("  " + m[:300])
    return out, False


def shortpath(p):
    p = p.replace("\\", "/")
    parts = p.split("/")
    return "/".join(parts[-3:]) if len(parts) > 3 else p


def process(text, idx):
    lines = text.replace("\r", "").split("\n")
    out, i, n, traces, dup = [], 0, len(lines), 0, 0
    while i < n:
        l = lines[i]
        if START.match(l) or l.startswith("Traceback"):
            j = i + 1
            while j < n and (is_frame(lines[j]) or START.match(lines[j]) or (lines[j].strip() and j > i and lines[j - 1].strip() and re.match(r"^\s*(\^+|~+|\w+Error|\w+Exception|Caused by|The above|During handling)", lines[j]))):
                j += 1
            # a python trace ends with the exception line after the frames
            if j < n and lines[j].strip() and re.match(r"^\S*(Error|Exception|Warning)\b", lines[j]):
                j += 1
            block = lines[i:j]
            if sum(1 for b in block if is_frame(b)) >= 1 and len(block) >= 2:
                o, d = compress(block, idx)
                out += o
                traces += 1
                dup += d
                i = j
                continue
        out.append(l)
        i += 1
    return "\n".join(out), traces, dup


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if a[0] == "--show":
        print(open(os.path.join(ROOT, f"{a[1]}.txt"), encoding="utf-8").read())
        return 0
    idx = load()
    code = 0
    if a[0] == "--stdin":
        text = sys.stdin.read()
    elif a[0] == "--file":
        text = open(a[1], encoding="utf-8", errors="replace").read()
    else:
        text, code = run(a)
    body, traces, dup = process(text, idx)
    save(idx)
    sys.stdout.write(body if body.endswith("\n") else body + "\n")
    print(f"[trace: {traces} trace(s), {dup} repeated, exit {code}]")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
