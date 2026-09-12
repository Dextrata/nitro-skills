#!/usr/bin/env python3
"""mine: log template mining. Turns thousands of log/build lines into a short
table of templates with counts. Executed, never read.

  mine.py CMD...            run CMD and mine its output
  mine.py --stdin           mine stdin
  mine.py --file LOG        mine a file
  mine.py --top N ...       show at most N templates (default 40)
  mine.py --show ID ...     print the raw lines that matched template ID (from the last run)
  mine.py --keep REGEX ...  always print lines matching REGEX verbatim (e.g. "error|fail")

Algorithm: Drain-style. Tokens that look like numbers, hex, paths, timestamps
or quoted strings are masked to <*>; lines are grouped by token count and
first token, then merged when >= 50% of tokens agree. Each template shows
count, first and last line number, and up to 2 example values per wildcard.
"""
import sys, os, re, subprocess, hashlib, json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.join(os.path.expanduser("~"), ".cache", "nitro", "mine")
os.makedirs(ROOT, mode=0o700, exist_ok=True)
LAST = os.path.join(ROOT, hashlib.md5(os.path.normcase(os.path.abspath(os.getcwd())).lower().encode()).hexdigest()[:8] + ".json")
SIM = 0.5
MASK = [
    (re.compile(r"\x1b\[[0-9;]*[A-Za-z]"), ""),
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*(Z|[+-]\d{2}:?\d{2})?"), "<ts>"),
    (re.compile(r"\b\d{1,2}:\d{2}:\d{2}[.\d]*\b"), "<ts>"),
    (re.compile(r"\"[^\"]*\"|'[^']*'"), "<str>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\b[0-9a-f]{7,}\b"), "<hex>"),
    (re.compile(r"(?:[A-Za-z]:)?(?:[\w.-]+[\\/]){1,}[\w.-]+(?::\d+)?"), "<path>"),
    (re.compile(r"\b\d+(\.\d+)?\b"), "<n>"),
]


def mask(line):
    for rx, rep in MASK:
        line = rx.sub(rep, line)
    return line


class Cluster:
    __slots__ = ("toks", "count", "first", "last", "examples", "ids")

    def __init__(self, toks, i, raw):
        self.toks, self.count, self.first, self.last = list(toks), 1, i, i
        self.examples, self.ids = {}, [i]


def similarity(a, b):
    same = sum(1 for x, y in zip(a, b) if x == y or x == "<*>" or y == "<*>")
    return same / max(len(a), 1)


def mine(lines):
    buckets = {}
    clusters = []
    for i, raw in enumerate(lines, 1):
        m = mask(raw.rstrip())
        toks = m.split()
        if not toks:
            continue
        key = (len(toks), toks[0] if not toks[0].startswith("<") else "*")
        best, bs = None, 0
        for c in buckets.get(key, []):
            s = similarity(c.toks, toks)
            if s > bs:
                best, bs = c, s
        if best and bs >= SIM:
            best.count += 1
            best.last = i
            best.ids.append(i)
            for k, (x, y) in enumerate(zip(best.toks, toks)):
                if x != y:
                    ex = best.examples.setdefault(k, [])
                    if x != "<*>" and x not in ex:
                        ex.append(x)
                    if y not in ex and len(ex) < 2:
                        ex.append(y)
                    best.toks[k] = "<*>"
        else:
            c = Cluster(toks, i, raw)
            buckets.setdefault(key, []).append(c)
            clusters.append(c)
    return clusters


def render(clusters, lines, top, keep):
    clusters.sort(key=lambda c: (-c.count, c.first))
    out = []
    saved = {}
    for cid, c in enumerate(clusters[:top], 1):
        saved[cid] = c.ids
        t = " ".join(c.toks)
        ex = "  ".join(f"{k}:{'|'.join(v[:2])}" for k, v in sorted(c.examples.items()) if v)
        rng = f"L{c.first}" if c.first == c.last else f"L{c.first}-{c.last}"
        out.append(f"{cid:>3} x{c.count:<5} {rng:<12} {t[:160]}" + (f"   [{ex[:120]}]" if ex else ""))
    rest = clusters[top:]
    if rest:
        out.append(f"    ... {len(rest)} more templates covering {sum(c.count for c in rest)} lines")
    if keep:
        rx = re.compile(keep, re.I)
        hits = [(i, l) for i, l in enumerate(lines, 1) if rx.search(l)]
        if hits:
            out.append(f"-- kept ({len(hits)} lines match /{keep}/):")
            out += [f"L{i}: {l.rstrip()[:200]}" for i, l in hits[:60]]
            if len(hits) > 60:
                out.append(f"   ... {len(hits) - 60} more")
    json.dump({"ids": saved, "lines": lines}, open(LAST, "w", encoding="utf-8"))
    return "\n".join(out)


def run(argv):
    if len(argv) == 1:
        p = subprocess.run(argv[0], shell=True, capture_output=True)
    else:
        p = subprocess.run(argv, capture_output=True)
    return (p.stdout + p.stderr).decode("utf-8", "replace"), p.returncode


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    top, keep, show = 40, None, None
    while a and a[0] in ("--top", "--keep", "--show"):
        if a[0] == "--top":
            top = int(a[1])
        elif a[0] == "--keep":
            keep = a[1]
        else:
            show = int(a[1])
        a = a[2:]
    if show is not None:
        d = json.load(open(LAST, encoding="utf-8"))
        for i in d["ids"].get(str(show), []):
            print(f"L{i}: {d['lines'][i - 1].rstrip()}")
        return 0
    code = 0
    if a and a[0] == "--stdin":
        text = sys.stdin.read()
    elif a and a[0] == "--file":
        text = open(a[1], encoding="utf-8", errors="replace").read()
    else:
        text, code = run(a)
    lines = text.replace("\r", "").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    clusters = mine(lines)
    print(render(clusters, lines, top, keep))
    print(f"[mine: {len(lines)} lines -> {len(clusters)} templates, exit {code}]")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
