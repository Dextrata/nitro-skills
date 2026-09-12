#!/usr/bin/env python3
"""q: query the codebase like a table instead of chaining rg calls.
Executed, never read.

  q.py "FILTER FILTER ..." [--cols name,file,line,...] [--limit N]
  q.py --reindex                       rebuild the symbol index for this tree
  q.py --stats                         index size and languages

Rows are symbols: functions, methods, classes (Python via ast; JS/TS/Go/Rust/
Java/Ruby via patterns). Columns:
  kind      function|method|class|const          name     symbol name (methods as Class.name)
  file      path                                 line     start line     end   end line
  len       line count                           params   parameter list (Python exact)
  calls     names this symbol calls              deco     decorators
  ret       return annotation                    doc      first doc line
  exported  1/0 (JS export, Python public)       lang
Filters:  col=value  col!=value  col~regex  col!~regex  col>N  col<N  calls=name  (any col)
Sort:     sort=col  sort=-col      Example:
  q.py "kind=function file~^src/ calls=db.query len>40 sort=-len" --cols name,file,line,len
Index is cached by file mtime under ~/.cache/nitro/q; the first run indexes the tree.
"""
import sys, os, re, ast, json, hashlib, time, shutil, subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".cache", "target", ".next", "coverage", ".tox"}
LANG = {".py": "py", ".js": "js", ".jsx": "js", ".ts": "ts", ".tsx": "ts", ".mjs": "js", ".cjs": "js",
        ".go": "go", ".rs": "rs", ".java": "java", ".kt": "kt", ".rb": "rb", ".cs": "cs", ".php": "php"}
ROOT = os.path.join(os.path.expanduser("~"), ".cache", "nitro", "q")
os.makedirs(ROOT, mode=0o700, exist_ok=True)
IDX = os.path.join(ROOT, hashlib.md5(os.path.normcase(os.path.abspath(os.getcwd())).lower().encode()).hexdigest()[:8] + ".json")
CALL = re.compile(r"(?<![\w.$])([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(")
DEF = re.compile(
    r"^(?P<ind>\s*)(?P<exp>export\s+)?(?:default\s+)?(?:pub(?:\([^)]*\))?\s+)?(?:public\s+|private\s+|protected\s+|static\s+|async\s+|final\s+|abstract\s+|override\s+)*"
    r"(?:(?P<kw>def|class|function\*?|fn|func|interface|struct|impl|enum|trait|type|module)\s+(?:\([^)]*\)\s*)?(?P<name>[\w$]+)\s*(?:<[^>]*>)?\s*(?:\((?P<params>[^)]*)\))?"
    r"|(?:const|let|var)\s+(?P<cname>[\w$]+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\((?P<aparams>[^)]*)\)\s*=>|function\b|(?P<one>[\w$]+)\s*=>)"
    r"|(?P<mname>[\w$]+)\s*\((?P<mparams>[^)]*)\)\s*(?::\s*[\w<>\[\]|, ]+)?\s*\{)")
KW = {"if", "for", "while", "switch", "catch", "return", "else", "do", "try", "function", "new", "typeof", "await"}
FD = next((shutil.which(x) for x in ("fd", "fdfind") if shutil.which(x)), None)


def _walk_files(root, exts, skip_dirs):
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x not in skip_dirs and not x.startswith(".")]
        for f in fs:
            if os.path.splitext(f)[1] in exts:
                yield os.path.relpath(os.path.join(d, f), root).replace("\\", "/")


def list_files(root=".", exts=None, skip_dirs=None):
    """Source files under root, relative, forward slashes. fd when present (gitignore-aware), os.walk otherwise."""
    exts = set(LANG) if exts is None else exts
    skip_dirs = SKIP_DIRS if skip_dirs is None else skip_dirs
    if FD and os.environ.get("NITRO_NO_FD") != "1":
        args = [FD, "--type", "f", "--color", "never", "--strip-cwd-prefix"]
        for e in sorted(exts):
            args += ["-e", e.lstrip(".")]
        for d in sorted(skip_dirs):
            args += ["-E", d]
        try:
            p = subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if p.returncode == 0:
                return sorted(l.strip().replace("\\", "/").removeprefix("./") for l in p.stdout.splitlines() if l.strip())
        except OSError:
            pass
    return sorted(_walk_files(root, exts, skip_dirs))


