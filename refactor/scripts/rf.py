#!/usr/bin/env python3
"""refactor: one-line intent -> mechanical edit. Executed, never read.

  rf.py rename OLD NEW [PATH...]           identifier rename (word-boundary; Python skips strings/comments)
  rf.py add-import FILE "import x"          insert after the last import (dedupes)
  rf.py wrap FILE A-B try EXC [handler]     wrap lines A-B in try/except EXC (Python) or try/catch (JS)
  rf.py wrap FILE A-B with EXPR             wrap lines A-B in `with EXPR:` (Python)
  rf.py wrap FILE A-B if COND               wrap lines A-B in an if block
  rf.py rm-symbol FILE NAME                 delete a top-level def/class/function (Python/JS)
  rf.py move-symbol SRC NAME DEST           cut a top-level symbol from SRC and append it to DEST
  rf.py replace PATTERN REPL [PATH...]      regex replace across files (Python re syntax, \\1 groups)
  rf.py --dry ...                           report what would change, write nothing

Prints one line per touched file: path, count, and new line numbers.
"""
import sys, os, re, io, ast, tokenize, shutil, subprocess, importlib.util

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".cache"}
EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".rb", ".php", ".cs"}
DRY = False
HERE = os.path.dirname(os.path.abspath(__file__))
RG = shutil.which("rg")


