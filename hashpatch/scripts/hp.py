#!/usr/bin/env python3
"""hashpatch: hash-anchored viewing and editing. Executed, never read.

  hp.py view    FILE [A-B | SYMBOL] [--anchors]   lines as N|text, closed by a lease line
  hp.py outline FILE                  structure with N:HHHH anchors (code, docs, configs, notebooks)
  hp.py grep    FILE REGEX [CTX]      matching lines (+CTX context), with anchors
  hp.py apply   FILE [--dry] [--echo] < PATCH     atomic; prints a receipt, not the lines

A view ends with  [lease FILE A-B h=HHHHHH]  (a hash of exactly those lines). A patch that
repeats it as  #lease A-B:HHHHHH  may cite bare line numbers inside A-B:
  #lease 40-80:3f9ac2
  @@
  @42-44           replace lines 42..44 with the body (empty body = delete)
  @57+             insert body after 57;   @57^ insert before;   @0+ top of file / new file
  @@
Anchored headers (from grep, outline or view --anchors) need no lease:
  @N:HHHH   @N:HHHH-M:HHHH   @N:HHHH+   @N:HHHH^
Line numbers always refer to the ORIGINAL file. Every lease and anchor is verified before
anything is written; one stale lease or anchor rejects the whole patch. The receipt gives each
hunk's new span and a fresh lease over the touched region, so a second edit needs no re-view.
"""
import sys, re, zlib, os

def h(line):
    return format(zlib.crc32(line.rstrip().encode("utf-8", errors="surrogateescape")) & 0xFFFF, "04x")

def lease_hash(lines, a, b):
    return format(zlib.crc32("\n".join(l.rstrip() for l in lines[a - 1:b]).encode("utf-8", errors="surrogateescape")) & 0xFFFFFF, "06x")

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

def plain(lines, i):
    return f"{i+1}|{lines[i]}"

def find_symbol(path, lines, name):
    """1-based inclusive span of NAME: Python via ast (decorators included, Class.method accepted),
    markdown by header text, other code by an outline line plus its brace or indentation block."""
    ext = os.path.splitext(path)[1].lower()
    short = name.split(".")[-1]
    if ext in (".py", ".pyi"):
        import ast
        try:
            tree = ast.parse("\n".join(lines))
        except SyntaxError:
            tree = None
        if tree is not None:
            best = None
            def walk(node, prefix):
                nonlocal best
                for ch in ast.iter_child_nodes(node):
                    if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        q = prefix + ch.name
                        if (q == name or ch.name == short) and (best is None or q == name):
                            best = (min([d.lineno for d in ch.decorator_list] + [ch.lineno]), ch.end_lineno)
                        walk(ch, q + ".")
            walk(tree, "")
            if best:
                return best
    if ext in (".md", ".markdown", ".mdx"):
        hdr = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
        for i, l in enumerate(lines):
            m = hdr.match(l)
            if m and (m.group(2).lower() == name.lower() or name.lower() in m.group(2).lower()):
                lvl, j = len(m.group(1)), i + 1
                while j < len(lines):
                    m2 = hdr.match(lines[j])
                    if m2 and len(m2.group(1)) <= lvl:
                        break
                    j += 1
                while j - 1 > i and not lines[j - 1].strip():
                    j -= 1
                return (i + 1, j)
        return None
    rx = re.compile(r"(?<![\w$])" + re.escape(short) + r"(?![\w$])")
    for i, l in enumerate(lines):
        if OUTLINE.search(l) and rx.search(l):
            ind = len(l) - len(l.lstrip())
            if "{" in l or (i + 1 < len(lines) and lines[i + 1].strip().startswith("{")):
                depth, opened, j = 0, False, i
                while j < len(lines):
                    depth += lines[j].count("{") - lines[j].count("}")
                    opened = opened or depth > 0
                    if opened and depth <= 0:
                        break
                    j += 1
                j = min(j + 1, len(lines))
            else:
                j = i + 1
                while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > ind):
                    j += 1
            while j - 1 > i and not lines[j - 1].strip():
                j -= 1
            return (i + 1, j)
    return None

def view(path, target=None, anchors=False):
    lines, _ = load(path)
    a, b = 1, len(lines)
    if target:
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", target)
        if m:
            a = int(m.group(1)); b = int(m.group(2) or a)
        else:
            span = find_symbol(path, lines, target)
            if not span:
                print(f"no symbol or section {target!r} in {path}; the outline names what is there:")
                outline(path)
                sys.exit(1)
            a, b = span
    a, b = max(a, 1), min(b, len(lines))
    for i in range(a - 1, b):
        print(fmt(lines, i) if anchors else plain(lines, i))
    if b >= a:
        print(f"[lease {path} {a}-{b} h={lease_hash(lines, a, b)}]")
    else:
        print(f"[lease {path} empty; file has {len(lines)} lines]")

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