def py_index(path, src):
    rows = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return rows
    lines = src.split("\n")

    def sig(fn):
        try:
            return ast.unparse(fn.args)
        except Exception:
            return ""

    def calls_of(node):
        s = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                try:
                    s.add(ast.unparse(n.func))
                except Exception:
                    pass
        return sorted(s)

    def doc(node):
        d = ast.get_docstring(node)
        return d.strip().split("\n")[0][:80] if d else ""

    def visit(node, prefix, depth):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + n.name
                rows.append({"kind": "method" if prefix else "function", "name": name, "file": path, "line": n.lineno,
                             "end": n.end_lineno, "len": n.end_lineno - n.lineno + 1, "params": sig(n),
                             "calls": calls_of(n), "deco": [ast.unparse(d).split("(")[0] for d in n.decorator_list],
                             "ret": ast.unparse(n.returns) if n.returns else "", "doc": doc(n),
                             "exported": 0 if n.name.startswith("_") else 1, "lang": "py"})
                visit(n, name + ".", depth + 1)
            elif isinstance(n, ast.ClassDef):
                name = prefix + n.name
                rows.append({"kind": "class", "name": name, "file": path, "line": n.lineno, "end": n.end_lineno,
                             "len": n.end_lineno - n.lineno + 1, "params": ", ".join(ast.unparse(b) for b in n.bases),
                             "calls": [], "deco": [ast.unparse(d).split("(")[0] for d in n.decorator_list], "ret": "",
                             "doc": doc(n), "exported": 0 if n.name.startswith("_") else 1, "lang": "py"})
                visit(n, name + ".", depth + 1)
            elif depth == 0 and isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                t = n.targets[0].id
                if t.isupper():
                    rows.append({"kind": "const", "name": t, "file": path, "line": n.lineno, "end": n.end_lineno,
                                 "len": n.end_lineno - n.lineno + 1, "params": "", "calls": [], "deco": [], "ret": "",
                                 "doc": lines[n.lineno - 1].strip()[:80], "exported": 1, "lang": "py"})
    visit(tree, "", 0)
    return rows


def generic_index(path, src, lang):
    rows, lines = [], src.split("\n")
    stack = []  # (name, indent, start, kind)
    for i, l in enumerate(lines, 1):
        if not l.strip() or l.lstrip().startswith(("//", "*", "#", "/*")):
            continue
        m = DEF.match(l)
        if not m:
            continue
        name = m.group("name") or m.group("cname") or m.group("mname")
        if not name or name in KW:
            continue
        kw = m.group("kw") or ""
        params = m.group("params") or m.group("aparams") or m.group("mparams") or m.group("one") or ""
        ind = len(m.group("ind"))
        kind = "class" if kw in ("class", "interface", "struct", "impl", "enum", "trait", "module", "type") else ("method" if m.group("mname") and stack else "function")
        while stack and stack[-1][1] >= ind:
            stack.pop()
        full = (stack[-1][0] + "." + name) if stack and kind != "class" and stack[-1][3] == "class" else name
        rows.append({"kind": kind, "name": full, "file": path, "line": i, "end": i, "len": 1, "params": params.strip(),
                     "calls": [], "deco": [], "ret": "", "doc": "",
                     "exported": 1 if (m.group("exp") or "pub" in l[:ind + 20] or "public" in l[:ind + 30] or (lang == "go" and name[:1].isupper())) else 0, "lang": lang})
        stack.append((name, ind, i, kind))
    # end lines by brace matching / indentation, and calls per span
    for r in rows:
        depth, started, end = 0, False, r["line"]
        for j in range(r["line"] - 1, min(len(lines), r["line"] + 2000)):
            depth += lines[j].count("{") - lines[j].count("}")
            if "{" in lines[j]:
                started = True
            if started and depth <= 0:
                end = j + 1
                break
            if not started and j > r["line"] + 2:
                end = r["line"]
                break
        r["end"] = end
        r["len"] = end - r["line"] + 1
        body = "\n".join(lines[r["line"] - 1:end])
        r["calls"] = sorted({c for c in CALL.findall(body) if c.split(".")[0] not in KW and c != r["name"]})
    return rows


