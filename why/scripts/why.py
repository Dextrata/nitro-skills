#!/usr/bin/env python3
"""why: the history behind a file or a range of lines, without git log -p or git blame.
Executed, never read.

  why.py FILE                 commits that touched FILE, newest first, one line each
  why.py FILE:A-B             commits that touched lines A-B (git log -L), one line each
  why.py FILE:A               the same for one line
  why.py ... -n 20            more rows (default 12)
  why.py FILE:A-B --show SHA  only that commit's hunk for those lines
  why.py --blame FILE:A-B     one row per run of lines with the same last commit, no code

Each row: sha, date, author, +added/-removed inside the target, subject, and any
#123 / ABC-45 references from the message. The tag says when the code first arrived
and when it last moved. Only git is invoked; nothing is written.
"""
import sys, os, re, subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEP, FS = "\x1e", "\x1f"
REF = re.compile(r"(?<![\w/])(#\d+|[A-Z][A-Z0-9]+-\d+|GH-\d+)\b")
DEF = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|fn|func|struct|enum|interface|trait|impl|type|module|pub fn)\s+(?:\([^)]*\)\s*)?([\w.$]+)"
                 r"|^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?(?:\(|function)"
                 r"|^\s*(?:public|private|protected|static|\s)*[\w<>\[\]]+\s+([\w$]+)\s*\([^)]*\)\s*\{")


def git(args, cwd="."):
    p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        msg = (p.stderr or "").strip().splitlines()
        raise SystemExit("git: " + (msg[-1] if msg else f"exit {p.returncode}"))
    return p.stdout


def parse_target(t):
    m = re.match(r"^(.+?):(\d+)(?:-(\d+))?$", t)
    if m and os.path.exists(m.group(1)):
        a = int(m.group(2))
        b = int(m.group(3) or a)
        return m.group(1).replace("\\", "/"), min(a, b), max(a, b)
    if not os.path.exists(t):
        raise SystemExit(f"no such file: {t}")
    return t.replace("\\", "/"), None, None


def enclosing(path, a):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    except OSError:
        return ""
    best = ""
    for i in range(min(a, len(lines)) - 1, -1, -1):
        m = DEF.match(lines[i])
        if m:
            name = next(g for g in m.groups() if g)
            ind = len(lines[i]) - len(lines[i].lstrip())
            if ind == 0 or not best:
                best = name if not best else f"{name}.{best}"
            if ind == 0:
                break
    return best


def commits_for_range(path, a, b, n, rev=None):
    fmt = f"{SEP}%h{FS}%ad{FS}%an{FS}%s{FS}%b"
    args = ["log", f"-L{a},{b}:{path}", f"--format={fmt}", "--date=short"]
    if rev:
        args.append(rev)
    out = git(args)
    rows = []
    for chunk in out.split(SEP)[1:]:
        head, _, diff = chunk.partition("\ndiff --git")
        parts = head.split(FS)
        if len(parts) < 5:
            continue
        sha, date, author, subject, body = parts[0].strip(), parts[1], parts[2], parts[3], parts[4]
        add = sum(1 for l in diff.split("\n") if l.startswith("+") and not l.startswith("+++"))
        rem = sum(1 for l in diff.split("\n") if l.startswith("-") and not l.startswith("---"))
        rows.append({"sha": sha, "date": date, "author": author, "subject": subject.strip(), "add": add, "rem": rem,
                     "refs": sorted(set(REF.findall(subject + " " + body))), "diff": "diff --git" + diff if diff else ""})
    return rows[:n] if n else rows, len(rows)


def commits_for_file(path, n):
    fmt = f"{SEP}%h{FS}%ad{FS}%an{FS}%s{FS}%b{FS}"
    out = git(["log", f"--format={fmt}", "--date=short", "--numstat", "--follow", "--", path])
    rows = []
    for chunk in out.split(SEP)[1:]:
        parts = chunk.split(FS)
        if len(parts) < 6:
            continue
        sha, date, author, subject, body, stat = parts[0].strip(), parts[1], parts[2], parts[3], parts[4], parts[5]
        m = re.search(r"^(\d+|-)\t(\d+|-)\t", stat, re.M)
        add = int(m.group(1)) if m and m.group(1) != "-" else 0
        rem = int(m.group(2)) if m and m.group(2) != "-" else 0
        rows.append({"sha": sha, "date": date, "author": author, "subject": subject.strip(), "add": add, "rem": rem,
                     "refs": sorted(set(REF.findall(subject + " " + body))), "diff": ""})
    return rows[:n], len(rows)