LEASE = re.compile(r"^\s*#?\s*\[?lease(?:\s+\S+)?\s+(\d+)-(\d+)[: ]\s*h?=?([0-9a-f]{6})\]?\s*$")
HDR = re.compile(r"^@(\d+)(?::([0-9a-f]{4}))?(?:-(\d+)(?::([0-9a-f]{4}))?)?([+^])?$")
def parse(text):
    leases, hunks, cur = [], [], None
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        if cur is None:
            m = LEASE.match(line)
            if m:
                leases.append((int(m.group(1)), int(m.group(2)), m.group(3)))
                continue
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
            cur = {"a": int(a), "ha": ha, "b": int(b) if b else int(a), "hb": hb if b else ha, "mode": mode or "=", "body": []}
        else:
            cur["body"].append(line)
    if cur is not None:  # unclosed final hunk: drop the blank produced by the trailing newline
        if cur["body"] and cur["body"][-1] == "": cur["body"].pop()
        hunks.append(cur)
    return leases, hunks

ORDER = {"^": 0, "=": 1, "+": 2}

def apply(path, text, dry=False, echo=False):
    lines, nl = load(path)
    leases, hunks = parse(text)
    if not hunks: sys.exit("empty patch")
    errs, valid = [], []
    for a, b, hh in leases:
        if not (1 <= a <= b <= len(lines)):
            errs.append(f"lease {a}-{b} out of range (file has {len(lines)} lines)"); continue
        now = lease_hash(lines, a, b)
        if now != hh:
            errs.append(f"stale lease {a}-{b}:{hh}; those lines changed since the view (now h={now}); view them again")
        else:
            valid.append((a, b))
    for k in hunks:
        if k["a"] == 0 and k["mode"] == "+": continue
        for n, hh in ((k["a"], k["ha"]), (k["b"], k["hb"])):
            if hh is None: continue
            if not (1 <= n <= len(lines)):
                errs.append(f"line {n} out of range (file has {len(lines)})"); continue
            if h(lines[n - 1]) != hh:
                errs.append(f"stale anchor {n}:{hh}; file now has {fmt(lines, n - 1)}")
        if k["ha"] is None or k["hb"] is None:
            where = f"@{k['a']}" + (f"-{k['b']}" if k["b"] != k["a"] else "") + (k["mode"] if k["mode"] != "=" else "")
            if not (1 <= k["a"] <= len(lines) and 1 <= k["b"] <= len(lines)):
                errs.append(f"{where} out of range (file has {len(lines)} lines)")
            elif not any(a <= k["a"] and k["b"] <= b for a, b in valid):
                errs.append(f"{where} has no anchor and no valid lease covers it; repeat the view's lease line at the top of the patch, or use anchors from grep/outline")
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

    # receipt: each hunk's new span, then one lease over everything touched (no line echo unless --echo)
    lines, _ = load(path)
    shift, lo, hi = 0, None, None
    print(f"APPLIED {len(hunks)} hunk(s) to {path}")
    for idx, k in enumerate(sorted(hunks, key=lambda k: (k["a"], ORDER[k["mode"]])), 1):
        a, b, n = k["a"], k["b"], len(k["body"])
        s = (a - 1 if k["mode"] in "=^" else a) + shift
        removed = (b - a + 1) if k["mode"] == "=" else 0
        where = f"@{a}" + (f"-{b}" if k["mode"] == "=" and b != a else "") + (k["mode"] if k["mode"] != "=" else "")
        if n:
            print(f"  h{idx} {where} -> now {s + 1}" + (f"-{s + n}" if n > 1 else ""))
            lo = s + 1 if lo is None else min(lo, s + 1); hi = max(hi or 0, s + n)
        else:
            print(f"  h{idx} {where} -> deleted")
            lo = s + 1 if lo is None else min(lo, s + 1); hi = max(hi or 0, s)
        if echo:
            for i in range(max(0, s - 1), min(len(lines), s + n + 1)): print(fmt(lines, i))
        shift += n - removed
    if lines:
        def moved(b):
            return b + sum(len(k["body"]) - ((k["b"] - k["a"] + 1) if k["mode"] == "=" else 0) for k in hunks if k["a"] <= b)
        la = min([a for a, b in valid] + ([lo] if lo else [len(lines)]))
        lb = max([moved(b) for a, b in valid] + ([hi] if hi else [0]))
        la, lb = max(1, min(la, len(lines))), max(1, min(max(lb, la), len(lines)))
        print(f"[lease {path} {la}-{lb} h={lease_hash(lines, la, lb)}]")
    else:
        print(f"[lease {path} empty]")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = sys.argv[1:]
    if not args: sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    flags = {a for a in rest if a.startswith("--")}
    rest = [a for a in rest if not a.startswith("--")]
    if cmd == "view":      view(rest[0], rest[1] if len(rest) > 1 else None, anchors="--anchors" in flags)
    elif cmd == "outline": outline(rest[0])
    elif cmd == "grep":    grep(rest[0], rest[1], int(rest[2]) if len(rest) > 2 else 0)
    elif cmd == "apply":   apply(rest[0], sys.stdin.buffer.read().decode("utf-8", errors="surrogateescape"), dry="--dry" in flags, echo="--echo" in flags)
    else: sys.exit(__doc__)