def _q():
    qp = os.path.join(os.path.dirname(os.path.dirname(HERE)), "q", "scripts", "q.py")
    if not os.path.isfile(qp):
        return None
    try:
        spec = importlib.util.spec_from_file_location("qmod", qp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def tag():
    return " (dry)" if DRY else ""


def files(paths):
    if not paths:
        paths = ["."]
    q = _q()
    for p in paths:
        if os.path.isfile(p):
            yield p.replace("\\", "/")
            continue
        if q is not None:
            for f in q.list_files(p, EXTS, SKIP_DIRS):
                yield (f if p in (".", "./") else os.path.join(p, f)).replace("\\", "/").removeprefix("./")
            continue
        for d, dirs, fs in os.walk(p):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for f in fs:
                if os.path.splitext(f)[1] in EXTS:
                    yield os.path.join(d, f).replace("\\", "/").removeprefix("./")


def candidates(paths, pattern, literal):
    """Files containing pattern via `rg -l`; None when rg is unavailable or rejects the pattern."""
    if not RG or os.environ.get("NITRO_NO_RG") == "1":
        return None
    args = [RG, "-l", "--no-messages", "--color", "never", "-f", "-"] + (["-F"] if literal else ["-U"]) + (list(paths) or ["."])
    try:
        p = subprocess.run(args, input=pattern, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError:
        return None
    if p.returncode not in (0, 1):
        return None
    explicit = {x.replace("\\", "/") for x in paths if os.path.isfile(x)}
    out = []
    for l in p.stdout.splitlines():
        l = l.strip().replace("\\", "/").removeprefix("./")
        if l and (l in explicit or (os.path.splitext(l)[1] in EXTS and not set(l.split("/")[:-1]) & SKIP_DIRS)):
            out.append(l)
    return sorted(out)


def targets(paths, pattern, literal):
    c = candidates(paths, pattern, literal)
    return files(paths) if c is None else c


def read(p):
    return open(p, encoding="utf-8", errors="surrogateescape", newline="").read()


def write(p, s):
    if DRY:
        return
    with open(p, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)


def rename_py(src, old, new):
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, SyntaxError):
        return None, 0
    lines = src.splitlines(True)
    offsets = [0]
    for l in lines:
        offsets.append(offsets[-1] + len(l))
    res, pos, n = [], 0, 0
    for t in toks:
        if t.type == tokenize.NAME and t.string == old:
            a = offsets[t.start[0] - 1] + t.start[1]
            b = offsets[t.end[0] - 1] + t.end[1]
            res.append(src[pos:a])
            res.append(new)
            pos = b
            n += 1
    res.append(src[pos:])
    return "".join(res), n


def cmd_rename(a):
    old, new, paths = a[0], a[1], a[2:]
    rx = re.compile(r"(?<![\w$])" + re.escape(old) + r"(?![\w$])")
    total = 0
    for p in targets(paths, old, True):
        src = read(p)
        if old not in src:
            continue
        if p.endswith(".py"):
            new_src, n = rename_py(src, old, new)
            if new_src is None:
                new_src, n = rx.subn(new, src)
        else:
            new_src, n = rx.subn(new, src)
        if n:
            write(p, new_src)
            total += n
            print(f"{p}: {n} renamed")
    print(f"[refactor: rename {old}->{new}, {total} occurrences{tag()}]")


def cmd_replace(a):
    rx = re.compile(a[0], re.M)
    repl = a[1]
    total = 0
    for p in targets(a[2:], a[0], False):
        src = read(p)
        new_src, n = rx.subn(repl, src)
        if n:
            write(p, new_src)
            total += n
            print(f"{p}: {n} replaced")
    print(f"[refactor: replace, {total} occurrences{tag()}]")


def cmd_add_import(a):
    p, stmt = a[0], a[1].strip()
    src = read(p)
    lines = src.splitlines(True)
    if any(l.strip() == stmt for l in lines):
        print(f"{p}: already has `{stmt}`")
        return
    last = -1
    if p.endswith(".py"):
        try:
            for node in ast.parse(src).body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    last = (node.end_lineno or node.lineno) - 1
                elif last >= 0:
                    break
        except SyntaxError:
            pass
        if last < 0:  # after shebang/comments and a module docstring
            i = 0
            while i < len(lines) and (lines[i].startswith("#") or not lines[i].strip()):
                i += 1
            if i < len(lines) and lines[i].lstrip().startswith(('"""', "'''")):
                q = lines[i].lstrip()[:3]
                j = i if lines[i].strip().count(q) >= 2 and len(lines[i].strip()) > 3 else i + 1
                while j < len(lines) and q not in lines[j]:
                    j += 1
                last = j
            else:
                last = i - 1
    else:
        for i, l in enumerate(lines):
            if re.match(r"\s*(import\b|const .*= require\()", l):
                last = i
            elif last >= 0 and l.strip() and not l.strip().startswith(("//", "/*", "*")):
                break
        if last < 0:
            last = 0 if lines and lines[0].startswith("#!") else -1
    nl = "\r\n" if "\r\n" in src else "\n"
    lines.insert(last + 1, stmt + nl)
    write(p, "".join(lines))
    print(f"{p}: inserted at line {last + 2}{tag()}")


def cmd_wrap(a):
    p, rng, kind = a[0], a[1], a[2]
    rest = a[3:]
    lo, hi = (int(x) for x in rng.split("-"))
    src = read(p)
    lines = src.splitlines(True)
    nl = "\r\n" if "\r\n" in src else "\n"
    block = lines[lo - 1:hi]
    ind = min((len(l) - len(l.lstrip()) for l in block if l.strip()), default=0)
    base = block[0][:ind] if block else ""
    py = p.endswith(".py")
    step = "    " if py else "  "
    body = [base + step + l[ind:] if l.strip() else l for l in block]
    if kind == "try":
        exc = rest[0] if rest else ("Exception" if py else "e")
        handler = rest[1] if len(rest) > 1 else ("raise" if py else "throw e")
        if py:
            new = [base + "try:" + nl] + body + [base + f"except {exc} as e:" + nl, base + step + handler + nl]
        else:
            new = ([base + "try {" + nl] + body +
                   [base + f"}} catch ({exc}) {{" + nl, base + step + handler + nl, base + "}" + nl])
    elif kind in ("with", "if", "for", "while"):
        head = " ".join(rest)
        if py:
            new = [base + f"{kind} {head}:" + nl] + body
        else:
            new = [base + f"{kind} ({head}) {{" + nl] + body + [base + "}" + nl]
    else:
        print("unknown wrap kind")
        return
    lines[lo - 1:hi] = new
    write(p, "".join(lines))
    print(f"{p}: wrapped {lo}-{hi} -> now {lo}-{lo + len(new) - 1}{tag()}")


def symbol_span(p, src, name):
    if p.endswith(".py"):
        for node in ast.parse(src).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                start = min([d.lineno for d in node.decorator_list] + [node.lineno])
                return start, node.end_lineno
        return None
    lines = src.splitlines()
    n = re.escape(name)
    rx = re.compile(r"^(export\s+)?(default\s+)?(async\s+)?(function\*?\s+" + n +
                    r"\b|class\s+" + n + r"\b|(const|let|var)\s+" + n + r"\s*=)")
    for i, l in enumerate(lines):
        if rx.match(l):
            depth, started = 0, False
            for j in range(i, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                if "{" in lines[j]:
                    started = True
                if started and depth <= 0:
                    return i + 1, j + 1
                if not started and lines[j].rstrip().endswith(";"):
                    return i + 1, j + 1
            return i + 1, len(lines)
    return None


def cmd_rm_symbol(a):
    p, name = a[0], a[1]
    src = read(p)
    span = symbol_span(p, src, name)
    if not span:
        print(f"{p}: {name} not found at top level")
        return None
    lines = src.splitlines(True)
    lo, hi = span
    while hi < len(lines) and not lines[hi].strip():
        hi += 1
    chunk = "".join(lines[lo - 1:hi])
    del lines[lo - 1:hi]
    write(p, "".join(lines))
    print(f"{p}: removed {name} (lines {lo}-{span[1]}){tag()}")
    return chunk


def cmd_move_symbol(a):
    src_p, name, dst = a[0], a[1], a[2]
    chunk = cmd_rm_symbol([src_p, name])
    if chunk is None:
        return
    dsrc = read(dst) if os.path.exists(dst) else ""
    sep = "" if not dsrc or dsrc.endswith("\n\n") else ("\n" if dsrc.endswith("\n") else "\n\n")
    write(dst, dsrc + sep + chunk.rstrip("\r\n") + "\n")
    print(f"{dst}: appended {name}{tag()}")


OPS = {"rename": cmd_rename, "replace": cmd_replace, "add-import": cmd_add_import,
       "wrap": cmd_wrap, "rm-symbol": cmd_rm_symbol, "move-symbol": cmd_move_symbol}


def main(a):
    global DRY
    if a and a[0] == "--dry":
        DRY = True
        a = a[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    op = OPS.get(a[0])
    if not op:
        print(f"unknown op {a[0]}")
        return 2
    op(a[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
