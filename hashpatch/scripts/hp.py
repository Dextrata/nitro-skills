#!/usr/bin/env python3
"""hashpatch: hash-anchored viewing and editing. Executed, never read.

  hp.py view    FILE [START-END]      lines as  N:HHHH|text
  hp.py outline FILE                  only def/class/func/export lines, with hashes
  hp.py grep    FILE REGEX [CTX]      matching lines (+CTX context), with hashes
  hp.py apply   FILE < PATCH          apply a hash-anchored patch (atomic)
  hp.py apply   FILE --dry < PATCH    validate anchors only

Patch grammar (hunks separated by a line that is exactly "@@"):
  @@
  @N:HHHH              replace line N with body (empty body = delete line)
  @N:HHHH-M:HHHH       replace lines N..M with body (empty body = delete)
  @N:HHHH+             insert body AFTER line N
  @N:HHHH^             insert body BEFORE line N
  @0+                  insert body at top of file (or into empty file)
  <body lines, verbatim, any content except a bare "@@">
  @@
Line numbers always refer to the ORIGINAL file (pre-patch). All anchors are
verified before anything is written. On success prints new N:HHHH lines for
each touched region so you don't need to re-view.
"""
import sys, re, zlib, os

def h(line):
    return format(zlib.crc32(line.rstrip().encode("utf-8", errors="surrogateescape")) & 0xFFFF, "04x")

def load(path):
    if not os.path.exists(path):
        return [], "\n"
    raw = open(path, "rb").read().decode("utf-8", errors="surrogateescape")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split("\n")
    load.trailing_nl = lines[-1] == ""  # remember whether the file ended with a newline
    if load.trailing_nl:
        lines.pop()
    return [l.rstrip("\r") for l in lines], nl
load.trailing_nl = True

def fmt(lines, i):
    return f"{i+1}:{h(lines[i])}|{lines[i]}"

def view(path, rng=None):
    lines, _ = load(path)
    a, b = 1, len(lines)
    if rng:
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", rng)
        a = int(m.group(1)); b = int(m.group(2) or a)
    for i in range(max(a, 1) - 1, min(b, len(lines))):
        print(fmt(lines, i))

OUTLINE = re.compile(
    r"^\s*(export\s+)?(async\s+)?(def|class|function|fn|func|struct|enum|interface|type|impl|trait|module|pub fn)\b"
    r"|^\s*(export\s+)?(const|let|var)\s+\w+\s*=\s*(async\s*)?(\(|function)"
    r"|^\s*(public|private|protected|static)\s"
    r"|^\s*@\w+|^\s*#\[|^(export\s+)?(const\s+)?[A-Z][A-Z0-9_]{2,}\s*(:[^=]+)?=")
_H = re.compile(r"^#{1,6} \S")
_SEC = re.compile(r"^\[.*\]\s*$")
_KV = re.compile(r"^[A-Za-z_][\w.-]*\s*=")
_MAKE = re.compile(r"^[A-Za-z0-9_.\-/$()%]+\s*:(?!=)")
_SH = re.compile(r"^\s*(function\s+[\w-]+|[\w-]+\s*\(\)\s*\{?\s*$)")
_XML = re.compile(r"^\s{0,4}<[A-Za-z][\w:.-]*(\s|>|/)")
_CSS = re.compile(r"^[^\s{}/][^{;]*\{\s*$|^@(media|import|font-face|keyframes|layer|mixin|function)\b|^\$[\w-]+:|^--[\w-]+:")
_HTML = re.compile(r"^\s*<(h[1-6]|section|article|nav|header|footer|main|form|table|script|style|template|title|body|head)\b|^\s*<[a-z][\w-]*[^>]*\bid=", re.I)
DOC_OUTLINE = {
    "md": _H, "markdown": _H, "mdx": _H,
    "yml": re.compile(r"^ {0,2}[A-Za-z_\"'$][^:#]*:(\s|$)"), "toml": _SEC, "ini": _SEC, "cfg": _SEC, "conf": _SEC,
    "env": _KV, "properties": _KV, "json": re.compile(r'^(\s{0,2}|\t)"[^"]+"\s*:'),
    "makefile": _MAKE, "dockerfile": re.compile(r"^(FROM|WORKDIR|EXPOSE|ENTRYPOINT|CMD|ARG|USER|VOLUME|HEALTHCHECK)\b", re.I),
    "sh": _SH, "bash": _SH, "zsh": _SH, "fish": _SH, "ps1": re.compile(r"^\s*(function|filter|class|enum|param)\b", re.I),
    "sql": re.compile(r"^\s*(create|alter|drop|insert|update|delete|select|with|merge|truncate|grant|begin|declare)\b", re.I),
    "css": _CSS, "scss": _CSS, "less": _CSS, "html": _HTML, "htm": _HTML, "vue": _HTML, "svelte": _HTML, "jinja": _HTML, "njk": _HTML,
    "xml": _XML, "csproj": _XML, "fsproj": _XML, "plist": _XML, "xsd": _XML, "svg": _XML, "xaml": _XML,
    "proto": re.compile(r"^\s*(message|service|rpc|enum|package|import|option)\b"),
    "tf": re.compile(r"^(resource|module|variable|output|provider|data|locals|terraform)\b"),
    "graphql": re.compile(r"^(type|input|enum|interface|union|scalar|schema|query|mutation|subscription|fragment|extend|directive)\b"),
}
for _a, _b in (("yaml", "yml"), ("psm1", "ps1"), ("hcl", "tf"), ("gql", "graphql"), ("mk", "makefile"), ("justfile", "makefile")):
    DOC_OUTLINE[_a] = DOC_OUTLINE[_b]

