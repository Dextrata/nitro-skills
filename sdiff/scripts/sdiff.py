#!/usr/bin/env python3
"""sdiff: semantic git diff. Executed, never read.

  sdiff.py [GIT-DIFF-ARGS...]     e.g. sdiff.py, sdiff.py --cached, sdiff.py HEAD~3, sdiff.py -- src/
  sdiff.py --hunk ID              print hunk ID from the last summary in full
  sdiff.py --file PATH            show all hunks of one file from the last summary

Renders the diff as one line per (file, enclosing symbol): +added/-removed,
hunk ids, and a classification:
  ws        whitespace/blank-only change          imports   only import lines changed
  moved     removed here and added elsewhere       rename    file rename with no content change
  comment   only comment lines changed            new/del   whole file
Anything else is a real change and shows the first changed line as a hint.
"""
import sys, os, re, subprocess, hashlib, json, ast

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.join(os.path.expanduser("~"), ".cache", "nitro", "sdiff")
os.makedirs(ROOT, mode=0o700, exist_ok=True)
LAST = os.path.join(ROOT, hashlib.md5(os.path.normcase(os.path.abspath(os.getcwd())).lower().encode()).hexdigest()[:8] + ".json")
IMPORT = re.compile(r"^\s*(import\s|from\s+\S+\s+import\s|const\s+.*=\s*require\(|export\s+.*from\s)")
COMMENT = re.compile(r"^\s*(#|//|/\*|\*|\*/|<!--)")
DEF_RX = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:def|class|function\*?|fn|func|interface|type|struct|impl|enum|trait)\s+([\w$]+)"
                    r"|^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?(?:\(|function|[\w$]+\s*=>)"
                    r"|^\s*(?:public|private|protected|static|\s)*[\w<>\[\]]+\s+([\w$]+)\s*\([^)]*\)\s*(?:throws\s+[\w, ]+)?\s*\{")


def git(args):
    p = subprocess.run(["git"] + args, capture_output=True)
    return p.stdout.decode("utf-8", "replace"), p.returncode


def symbols(path, src):
    """list of (start, end, name) for top-level and nested defs."""
    out = []
    if path.endswith(".py"):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            tree = None
        if tree:
            def walk(node, prefix=""):
                for n in ast.iter_child_nodes(node):
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        name = prefix + n.name
                        out.append((n.lineno, n.end_lineno, name))
                        walk(n, name + ".")
            walk(tree)
            return out
    lines = src.split("\n")
    stack = []
    for i, l in enumerate(lines, 1):
        m = DEF_RX.match(l)
        if m:
            name = next(g for g in m.groups() if g)
            ind = len(l) - len(l.lstrip())
            while stack and stack[-1][1] >= ind:
                s = stack.pop()
                out.append((s[2], i - 1, s[0]))
            stack.append((name, ind, i))
    for s in stack:
        out.append((s[2], len(lines), s[0]))
    return out


def changed_positions(h):
    """New-file line numbers touched by a hunk: '+' lines where they are, '-' lines where they were."""
    pos, n = [], h["new"]
    for l in h["lines"][1:]:
        if l.startswith("+"):
            pos.append(n)
            n += 1
        elif l.startswith("-"):
            pos.append(n)
        elif l.startswith(" "):
            n += 1
    return pos


def enclosing(syms, positions):
    votes = {}
    for p in positions:
        best = None
        for s, e, name in syms:
            if s <= p <= e and (best is None or (e - s) < (best[1] - best[0])):
                best = (s, e, name)
        key = best[2] if best else "(top level)"
        votes[key] = votes.get(key, 0) + 1
    return max(votes.items(), key=lambda kv: kv[1])[0] if votes else "(top level)"


def parse(diff):
    files, cur = [], None
    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            cur = {"path": line.split(" b/")[-1], "hunks": [], "status": "mod", "old": None}
            files.append(cur)
        elif cur is None:
            continue
        elif line.startswith("rename from"):
            cur["old"] = line[12:]
        elif line.startswith("rename to"):
            cur["status"] = "rename"
        elif line.startswith("new file"):
            cur["status"] = "new"
        elif line.startswith("deleted file"):
            cur["status"] = "del"
        elif line.startswith("Binary"):
            cur["status"] = "binary"
        elif line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            h = {"old": int(m.group(1)), "new": int(m.group(3)), "nlen": int(m.group(4) or 1), "lines": [line], "add": [], "rem": []}
            cur["hunks"].append(h)
        elif cur["hunks"] and line[:1] in ("+", "-", " ", "\\"):
            h = cur["hunks"][-1]
            h["lines"].append(line)
            if line.startswith("+"):
                h["add"].append(line[1:])
            elif line.startswith("-"):
                h["rem"].append(line[1:])
    return files


