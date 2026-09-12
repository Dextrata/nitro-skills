#!/usr/bin/env python3
"""shape: print the SHAPE of structured output instead of the payload.
Executed, never read.

  shape.py CMD...                 run CMD; detect JSON / JSON-lines / CSV / TSV / table / text
  shape.py --file F               shape a file
  shape.py --stdin                shape stdin
  shape.py --path a.b[0].c ...    descend into JSON before shaping (also works on JSON-lines rows)
  shape.py --rows N ...           sample rows to print (default 3)
  shape.py --full ...             print the (pretty) payload; only for small things

JSON: a schema tree with types, cardinalities (distinct values / example values for
leaves), array lengths and element schema. Tabular: columns with inferred type,
distinct count, min/max, and sample rows. Text: line/char count + head + tail.
"""
import sys, os, re, subprocess, json, csv, io

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROWS = 3
MAXKEYS = 40


def run(argv):
    if len(argv) == 1:
        p = subprocess.run(argv[0], shell=True, capture_output=True)
    else:
        p = subprocess.run(argv, capture_output=True)
    return p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"), p.returncode


def descend(obj, path):
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if part.startswith("["):
            obj = obj[int(part[1:-1])]
        else:
            if isinstance(obj, list):
                obj = [o.get(part) if isinstance(o, dict) else None for o in obj]
            else:
                obj = obj[part]
    return obj


def tname(v):
    return {dict: "obj", list: "arr", str: "str", int: "int", float: "num", bool: "bool", type(None): "null"}.get(type(v), "?")


def short(v, n=40):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[:n - 1] + "…"


def merge_schema(items):
    """Union schema of a list of dicts: key -> (types, values seen, present count)."""
    keys = {}
    for it in items:
        if not isinstance(it, dict):
            keys.setdefault("<non-object>", {"types": set(), "vals": [], "n": 0})
            keys["<non-object>"]["types"].add(tname(it))
            keys["<non-object>"]["n"] += 1
            continue
        for k, v in it.items():
            e = keys.setdefault(k, {"types": set(), "vals": [], "n": 0, "sub": []})
            e["types"].add(tname(v))
            e["n"] += 1
            if isinstance(v, (dict, list)):
                e["sub"].append(v)
            elif len(e["vals"]) < 500:
                e["vals"].append(v)
    return keys


def schema_lines(obj, indent, out, n_parent=1):
    pad = "  " * indent
    if isinstance(obj, dict):
        for i, (k, v) in enumerate(obj.items()):
            if i >= MAXKEYS:
                out.append(f"{pad}… {len(obj) - MAXKEYS} more keys")
                break
            if isinstance(v, (dict, list)):
                out.append(f"{pad}{k}: {describe(v)}")
                schema_lines(v, indent + 1, out)
            else:
                out.append(f"{pad}{k}: {tname(v)} = {short(v)}")
    elif isinstance(obj, list):
        if not obj:
            return
        if all(isinstance(x, dict) for x in obj):
            keys = merge_schema(obj)
            for i, (k, e) in enumerate(keys.items()):
                if i >= MAXKEYS:
                    out.append(f"{pad}… {len(keys) - MAXKEYS} more keys")
                    break
                ty = "|".join(sorted(e["types"]))
                pres = "" if e["n"] == len(obj) else f" ({e['n']}/{len(obj)} present)"
                if e.get("sub"):
                    out.append(f"{pad}{k}: {ty}{pres}")
                    schema_lines(e["sub"] if isinstance(e["sub"][0], dict) else e["sub"][0], indent + 1, out)
                else:
                    vals = e["vals"]
                    distinct = {json.dumps(x, sort_keys=True) for x in vals}
                    ex = ", ".join(short(x, 24) for x in list(dict.fromkeys(vals))[:3])
                    card = f"{len(distinct)} distinct" if len(distinct) < len(vals) else "all distinct"
                    rng = ""
                    nums = [x for x in vals if isinstance(x, (int, float)) and not isinstance(x, bool)]
                    if nums and len(nums) == len(vals):
                        rng = f" min={min(nums)} max={max(nums)}"
                    out.append(f"{pad}{k}: {ty}{pres}, {card}{rng}; e.g. {ex}")
        elif all(isinstance(x, list) for x in obj):
            out.append(f"{pad}[arr x{len(obj)}, inner len {min(len(x) for x in obj)}-{max(len(x) for x in obj)}]")
            schema_lines(obj[0], indent + 1, out)
        else:
            types = sorted({tname(x) for x in obj})
            ex = ", ".join(short(x, 24) for x in obj[:5])
            out.append(f"{pad}[{'|'.join(types)} x{len(obj)}] e.g. {ex}")


def describe(v):
    if isinstance(v, dict):
        return f"obj({len(v)} keys)"
    if isinstance(v, list):
        inner = sorted({tname(x) for x in v}) or ["?"]
        return f"arr[{len(v)}] of {'|'.join(inner)}"
    return tname(v)