def _outline_ipynb(lines):
    import json
    try:
        nb = json.loads("\n".join(lines))
    except ValueError:
        return 0
    idxs = [i for i, l in enumerate(lines) if '"cell_type"' in l]
    n = 0
    for k, c in enumerate(nb.get("cells", [])):
        src = c.get("source", "")
        src = "".join(src) if isinstance(src, list) else src
        first = next((s for s in src.split("\n") if s.strip()), "")[:70]
        outs = len(c.get("outputs", [])) if c.get("cell_type") == "code" else 0
        head = fmt(lines, idxs[k]) if k < len(idxs) else "?:????|"
        print(f"{head}  # cell {k + 1} {c.get('cell_type')}: {first}  ({src.count(chr(10)) + 1} lines, {outs} outputs)")
        n += 1
    return n

def outline(path):
    lines, _ = load(path)
    base = os.path.basename(path).lower()
    ext = base.rsplit(".", 1)[-1] if "." in base[1:] else base
    if base.startswith("dockerfile") or base.endswith(".dockerfile"):
        ext = "dockerfile"
    elif base in ("makefile", "gnumakefile", "justfile", ".justfile"):
        ext = "makefile"
    elif base.startswith(".env"):
        ext = "env"
    n = 0
    if ext == "ipynb":
        n = _outline_ipynb(lines)
    elif ext in ("csv", "tsv"):
        if lines:
            print(fmt(lines, 0)[:300])
        print(f"[outline: {path}, {len(lines)} lines ({max(len(lines) - 1, 0)} data rows); the shape skill gives column stats]")
        return
    elif ext == "rst":
        for i in range(len(lines) - 1):
            if lines[i].strip() and re.fullmatch(r"[=\-~^\"'`#*+]{3,}", lines[i + 1].strip()) and len(lines[i + 1].strip()) >= len(lines[i].strip()):
                print(fmt(lines, i)); n += 1
    else:
        rx = DOC_OUTLINE.get(ext, OUTLINE)
        in_section = False
        for i, l in enumerate(lines):
            if ext == "toml" and not in_section:
                in_section = l.startswith("[")
                if not in_section and _KV.match(l):
                    print(fmt(lines, i)); n += 1
                    continue
            if rx.search(l):
                print(fmt(lines, i)[:300]); n += 1
    if n:
        print(f"[outline: {path}, {len(lines)} lines, {n} entries]")
    elif ext == "json":
        print(f"[outline: {path}, {len(lines)} lines, no top-level keys on their own lines; use the shape skill (--file) for its schema]")
    else:
        for i in range(min(3, len(lines))):
            print(fmt(lines, i)[:300])
        print(f"[outline: {path}, {len(lines)} lines, no structure recognized; first 3 shown, use view A-B or grep]")

def grep(path, pat, ctx=0):
    lines, _ = load(path)
    rx = re.compile(pat)
    shown = set()
    for i, l in enumerate(lines):
        if rx.search(l):
            for j in range(max(0, i - ctx), min(len(lines), i + ctx + 1)):
                if j not in shown:
                    shown.add(j); print(fmt(lines, j))
            if ctx: print("--")