def classify(h, moved_set):
    add, rem = h["add"], h["rem"]
    na = [l.strip() for l in add if l.strip()]
    nr = [l.strip() for l in rem if l.strip()]
    if na == nr:
        return "ws"
    if all(IMPORT.match(l) for l in na + nr) and (na or nr):
        return "imports"
    if all(COMMENT.match(l) for l in na + nr) and (na or nr):
        return "comment"
    key = "\n".join(na) if na and not nr else None
    if key and key in moved_set:
        return "moved"
    keyr = "\n".join(nr) if nr and not na else None
    if keyr and keyr in moved_set:
        return "moved"
    return ""


def main(a):
    if a and a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if a and a[0] in ("--hunk", "--file"):
        d = json.load(open(LAST, encoding="utf-8"))
        if a[0] == "--hunk":
            print("\n".join(d["hunks"][a[1]]))
        else:
            for hid, (path, lines) in d["byfile"].items():
                if path == a[1]:
                    print("\n".join(lines))
        return 0
    diff, code = git(["diff", "--no-color", "-M"] + a)
    if code:
        print(diff.strip() or "git diff failed")
        return code
    files = parse(diff)
    if not files:
        print("[sdiff: no changes]")
        return 0
    # moved detection: identical pure-add / pure-remove blocks across the diff
    blocks = {}
    for f in files:
        for h in f["hunks"]:
            na = [l.strip() for l in h["add"] if l.strip()]
            nr = [l.strip() for l in h["rem"] if l.strip()]
            if na and not nr:
                blocks.setdefault("\n".join(na), set()).add("a")
            if nr and not na:
                blocks.setdefault("\n".join(nr), set()).add("r")
    moved = {k for k, v in blocks.items() if v == {"a", "r"}}
    store = {"hunks": {}, "byfile": {}}
    hid = 0
    out = []
    tot_a = tot_r = 0
    for f in files:
        path = f["path"]
        if f["status"] == "rename" and not f["hunks"]:
            out.append(f"{f['old']} -> {path}   rename")
            continue
        if f["status"] == "binary":
            out.append(f"{path}   binary")
            continue
        src = ""
        if f["status"] != "del" and os.path.exists(path):
            try:
                src = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                pass
        syms = symbols(path, src) if src else []
        groups = {}
        for h in f["hunks"]:
            hid += 1
            key = f"h{hid}"
            store["hunks"][key] = h["lines"]
            store["byfile"].setdefault(key, (path, h["lines"]))
            sym = enclosing(syms, changed_positions(h)) if syms else "(top level)"
            g = groups.setdefault(sym, {"a": 0, "r": 0, "ids": [], "cls": set(), "hint": ""})
            g["a"] += len(h["add"])
            g["r"] += len(h["rem"])
            g["ids"].append(key)
            c = classify(h, moved)
            g["cls"].add(c)
            if not c and not g["hint"]:
                first = next((l for l in h["add"] + h["rem"] if l.strip()), "")
                g["hint"] = first.strip()[:70]
        tot = sum(g["a"] + g["r"] for g in groups.values())
        status = {"new": "  NEW FILE", "del": "  DELETED"}.get(f["status"], "")
        out.append(f"{path}{status}   +{sum(g['a'] for g in groups.values())}/-{sum(g['r'] for g in groups.values())}")
        if f["status"] in ("new", "del") and tot > 12:
            names = ", ".join(n for _, _, n in syms[:12]) if syms else ""
            if names:
                out.append(f"    symbols: {names}" + (" …" if len(syms) > 12 else ""))
            continue
        for sym, g in groups.items():
            cls = ",".join(sorted(c for c in g["cls"] if c))
            if g["cls"] == {""} or "" in g["cls"]:
                cls = (cls + " " if cls else "") + f"| {g['hint']}"
            out.append(f"    {sym:<32} +{g['a']}/-{g['r']:<4} {' '.join(g['ids']):<12} {cls}")
        tot_a += sum(g["a"] for g in groups.values())
        tot_r += sum(g["r"] for g in groups.values())
    json.dump(store, open(LAST, "w", encoding="utf-8"))
    print("\n".join(out))
    print(f"[sdiff: {len(files)} files, +{tot_a}/-{tot_r}, {hid} hunks; --hunk hN for detail]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
