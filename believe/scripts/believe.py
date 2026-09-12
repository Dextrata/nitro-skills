#!/usr/bin/env python3
"""believe: verify a mental model of a file instead of reading it. Executed,
never read.

  believe.py FILE "CLAIM; CLAIM; ..."
  believe.py FILE < claims.txt        (one claim per line)

Claim forms (Python via ast; JS/TS via pattern matching):
  name(a, b=1) -> T        function exists with these params (and return annotation, if given)
  Class.method(a)          method on a class
  class Name: m1, m2       class exists and has these members
  imports x, y.z           module imports these names/modules
  calls name               something in the file calls `name(`
  has "literal"            literal text occurs
  no "literal"             literal text does not occur
  lines ~N                 line count within 25% of N
  decorated name @deco     function carries decorator
Prints OK/MISMATCH per claim with the truth for mismatches, then a one-line score.
"""
import sys, os, re, ast

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def py_facts(src):
    f = {"funcs": {}, "classes": {}, "imports": set(), "calls": set(), "decos": {}}
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return None, f"syntax error line {e.lineno}"

    def sig(fn):
        a = fn.args
        parts = []
        pos = a.posonlyargs + a.args
        defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
        for arg, d in zip(pos, defaults):
            parts.append(arg.arg + (f"={ast.unparse(d)}" if d is not None else ""))
        if a.vararg:
            parts.append("*" + a.vararg.arg)
        elif a.kwonlyargs:
            parts.append("*")
        for arg, d in zip(a.kwonlyargs, a.kw_defaults):
            parts.append(arg.arg + (f"={ast.unparse(d)}" if d is not None else ""))
        if a.kwarg:
            parts.append("**" + a.kwarg.arg)
        ret = ast.unparse(fn.returns) if fn.returns else None
        return parts, ret

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            f["funcs"].setdefault(node.name, sig(node))
            f["decos"][node.name] = [ast.unparse(d).split("(")[0] for d in node.decorator_list]
        elif isinstance(node, ast.ClassDef):
            members = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            members += [t.id for n in node.body if isinstance(n, ast.Assign)
                        for t in n.targets if isinstance(t, ast.Name)]
            members += [n.target.id for n in node.body
                        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
            f["classes"][node.name] = members
            for n in node.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    f["funcs"][f"{node.name}.{n.name}"] = sig(n)
        elif isinstance(node, ast.Import):
            for al in node.names:
                f["imports"].add(al.name)
        elif isinstance(node, ast.ImportFrom):
            f["imports"].add(node.module or "")
            for al in node.names:
                f["imports"].add(f"{node.module}.{al.name}")
                f["imports"].add(al.name)
        elif isinstance(node, ast.Call):
            try:
                f["calls"].add(ast.unparse(node.func))
            except Exception:
                pass
    return f, None


JS_FN = re.compile(
    r"(?:function\s+(\w+)\s*\(([^)]*)\)"
    r"|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\(([^)]*)\)|(\w+))\s*=>"
    r"|^\s*(?:async\s+)?(\w+)\s*\(([^)]*)\)\s*\{)", re.M)
JS_CLASS = re.compile(r"class\s+(\w+)[^{]*\{")
JS_IMPORT = re.compile(r"(?:import\s+.*?from\s+['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\s*\))")
KW = {"if", "for", "while", "switch", "catch", "function", "return"}


def js_facts(src):
    f = {"funcs": {}, "classes": {}, "imports": set(), "calls": set(), "decos": {}}
    for m in JS_FN.finditer(src):
        name = m.group(1) or m.group(3) or m.group(6)
        params = m.group(2) if m.group(2) is not None else (
            m.group(4) if m.group(4) is not None else m.group(5) or "")
        if name and name not in KW:
            f["funcs"].setdefault(name, ([p.strip() for p in params.split(",") if p.strip()], None))
    for m in JS_CLASS.finditer(src):
        body_start = m.end()
        depth, i = 1, body_start
        while i < len(src) and depth:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        body = src[body_start:i]
        members = re.findall(r"^\s*(?:static\s+|async\s+|get\s+|set\s+)*(\w+)\s*(?:\(|=)", body, re.M)
        f["classes"][m.group(1)] = [x for x in members if x not in KW]
        for mm in re.finditer(r"^\s*(?:static\s+|async\s+)*(\w+)\s*\(([^)]*)\)\s*\{", body, re.M):
            f["funcs"][f"{m.group(1)}.{mm.group(1)}"] = (
                [p.strip() for p in mm.group(2).split(",") if p.strip()], None)
    for m in JS_IMPORT.finditer(src):
        f["imports"].add(m.group(1) or m.group(2))
    for m in re.finditer(r"([\w.$]+)\s*\(", src):
        f["calls"].add(m.group(1))
    return f, None


def pname(p):
    return re.split(r"[=:]", p.strip().lstrip("*"))[0].strip()


def quoted(prefix, c):
    m = re.match(r"^" + prefix + r"\s+\"(.*)\"$", c) or re.match(r"^" + prefix + r"\s+'(.*)'$", c)
    return m.group(1) if m else None


def check(claim, f, src):
    c = claim.strip()
    if not c:
        return None
    lit = quoted("has", c)
    if lit is not None:
        return (lit in src, f'"{lit}" not found')
    lit = quoted("no", c)
    if lit is not None:
        return (lit not in src, f'"{lit}" IS present')
    m = re.match(r"^lines\s*~\s*(\d+)$", c)
    if m:
        n = src.count("\n") + 1
        want = int(m.group(1))
        return (abs(n - want) <= max(3, want * 0.25), f"actually {n} lines")
    m = re.match(r"^imports\s+(.+)$", c)
    if m:
        want = [x.strip() for x in m.group(1).split(",") if x.strip()]
        missing = [w for w in want if not any(
            i == w or i.endswith("." + w) or i.startswith(w) for i in f["imports"])]
        return (not missing, f"not imported: {', '.join(missing)}; "
                             f"imports: {', '.join(sorted(f['imports']))[:200]}")
    m = re.match(r"^calls\s+(.+)$", c)
    if m:
        want = m.group(1).strip()
        ok = any(x == want or x.endswith("." + want) for x in f["calls"])
        stem = want.split(".")[-1].lower()[:4]
        near = [x for x in f["calls"] if stem in x.lower()][:6]
        return (ok, f"no call to {want}; similar: {', '.join(near) or 'none'}")
    m = re.match(r"^decorated\s+([\w.]+)\s+@?([\w.]+)$", c)
    if m:
        d = f["decos"].get(m.group(1))
        if d is None:
            return (False, f"{m.group(1)} not defined")
        return (m.group(2) in d, f"decorators: {d}")
    m = re.match(r"^class\s+(\w+)\s*:\s*(.*)$", c)
    if m:
        members = f["classes"].get(m.group(1))
        if members is None:
            return (False, f"class {m.group(1)} not defined; classes: {', '.join(f['classes']) or 'none'}")
        want = [x.strip() for x in m.group(2).split(",") if x.strip()]
        missing = [w for w in want if w not in members]
        return (not missing, f"missing {missing}; has: {', '.join(members)}")
    m = re.match(r"^([\w.]+)\s*\((.*)\)\s*(?:->\s*(.+))?$", c)
    if m:
        name, params, ret = m.group(1), m.group(2), m.group(3)
        got = f["funcs"].get(name)
        if got is None:
            stem = name.split(".")[-1].lower()
            near = [k for k in f["funcs"] if stem in k.lower()][:5]
            return (False, f"{name} not defined; similar: {', '.join(near) or 'none'}")
        gp, gr = got
        want = [pname(p) for p in params.split(",") if p.strip()]
        gnames = [pname(p) for p in gp if pname(p) not in ("self", "cls", "")]
        gnames_full = [pname(p) for p in gp]
        ok = want == gnames or want == gnames_full
        if ok and ret is not None and gr is not None and ret.strip() != gr.strip():
            ok = False
        truth = f"{name}({', '.join(gp)})" + (f" -> {gr}" if gr else "")
        return (ok, f"actually {truth}")
    return (False, "unparseable claim")


def main(a):
    if len(a) < 1 or a[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    path = a[0]
    claims_text = " ".join(a[1:]) if len(a) > 1 else sys.stdin.read()
    claims = [x for x in re.split(r";|\n", claims_text) if x.strip()]
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except OSError as e:
        print(f"MISMATCH file: {e}")
        return 1
    ext = os.path.splitext(path)[1].lower()
    f, err = (py_facts if ext in (".py", ".pyi") else js_facts)(src)
    if err:
        print(f"MISMATCH file: {err}")
        return 1
    ok_n = 0
    for c in claims:
        r = check(c, f, src)
        if r is None:
            continue
        ok, truth = r
        ok_n += ok
        print(f"{'OK      ' if ok else 'MISMATCH'} {c.strip()}" + ("" if ok else f"  =>  {truth}"))
    print(f"[believe: {ok_n}/{len(claims)} confirmed, {path} {src.count(chr(10)) + 1} lines]")
    return 0 if ok_n == len(claims) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