def build(prev):
    files, rows, reused = {}, [], 0
    for p in list_files():
        ext = os.path.splitext(p)[1]
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        old = prev.get("files", {}).get(p)
        if old and old["mt"] == mt:
            files[p] = old
            rows += old["rows"]
            reused += 1
            continue
        try:
            src = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if len(src) > 2_000_000:
            continue
        r = py_index(p, src) if LANG[ext] == "py" else generic_index(p, src, LANG[ext])
        files[p] = {"mt": mt, "rows": r}
        rows += r
    return {"files": files, "built": time.time()}, rows


def load_index(force=False):
    prev = {}
    if not force:
        try:
            prev = json.load(open(IDX, encoding="utf-8"))
        except Exception:
            prev = {}
    idx, rows = build(prev)
    json.dump(idx, open(IDX, "w", encoding="utf-8"))
    return rows


FILTER = re.compile(r"^(\w+)(!~|!=|>=|<=|~|=|>|<)(.*)$")


def match(row, filters):
    for col, op, val in filters:
        v = row.get(col, "")
        if isinstance(v, list):
            if op == "=":
                if not any(x == val or x.endswith("." + val) for x in v):
                    return False
            elif op == "~":
                if not any(re.search(val, x) for x in v):
                    return False
            elif op == "!=":
                if any(x == val or x.endswith("." + val) for x in v):
                    return False
            elif op == "!~":
                if any(re.search(val, x) for x in v):
                    return False
            continue
        s = str(v)
        if op == "=" and s != val and not (col == "name" and s.endswith("." + val)):
            return False
        if op == "!=" and (s == val or (col == "name" and s.endswith("." + val))):
            return False
        if op == "~" and not re.search(val, s):
            return False
        if op == "!~" and re.search(val, s):
            return False
        if op in (">", "<", ">=", "<="):
            try:
                a, b = float(s), float(val)
            except ValueError:
                return False
            if not {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[op]:
                return False
    return True


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if a[0] == "--reindex":
        rows = load_index(force=True)
        print(f"[q: indexed {len(rows)} symbols]")
        return 0
    rows = load_index()
    if a[0] == "--stats":
        langs = {}
        for r in rows:
            langs[r["lang"]] = langs.get(r["lang"], 0) + 1
        print(f"[q: {len(rows)} symbols; " + ", ".join(f"{k}={v}" for k, v in sorted(langs.items())) + "]")
        return 0
    cols, limit, query = ["kind", "name", "file", "line", "len"], 50, []
    i = 0
    while i < len(a):
        if a[i] == "--cols":
            cols = a[i + 1].split(",")
            i += 2
        elif a[i] == "--limit":
            limit = int(a[i + 1])
            i += 2
        else:
            query.append(a[i])
            i += 1
    filters, sort = [], None
    for tok in " ".join(query).split():
        m = FILTER.match(tok)
        if not m:
            print(f"bad filter: {tok}")
            return 2
        col, op, val = m.groups()
        if col == "sort":
            sort = val
        else:
            filters.append((col, op, val))
    hits = [r for r in rows if match(r, filters)]
    if sort:
        desc = sort.startswith("-")
        key = sort.lstrip("-")
        hits.sort(key=lambda r: (r.get(key, 0) if isinstance(r.get(key, 0), (int, float)) else str(r.get(key, ""))), reverse=desc)
    for r in hits[:limit]:
        vals = []
        for c in cols:
            v = r.get(c, "")
            if isinstance(v, list):
                v = ",".join(v)[:120]
            vals.append(str(v))
        print("  ".join(vals))
    more = f", {len(hits) - limit} more (--limit)" if len(hits) > limit else ""
    print(f"[q: {len(hits)} of {len(rows)} symbols{more}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
