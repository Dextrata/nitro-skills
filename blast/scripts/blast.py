#!/usr/bin/env python3
"""blast: impact set of a symbol before you touch it. Executed, never read.

  blast.py NAME              definition(s), callers grouped by enclosing symbol, callees
  blast.py NAME --depth 2    transitive callers (who calls the callers)
  blast.py NAME --tests      also list test files that mention NAME
  blast.py FILE:LINE         resolve the symbol at that line first

Uses the q index (same cache) for definitions and callee lists, then a
word-boundary scan of the tree for references, mapped to their enclosing symbol.
"""
import sys, os, re, importlib.util

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
QP = os.path.join(os.path.dirname(os.path.dirname(HERE)), "q", "scripts", "q.py")
spec = importlib.util.spec_from_file_location("qmod", QP)
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


def refs(name, rows, exclude_def=True):
    """(file, line, text) for every word-boundary occurrence outside definitions."""
    rx = re.compile(r"(?<![\w$])" + re.escape(name.split(".")[-1]) + r"(?![\w$])")
    defs = {(r["file"], r["line"]) for r in rows if r["name"].split(".")[-1] == name.split(".")[-1]}
    out = []
    for p in q.list_files():
        try:
            src = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if name.split(".")[-1] not in src:
            continue
        for i, l in enumerate(src.split("\n"), 1):
            if rx.search(l) and not (exclude_def and (p, i) in defs):
                out.append((p, i, l.strip()[:90]))
    return out


def enclosing(rows_by_file, path, line):
    best = None
    for r in rows_by_file.get(path, []):
        if r["line"] <= line <= r["end"] and (best is None or r["len"] < best["len"]):
            best = r
    return best["name"] if best else "(module level)"


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    name, depth, tests = a[0], 1, False
    i = 1
    while i < len(a):
        if a[i] == "--depth":
            depth = int(a[i + 1])
            i += 2
        elif a[i] == "--tests":
            tests = True
            i += 1
        else:
            i += 1
    rows = q.load_index()
    by_file = {}
    for r in rows:
        by_file.setdefault(r["file"], []).append(r)
    m = re.match(r"^(.+):(\d+)$", name)
    if m:
        name = enclosing(by_file, m.group(1).replace("\\", "/"), int(m.group(2)))
        print(f"symbol at {m.group(0)}: {name}")
    short = name.split(".")[-1]
    defs = [r for r in rows if r["name"] == name or r["name"].split(".")[-1] == short]
    if not defs:
        print(f"[blast: no definition of {name} in index; try q --reindex]")
    for r in defs:
        print(f"def   {r['kind']} {r['name']}  {r['file']}:{r['line']}-{r['end']}  ({r['params'][:80]})")
    callees = sorted({c for r in defs for c in r["calls"]})
    if callees:
        local = {c for c in callees if any(x["name"] == c or x["name"].split(".")[-1] == c.split(".")[-1] for x in rows)}
        print(f"calls {len(callees)}: " + ", ".join(sorted(local))[:300] + (f"  (+{len(callees) - len(local)} external)" if len(callees) > len(local) else ""))
    frontier, seen_syms, level = {name}, set(), 1
    total = 0
    while frontier and level <= depth:
        next_frontier = set()
        for sym in sorted(frontier):
            rs = refs(sym, rows)
            groups = {}
            for p, ln, txt in rs:
                enc = enclosing(by_file, p, ln)
                key = (p, enc)
                groups.setdefault(key, []).append((ln, txt))
            if level > 1 and not rs:
                continue
            print(f"{'callers' if level == 1 else 'level ' + str(level)} of {sym}: {len(rs)} refs in {len(groups)} symbols")
            for (p, enc), items in sorted(groups.items()):
                lines = ",".join(str(ln) for ln, _ in items[:6]) + (",…" if len(items) > 6 else "")
                print(f"    {enc:<36} {p}:{lines}   {items[0][1][:60]}")
                total += len(items)
                if enc != "(module level)" and enc not in seen_syms:
                    next_frontier.add(enc)
        seen_syms |= frontier
        frontier = next_frontier - seen_syms
        level += 1
    if tests:
        t = sorted({p for p, _, _ in refs(name, rows, exclude_def=False) if re.search(r"(^|/)(tests?|spec|__tests__)(/|_|\.)|\.test\.|\.spec\.|_test\.", p)})
        print("tests: " + (", ".join(t) if t else "none mention it"))
    print(f"[blast: {name}, {len(defs)} def(s), {total} refs]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
