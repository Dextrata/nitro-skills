#!/usr/bin/env python3
"""rerun: run a command, show only what changed since last run. Executed, never read.

  rr.py CMD...            run CMD; print delta vs previous run of the same CMD
  rr.py --full CMD...     run and print squeezed output in full (reset baseline)
  rr.py --raw  CMD...     run and print raw output (no squeeze, still caches)
  rr.py --list            show cached commands
  rr.py --forget CMD...   drop the baseline for CMD

Delta rules: output is normalized (timestamps, durations, hex ids, temp paths,
memory addresses, ANSI) so cosmetic churn never shows. Repeated lines are
squeezed to "line  (xN)". Stack frames inside node_modules / site-packages are
collapsed. First run prints the full squeezed output as the baseline.
"""
import sys, os, re, subprocess, hashlib, json, difflib

CACHE = os.path.join(os.path.expanduser("~"), ".cache", "rerun")
os.makedirs(CACHE, mode=0o700, exist_ok=True)  # cached output may contain anything the command printed

NOISE = [
    (re.compile(r"\x1b\[[0-9;]*[A-Za-z]"), ""),
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?"), "<ts>"),
    (re.compile(r"\b\d{1,2}:\d{2}:\d{2}(\.\d+)?\b"), "<time>"),
    (re.compile(r"\b\d+(\.\d+)?\s?(ms|s|sec|secs|seconds|m|min)\b"), "<dur>"),
    (re.compile(r"\b0x[0-9a-fA-F]{6,}\b"), "<addr>"),
    (re.compile(r"\b[0-9a-f]{12,}\b"), "<hex>"),
    (re.compile(r"\b(pytest-of-\w+[\\/]pytest-|tmp|pip-|npm-)[A-Za-z0-9_]{5,}\b"), r"\1<rand>"),
    (re.compile(r"\bpid[ =:]\d+", re.I), "pid=<n>"),
    (re.compile(r"\bport[ =:]\d+", re.I), "port=<n>"),
]
FRAME = re.compile(r"^\s*(at |File \"|#\d+ )?.*([\\/](node_modules|site-packages|dist-packages|\.venv|vendor)[\\/])")

def normalize(text):
    out, prev, count, collapsed = [], None, 0, 0
    def flush():
        nonlocal prev, count, collapsed
        if collapsed:
            out.append(f"      ... {collapsed} library frame(s) ...")
            collapsed = 0
        if prev is not None:
            out.append(prev if count == 1 else f"{prev}  (x{count})")
        prev, count = None, 0
    for line in text.split(chr(10)):
        line = line.replace(chr(13), "")
        for rx, rep in NOISE:
            line = rx.sub(rep, line)
        line = line.rstrip()
        if FRAME.search(line):
            if prev is not None and not collapsed:
                out.append(prev if count == 1 else f"{prev}  (x{count})"); prev, count = None, 0
            collapsed += 1
            continue
        if line == prev:
            count += 1
        else:
            flush(); prev, count = line, 1
    flush()
    return "\n".join(out)

def key(cmd):
    return hashlib.sha1((os.getcwd() + "\0" + " ".join(cmd)).encode()).hexdigest()[:16]

def run(cmd):
    p = subprocess.run(cmd[0] if len(cmd) == 1 else cmd, shell=(len(cmd) == 1), capture_output=True)
    dec = lambda b: b.decode("utf-8", errors="replace")  # bytes, so CRs reach normalize() intact
    return p.returncode, dec(p.stdout) + dec(p.stderr)

def main():
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    if args[0] == "--list":
        for f in os.listdir(CACHE):
            m = json.load(open(os.path.join(CACHE, f)))
            print(f"{m['cwd']}  $ {m['cmd']}  (exit {m['rc']})")
        return
    if args[0] == "--forget":
        p = os.path.join(CACHE, key(args[1:]) + ".json")
        if os.path.exists(p): os.remove(p); print("forgotten")
        return
    mode = "delta"
    if args[0] in ("--full", "--raw"):
        mode = args[0][2:]; args = args[1:]
    rc, raw = run(args)
    norm = normalize(raw)
    path = os.path.join(CACHE, key(args) + ".json")
    prev = json.load(open(path)) if os.path.exists(path) else None
    json.dump({"cmd": " ".join(args), "cwd": os.getcwd(), "rc": rc, "out": norm}, open(path, "w"))

    if mode == "raw":
        print(raw, end=""); print(f"[exit {rc}]"); sys.exit(rc)
    if mode == "full" or prev is None:
        print(norm); print(f"[exit {rc}] baseline saved ({len(norm.splitlines())} lines)"); sys.exit(rc)
    if prev["out"] == norm and prev["rc"] == rc:
        print(f"[exit {rc}] unchanged since last run ({len(norm.splitlines())} lines suppressed)"); sys.exit(rc)
    diff = list(difflib.unified_diff(prev["out"].splitlines(), norm.splitlines(),
                                     "previous", "current", n=1, lineterm=""))
    # drop file headers; keep hunks compact
    for l in diff[2:]: print(l)
    tag = "" if prev["rc"] == rc else f" (was exit {prev['rc']})"
    print(f"[exit {rc}]{tag}  +{sum(1 for l in diff[2:] if l.startswith('+'))} -{sum(1 for l in diff[2:] if l.startswith('-'))} lines")
    sys.exit(rc)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