HDR = re.compile(r"^@(\d+):([0-9a-f]{4})(?:-(\d+):([0-9a-f]{4}))?([+^])?$")
def parse(text):
    hunks, cur = [], None
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        if line == "@@":
            if cur is not None: cur["closed"] = True; hunks.append(cur); cur = None
            continue
        if cur is None:
            if line.strip() == "": continue
            if line == "@0+":
                cur = {"a": 0, "ha": None, "b": 0, "hb": None, "mode": "+", "body": []}
                continue
            m = HDR.match(line)
            if not m: sys.exit(f"bad hunk header: {line!r}")
            a, ha, b, hb, mode = m.groups()
            cur = {"a": int(a), "ha": ha, "b": int(b) if b else int(a), "hb": hb, "mode": mode or "=", "body": []}
        else:
            cur["body"].append(line)
    if cur is not None:  # unclosed final hunk: drop the blank produced by the trailing newline
        if cur["body"] and cur["body"][-1] == "": cur["body"].pop()
        hunks.append(cur)
    return hunks

ORDER = {"^": 0, "=": 1, "+": 2}

def apply(path, text, dry=False):
    lines, nl = load(path)
    hunks = parse(text)
    if not hunks: sys.exit("empty patch")
    errs = []
    for k in hunks:
        for n, hh in ((k["a"], k["ha"]), (k["b"], k["hb"])):
            if hh is None: continue
            if not (1 <= n <= len(lines)):
                errs.append(f"line {n} out of range (file has {len(lines)})"); continue
            if h(lines[n - 1]) != hh:
                errs.append(f"stale anchor {n}:{hh}; file now has {fmt(lines, n - 1)}")
        if k["a"] > k["b"]: errs.append(f"bad range {k['a']}-{k['b']}")
    spans = sorted((k["a"], k["b"]) for k in hunks if k["mode"] == "=")
    for (a1, b1), (a2, b2) in zip(spans, spans[1:]):
        if a2 <= b1: errs.append(f"overlapping hunks {a1}-{b1} and {a2}-{b2}")
    for k in hunks:
        if k["mode"] == "=": continue
        n = k["a"]
        for a, b in spans:
            if (k["mode"] == "+" and a <= n < b) or (k["mode"] == "^" and a < n <= b):
                errs.append(f"insert at {n} lies inside replaced range {a}-{b}; fold it into that hunk")
    if errs:
        print("REJECTED (nothing written):")
        for e in errs: print("  " + e)
        sys.exit(1)
    if dry:
        print(f"OK: {len(hunks)} hunk(s) valid"); return

    # apply bottom-up so original line numbers stay valid
    for k in sorted(hunks, key=lambda k: (k["a"], ORDER[k["mode"]]), reverse=True):
        a, b, body = k["a"], k["b"], k["body"]
        if k["mode"] == "=":   s, e = a - 1, b
        elif k["mode"] == "+": s = e = a
        else:                  s = e = a - 1
        lines[s:e] = body
    out = nl.join(lines) + (nl if lines and load.trailing_nl else "")
    open(path, "wb").write(out.encode("utf-8", errors="surrogateescape"))

    # report fresh anchors around each touched region (ascending, tracking shift)
    lines, _ = load(path)
    shift, seen = 0, set()
    print(f"APPLIED {len(hunks)} hunk(s) to {path}; new anchors:")
    for k in sorted(hunks, key=lambda k: (k["a"], ORDER[k["mode"]])):
        a, b, n = k["a"], k["b"], len(k["body"])
        s = (a - 1 if k["mode"] in "=^" else a) + shift
        removed = (b - a + 1) if k["mode"] == "=" else 0
        for i in range(max(0, s - 1), min(len(lines), s + n + 1)):
            if i not in seen: seen.add(i); print(fmt(lines, i))
        print("--")
        shift += n - removed

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    if cmd == "view":      view(rest[0], rest[1] if len(rest) > 1 else None)
    elif cmd == "outline": outline(rest[0])
    elif cmd == "grep":    grep(rest[0], rest[1], int(rest[2]) if len(rest) > 2 else 0)
    elif cmd == "apply":   apply(rest[0], sys.stdin.buffer.read().decode("utf-8", errors="surrogateescape"), dry="--dry" in rest)
    else: sys.exit(__doc__)