def fmt_row(r):
    subj = r["subject"][:64] + ("…" if len(r["subject"]) > 64 else "")
    refs = ("  " + " ".join(x for x in r["refs"] if x not in r["subject"])) if any(x not in r["subject"] for x in r["refs"]) else ""
    return f"  {r['sha']:<9}{r['date']:<11}{r['author'][:12]:<13}+{r['add']}/-{r['rem']:<5} {subj}{refs}"


def blame(path, a, b):
    out = git(["blame", "-L", f"{a},{b}", "--date=short", "-w", "--", path])
    runs = []
    for i, l in enumerate(out.split("\n")):
        m = re.match(r"^\^?([0-9a-f]{7,})\s+(?:\S+\s+)?\((.+?)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)\)", l)
        if not m:
            continue
        sha, author, date, ln = m.group(1)[:7], m.group(2).strip(), m.group(3), int(m.group(4))
        if runs and runs[-1]["sha"] == sha and runs[-1]["end"] == ln - 1:
            runs[-1]["end"] = ln
        else:
            runs.append({"sha": sha, "author": author, "date": date, "start": ln, "end": ln})
    subj = {}
    for r in runs:
        if r["sha"] not in subj:
            subj[r["sha"]] = git(["log", "-1", "--format=%s", r["sha"]]).strip()
    for r in runs:
        span = f"{r['start']}" if r["start"] == r["end"] else f"{r['start']}-{r['end']}"
        print(f"  {span:<10}{r['sha'][:7]:<9}{r['date']:<11}{r['author'][:12]:<13}{subj[r['sha']][:60]}")
    print(f"[why --blame: {path}:{a}-{b}, {len(runs)} run(s) from {len(subj)} commit(s)]")


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    n, show, do_blame, target = 12, None, False, None
    i = 0
    while i < len(a):
        if a[i] == "-n":
            n = int(a[i + 1])
            i += 2
        elif a[i] == "--show":
            show = a[i + 1]
            i += 2
        elif a[i] == "--blame":
            do_blame = True
            i += 1
        else:
            target = a[i]
            i += 1
    if not target:
        print(__doc__)
        return 2
    path, lo, hi = parse_target(target)
    if do_blame:
        if lo is None:
            lo, hi = 1, sum(1 for _ in open(path, "rb"))
        blame(path, lo, hi)
        return 0
    if lo is not None:
        sym = enclosing(path, lo)
        rows, total = commits_for_range(path, lo, hi, None if show else n)
        where = f"{path}:{lo}-{hi}" + (f" ({sym})" if sym else "")
        if show:
            hit = next((r for r in rows if r["sha"].startswith(show) or show.startswith(r["sha"])), None)
            if not hit:
                print(f"[why: {show} did not touch {where}]")
                return 1
            print(fmt_row(hit))
            print(hit["diff"].rstrip() or "(no hunk recorded)")
            print(f"[why: hunk of {hit['sha']} for {where}]")
            return 0
    else:
        rows, total = commits_for_file(path, n)
        where = path
    if not rows:
        print(f"[why: no commits touch {where}]")
        return 1
    print(f"why {where}   {total} commit(s)" + (f", showing {len(rows)}" if len(rows) < total else ""))
    for r in rows:
        print(fmt_row(r))
    first = rows[-1] if len(rows) == total else None
    if lo is None and first is None:
        born = git(["log", "--diff-filter=A", "--follow", "--format=%ad %h", "--date=short", "--", path]).strip().split("\n")[-1]
        first_s = f"first {born}" if born else ""
    else:
        first_s = f"first {first['date']} {first['sha']}" if first else ""
    hint = "; --show SHA for its hunk" if lo is not None else "; why FILE:A-B for the lines you care about"
    print(f"[why: {where}, {total} commit(s); {first_s}, last {rows[0]['date']} {rows[0]['sha']}{hint}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
