#!/usr/bin/env python3
"""recall: cross-session memo of investigations, revalidated by line hashes.
Executed, never read.

  recall.py ask "QUESTION"                 best matching saved answers, with each file:line ref checked
  recall.py save "QUESTION" "ANSWER"       store; every path:line (or path:A-B) in ANSWER is hashed now
  recall.py list [FILTER]                  one line per memo
  recall.py forget ID                      delete a memo
  recall.py refresh ID                     re-hash a memo's refs against the current tree (after verifying it)

Store: .claude/recall.jsonl in the repo (commit it so the whole team's agents
benefit) or ~/.cache/nitro/recall if the repo has no .claude directory.
Matching is token overlap on the question plus the answer text; a ref whose
lines changed since save prints as STALE with the current line hash, so the
answer is trusted only where it still holds.
"""
import sys, os, re, json, time, zlib, hashlib, subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REF = re.compile(r"(?<![\w/])((?:[\w.-]+/)*[\w.-]+\.\w{1,5}):(\d+)(?:-(\d+))?")
STOP = {"the", "a", "an", "is", "are", "where", "what", "how", "does", "do", "in", "of", "to", "for", "and", "or", "it", "this", "that", "which", "we", "i", "be", "on", "with", "handled", "handle"}


def store_path():
    if os.path.isdir(".claude"):
        return os.path.join(".claude", "recall.jsonl")
    d = os.path.join(os.path.expanduser("~"), ".cache", "nitro", "recall")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return os.path.join(d, hashlib.md5(os.path.normcase(os.path.abspath(os.getcwd())).lower().encode()).hexdigest()[:8] + ".jsonl")


def load():
    p = store_path()
    if not os.path.exists(p):
        return []
    out = []
    for l in open(p, encoding="utf-8"):
        l = l.strip()
        if l:
            try:
                out.append(json.loads(l))
            except Exception:
                pass
    return out


def save_all(memos):
    with open(store_path(), "w", encoding="utf-8") as f:
        for m in memos:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")


def line_hash(path, a, b):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    except OSError:
        return None
    chunk = "\n".join(l.rstrip() for l in lines[a - 1:b])
    return format(zlib.crc32(chunk.encode()) & 0xFFFF, "04x")


def hash_refs(answer):
    refs = {}
    for m in REF.finditer(answer):
        path, a, b = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
        h = line_hash(path, a, b)
        if h is not None:
            refs[f"{path}:{a}-{b}"] = h
    return refs


def commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True).stdout.decode().strip()
    except Exception:
        return ""


def toks(s):
    return {t for t in re.findall(r"[a-z0-9_]+", s.lower()) if t not in STOP and len(t) > 1}


def score(q, m):
    qt = toks(q)
    if not qt:
        return 0
    mt = toks(m["q"])
    at = toks(m["a"])
    return len(qt & mt) / len(qt | mt) + 0.5 * len(qt & at) / max(len(qt), 1)


def show(m, verbose=True):
    stale, ok = [], 0
    for ref, h in m.get("refs", {}).items():
        path, rng = ref.rsplit(":", 1)
        a, b = (int(x) for x in rng.split("-"))
        cur = line_hash(path, a, b)
        if cur == h:
            ok += 1
        else:
            stale.append(f"{ref} ({'missing' if cur is None else 'changed'})")
    tag = "FRESH" if not stale else ("STALE" if ok == 0 and m.get("refs") else "PARTLY STALE")
    print(f"#{m['id']} [{tag}] {m['q']}   (saved {m.get('at', '')[:10]} @{m.get('commit', '')})")
    if verbose:
        for l in m["a"].split("\n"):
            print("    " + l)
        for s in stale:
            print("    STALE: " + s)


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    memos = load()
    cmd = a[0]
    if cmd == "save":
        q, ans = a[1], " ".join(a[2:]) if len(a) > 2 else sys.stdin.read().strip()
        mid = (max((m["id"] for m in memos), default=0) + 1)
        memos.append({"id": mid, "q": q, "a": ans, "refs": hash_refs(ans), "commit": commit(), "at": time.strftime("%Y-%m-%dT%H:%M")})
        save_all(memos)
        print(f"[recall: saved #{mid} with {len(memos[-1]['refs'])} ref(s) -> {store_path()}]")
        return 0
    if cmd == "list":
        flt = " ".join(a[1:]).lower()
        for m in memos:
            if not flt or flt in m["q"].lower() or flt in m["a"].lower():
                show(m, verbose=False)
        print(f"[recall: {len(memos)} memo(s)]")
        return 0
    if cmd == "forget":
        memos = [m for m in memos if m["id"] != int(a[1])]
        save_all(memos)
        print("[recall: forgotten]")
        return 0
    if cmd == "refresh":
        for m in memos:
            if m["id"] == int(a[1]):
                m["refs"] = hash_refs(m["a"])
                m["commit"] = commit()
                m["at"] = time.strftime("%Y-%m-%dT%H:%M")
        save_all(memos)
        print("[recall: refreshed]")
        return 0
    if cmd == "ask":
        q = " ".join(a[1:])
        ranked = sorted(((score(q, m), m) for m in memos), key=lambda x: -x[0])
        hits = [(s, m) for s, m in ranked if s >= 0.25][:3]
        if not hits:
            print(f"[recall: no memo for '{q}'. Investigate, then: recall save \"{q}\" \"answer with file:line refs\"]")
            return 1
        for s, m in hits:
            show(m)
        print(f"[recall: {len(hits)} hit(s)]")
        return 0
    print(f"unknown command {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