def shape_json(obj, rows):
    out = [f"root: {describe(obj)}"]
    schema_lines(obj, 1, out)
    if isinstance(obj, list) and obj and rows:
        out.append(f"-- first {min(rows, len(obj))} of {len(obj)}:")
        for x in obj[:rows]:
            out.append("  " + short(x, 240))
    return "\n".join(out)


def parse_json(text):
    t = text.strip()
    try:
        return json.loads(t), "json"
    except Exception:
        pass
    rows = []
    for l in t.split("\n"):
        l = l.strip()
        if not l:
            continue
        try:
            rows.append(json.loads(l))
        except Exception:
            return None, None
    return (rows, "jsonl") if rows else (None, None)


def infer(vals):
    def isnum(s):
        try:
            float(s)
            return True
        except ValueError:
            return False
    nonempty = [v for v in vals if v != ""]
    if not nonempty:
        return "empty"
    if all(isnum(v) for v in nonempty):
        return "num"
    if all(re.match(r"\d{4}-\d{2}-\d{2}", v) for v in nonempty):
        return "date"
    if all(v.lower() in ("true", "false", "yes", "no", "0", "1") for v in nonempty):
        return "bool"
    return "str"


def shape_table(rows, header, rows_n, kind):
    out = [f"{kind}: {len(rows)} rows x {len(header)} cols"]
    for i, col in enumerate(header):
        vals = [r[i] if i < len(r) else "" for r in rows]
        ty = infer(vals)
        distinct = set(vals)
        extra = ""
        if ty == "num":
            nums = [float(v) for v in vals if v != ""]
            if nums:
                extra = f" min={min(nums):g} max={max(nums):g}"
        ex = ", ".join(short(v, 20) for v in list(dict.fromkeys(vals))[:3])
        out.append(f"  {col}: {ty}, {len(distinct)} distinct{extra}; e.g. {ex}")
    if rows_n:
        out.append(f"-- first {min(rows_n, len(rows))}:")
        for r in rows[:rows_n]:
            out.append("  " + " | ".join(short(v, 24) for v in r))
    return "\n".join(out)


def parse_table(text):
    lines = [l for l in text.replace("\r", "").split("\n") if l.strip()]
    if len(lines) < 2:
        return None
    for delim, kind in ((",", "csv"), ("\t", "tsv"), (";", "csv;")):
        try:
            rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delim))
        except csv.Error:
            continue
        if len(rows[0]) >= 2 and sum(1 for r in rows if len(r) == len(rows[0])) >= 0.9 * len(rows):
            return rows[0], rows[1:], kind
    if all("|" in l for l in lines[:5]):
        rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines if not re.match(r"^\s*\|?[-:| ]+\|?\s*$", l)]
        if rows and sum(1 for r in rows if len(r) == len(rows[0])) >= 0.9 * len(rows):
            return rows[0], rows[1:], "table"
    cols = [re.split(r"\s{2,}", l.strip()) for l in lines]
    if len(cols[0]) >= 2 and sum(1 for c in cols if len(c) == len(cols[0])) >= 0.9 * len(cols):
        return cols[0], cols[1:], "columns"
    return None


def shape_text(text):
    lines = text.split("\n")
    n = len(lines)
    out = [f"text: {n} lines, {len(text)} chars"]
    head, tail = lines[:8], lines[-5:] if n > 13 else []
    out += ["  " + l[:200] for l in head]
    if tail:
        out.append(f"  … {n - 13} lines …")
        out += ["  " + l[:200] for l in tail]
    return "\n".join(out)


def main(a):
    global ROWS
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    path, full = None, False
    while a and a[0] in ("--path", "--rows", "--full"):
        if a[0] == "--path":
            path = a[1]
            a = a[2:]
        elif a[0] == "--rows":
            ROWS = int(a[1])
            a = a[2:]
        else:
            full = True
            a = a[1:]
    err, code = "", 0
    if a and a[0] == "--stdin":
        text = sys.stdin.read()
    elif a and a[0] == "--file":
        text = open(a[1], encoding="utf-8", errors="replace").read()
    else:
        text, err, code = run(a)
    obj, kind = parse_json(text)
    if obj is not None:
        if path:
            try:
                obj = descend(obj, path)
            except Exception as e:
                print(f"path error: {e}")
                return 1
        if full:
            print(json.dumps(obj, indent=1, ensure_ascii=False))
        else:
            print(shape_json(obj, ROWS))
            if kind == "jsonl":
                print("(json-lines)")
    else:
        t = parse_table(text)
        if t and not full:
            print(shape_table(t[1], t[0], ROWS, t[2]))
        elif full:
            print(text)
        else:
            print(shape_text(text))
    if err.strip():
        print("-- stderr: " + " / ".join(err.strip().split("\n")[:5])[:300])
    print(f"[shape: {len(text)} chars in, exit {code}]")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
