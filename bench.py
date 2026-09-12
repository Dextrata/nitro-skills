#!/usr/bin/env python3
"""bench: measure what each skill actually saves.

For every skill, a scenario defines the BASELINE (what an agent would have put
in context without the skill) and the SKILL run (what it puts in context
instead). Both are measured in characters of output; tokens are approximated as
characters / 4, the same convention the README uses.

  python bench.py              run every scenario, print the table
  python bench.py --markdown   print it as the README table
  python bench.py NAME...      run only the named scenarios

Fixtures are built in a temp dir; nothing in the repo is touched. Scenarios
whose skill depends on session state (seen, rerun, alias, trace, recall, budget)
run the underlying command twice and measure the second run, because that is
where the skill pays off -- the first run is the baseline it stores.
"""
import sys, os, io, re, json, shutil, subprocess, tempfile, contextlib

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def script(skill, name):
    return os.path.join(ROOT, skill, "scripts", name)


def run(args, cwd, env=None, stdin=None):
    e = dict(os.environ)
    e["NITRO_CACHE"] = os.path.join(cwd, ".nitro-cache")
    e["HOME"] = cwd
    e["USERPROFILE"] = cwd
    if env:
        e.update(env)
    p = subprocess.run([PY] + args, cwd=cwd, env=e, input=stdin,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def toks(s):
    return max(1, len(s) // 4)


def rg(args, cwd):
    """ripgrep via its real executable: on Windows it is often a .cmd shim."""
    exe = shutil.which("rg") or shutil.which("rg.exe")
    if not exe:
        raise RuntimeError("ripgrep (rg) not found on PATH; bench needs it for baselines")
    p = subprocess.run([exe] + args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", shell=exe.lower().endswith(".cmd"))
    return p.stdout or ""


# ---------------------------------------------------------------- fixtures

def big_module(path, funcs=60):
    """A realistic source file: ~60 functions with bodies, imports, a class."""
    L = ["import os", "import sys", "import json", "from typing import Any", ""]
    L += ["class Encoder:", '    """Encode things."""', "",
          "    def __init__(self, indent=None, sort_keys=False):",
          "        self.indent = indent", "        self.sort_keys = sort_keys", "",
          "    def encode(self, o: Any) -> str:",
          "        if isinstance(o, str):", "            return self.encode_string(o)",
          "        return json.dumps(o, indent=self.indent)", "",
          "    def encode_string(self, s: str) -> str:",
          "        return json.dumps(s)", ""]
    for i in range(funcs):
        L += [f"def helper_{i}(value, flag=False, *, name='h{i}'):",
              f'    """Helper number {i}."""',
              "    total = 0",
              "    for item in value:",
              "        if flag:",
              "            total += len(str(item))",
              "        else:",
              "            total += 1",
              f"    return total, name",
              ""]
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return "\n".join(L) + "\n"


def log_file(path, n=4000):
    import random
    rnd = random.Random(7)
    lines = []
    for i in range(n):
        r = rnd.random()
        if r < 0.55:
            lines.append(f"2024-05-0{rnd.randint(1,9)} 10:{i%60:02d}:11 INFO  compiled module_{i%300}.ts in {rnd.randint(3,900)}ms")
        elif r < 0.8:
            lines.append(f"2024-05-01 10:{i%60:02d}:11 DEBUG cache hit for key {rnd.getrandbits(40):010x}")
        elif r < 0.95:
            lines.append(f"2024-05-01 10:{i%60:02d}:11 WARN  slow query took {rnd.randint(200,9000)}ms on table users_{i%12}")
        else:
            lines.append(f"2024-05-01 10:{i%60:02d}:11 ERROR failed to fetch /api/v2/items/{i} status=500")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return "\n".join(lines) + "\n"


def json_file(path, n=400):
    data = {"ok": True, "page": 1, "total": n,
            "items": [{"id": f"itm_{i:05d}", "name": f"Widget {i}",
                       "price": 10 + i % 90, "tags": ["a", "b"][: 1 + i % 2],
                       "owner": {"id": i % 20, "email": f"u{i%20}@example.com"}}
                      for i in range(n)]}
    txt = json.dumps(data, indent=2)
    open(path, "w", encoding="utf-8").write(txt)
    return txt


def crashing_script(path):
    src = '''import json, os, sys

def level3(x):
    return json.loads(x)

def level2(x):
    return level3(x)

def level1(x):
    return level2(x)

level1("{not valid json")
'''
    open(path, "w", encoding="utf-8").write(src)
    return src


def git_repo(d):
    def g(*a):
        subprocess.run(["git"] + list(a), cwd=d, capture_output=True, text=True)
    g("init", "-q")
    g("config", "user.email", "b@e.com")
    g("config", "user.name", "bench")
    big_module(os.path.join(d, "mod.py"))
    g("add", "-A")
    g("commit", "-qm", "base")
    # a realistic mixed change: one real edit, a whitespace churn, an import add
    p = os.path.join(d, "mod.py")
    t = open(p, encoding="utf-8").read()
    t = t.replace("import json\n", "import json\nimport re\n")
    t = t.replace("        total = 0\n", "        total = 0  # start\n")
    t = t.replace("def helper_3(value, flag=False, *, name='h3'):",
                  "def helper_3(value, flag=True, *, name='h3'):")
    open(p, "w", encoding="utf-8").write(t)
    return g


# ---------------------------------------------------------------- scenarios
# Each returns (baseline_text, skill_text, baseline_desc, skill_desc)

def sc_hashpatch(d):
    p = os.path.join(d, "mod.py")
    src = big_module(p)
    hp = script("hashpatch", "hp.py")
    # baseline: read whole file, then Edit echoes old + new text of the hunk
    old = "def helper_3(value, flag=False, *, name='h3'):"
    new = "def helper_3(value, flag=True, *, name='h3'):"
    baseline = src + old + "\n" + new + "\n"
    # skill: outline, grep to the target, patch, trust returned anchors
    out = run([hp, "outline", p], d)
    gr = run([hp, "grep", p, "helper_3", "2"], d)
    m = re.search(r"^(\d+):([0-9a-f]{4})\|def helper_3", gr, re.M)
    patch = f"@@\n@{m.group(1)}:{m.group(2)}\n{new}\n@@\n" if m else ""
    ap = run([hp, "apply", p], d, stdin=patch)
    return baseline, out + gr + ap, "Read whole file + Edit (old + new text)", "outline + grep + patch"


def sc_hashpatch_fair(d):
    p = os.path.join(d, "mod.py")
    src = big_module(p)
    hp = script("hashpatch", "hp.py")
    lines = src.splitlines(True)
    i = next(k for k, l in enumerate(lines) if l.startswith("def helper_3"))
    old = "def helper_3(value, flag=False, *, name='h3'):"
    new = "def helper_3(value, flag=True, *, name='h3'):"
    baseline = "".join(lines[max(0, i - 30):i + 30]) + old + "\n" + new + "\n"
    gr = run([hp, "grep", p, "helper_3", "2"], d)
    m = re.search(r"^(\d+):([0-9a-f]{4})\|def helper_3", gr, re.M)
    patch = f"@@\n@{m.group(1)}:{m.group(2)}\n{new}\n@@\n" if m else ""
    ap = run([hp, "apply", p], d, stdin=patch)
    return baseline, gr + ap, "Read a 60-line range + Edit", "grep + patch"


def sc_probe(d):
    p = os.path.join(d, "mod.py")
    src = big_module(p)
    out = run([script("probe", "probe.py"), p], d)
    return src, out, "Read whole module source", "probe signatures"


def sc_rerun(d):
    p = os.path.join(d, "suite.py")

    def write(fail):
        open(p, "w", encoding="utf-8").write(
            "for i in range(300):\n"
            "    print(f'test_case_{i:03d} ... ok')\n"
            f"print({'FAILED' if fail else 'ALL PASS'!r})\n")

    rr = script("rerun", "rr.py")
    write(True)
    run([rr, PY, p], d)                 # first run: stores the baseline
    write(False)                        # the edit under test
    second = run([rr, PY, p], d)        # same command, one line differs
    raw = subprocess.run([PY, p], cwd=d, capture_output=True, text=True).stdout
    return raw, second, "full 300-line output every run", "diff vs stored baseline"


def sc_seen(d):
    p = os.path.join(d, "mod.py")
    big_module(p)
    sn = script("seen", "seen.py")
    first = run([sn, PY, "-c", f"print(open(r'{p}',encoding='utf-8').read())"], d)
    second = run([sn, PY, "-c", f"print(open(r'{p}',encoding='utf-8').read())"], d)
    raw = subprocess.run([PY, "-c", f"print(open(r'{p}',encoding='utf-8').read())"],
                         cwd=d, capture_output=True, text=True).stdout
    return raw, second, "re-printing output already shown", "folded pointers to earlier blocks"


def sc_alias(d):
    # The realistic shape: a handful of long strings (a deep package prefix, a
    # commit sha, a fully-qualified class) recurring across many lines -- not a
    # unique long name per line, which nothing can compress.
    deep = os.path.join(d, "src", "main", "generated", "protocol", "handlers")
    os.makedirs(deep)
    pkg = "com.example.platform.protocol.handlers.RequestDispatchHandler"
    sha = "9f3c1ab77d24e8b05c6e1f4a3b2d9e8c7a6b5f40"
    raw = []
    for i in range(40):
        f = os.path.join(deep, "dispatch.py")
        raw.append(f"{f}:{i}: {pkg}.handle failed at {sha} (attempt {i})")
    raw = "\n".join(raw) + "\n"
    out = run([script("alias", "al.py"), "--stdin"], d, stdin=raw)
    return raw, out, "repeated deep paths verbatim", "§N tokens + one legend"


def sc_believe(d):
    p = os.path.join(d, "mod.py")
    src = big_module(p)
    claims = ("helper_3(value, flag=False, *, name='h3'); "
              "class Encoder: encode, encode_string; "
              "imports json; calls json.dumps")
    out = run([script("believe", "believe.py"), p, claims], d)
    return src, out, "re-reading the file to confirm", "OK/MISMATCH per claim"


def sc_refactor(d):
    for i in range(6):
        p = os.path.join(d, f"m{i}.py")
        open(p, "w", encoding="utf-8").write(
            "\n".join([f"def caller_{j}():\n    return old_name({j})" for j in range(8)]) + "\n"
            "def old_name(x):\n    return x\n")
    # baseline: a patch per file, each quoting old + new for every hit
    baseline = ""
    for i in range(6):
        t = open(os.path.join(d, f"m{i}.py"), encoding="utf-8").read()
        for line in t.splitlines():
            if "old_name" in line:
                baseline += line + "\n" + line.replace("old_name", "new_name") + "\n"
    out = run([script("refactor", "rf.py"), "rename", "old_name", "new_name", "."], d)
    return baseline, out, "one patch per file (old + new per hit)", "one line of intent, one line per file"


def sc_mine(d):
    p = os.path.join(d, "build.log")
    raw = log_file(p)
    out = run([script("mine", "mine.py"), "--file", p], d)
    return raw, out, "dumping a 4,000-line build log", "templates with counts"


def sc_shape(d):
    p = os.path.join(d, "api.json")
    raw = json_file(p)
    out = run([script("shape", "shape.py"), "--file", p], d)
    return raw, out, "cat a 400-item JSON response", "schema + 3 samples"


def sc_trace(d):
    p = os.path.join(d, "crash.py")
    crashing_script(p)
    tr = script("trace", "trace.py")
    raw = subprocess.run([PY, p], cwd=d, capture_output=True, text=True).stderr
    first = run([tr, PY, p], d)
    second = run([tr, PY, p], d)   # same crash again while iterating
    return raw + raw, first + second, "full traceback, twice while iterating", "user frames once, then a pointer"


def sc_sdiff(d):
    git_repo(d)
    raw = subprocess.run(["git", "diff"], cwd=d, capture_output=True, text=True).stdout
    out = run([script("sdiff", "sdiff.py")], d)
    return raw, out, "git diff", "one row per changed symbol, classified"


def sc_q(d):
    big_module(os.path.join(d, "mod.py"))
    for i in range(4):
        big_module(os.path.join(d, f"extra{i}.py"), funcs=20)
    # baseline: the rg hop sequence an agent would run instead
    baseline = ""
    for pat in ["def ", "class ", "json.dumps", "helper_"]:
        r = rg(["-n", pat, "."], d)
        baseline += r
    run([script("q", "q.py"), "--reindex"], d)
    out = run([script("q", "q.py"), "kind=function calls=json.dumps",
               "--cols", "name,file,line,params"], d)
    out += run([script("q", "q.py"), "kind=class", "--cols", "name,file,line"], d)
    return baseline, out, "4 chained rg calls with overlapping hits", "2 index queries"


def sc_blast(d):
    for i in range(5):
        p = os.path.join(d, f"m{i}.py")
        body = "\n".join(
            f"def caller_{i}_{j}(arg):\n    x = target_fn(arg, {j})\n    return x\n"
            for j in range(6))
        open(p, "w", encoding="utf-8").write(body)
    open(os.path.join(d, "target.py"), "w", encoding="utf-8").write(
        "def target_fn(arg, n):\n    return arg * n\n")
    baseline = rg(["-n", "-C", "3", "target_fn", "."], d)
    run([script("q", "q.py"), "--reindex"], d)
    out = run([script("blast", "blast.py"), "target_fn"], d)
    return baseline, out, "rg -C 3 for every mention", "def + callers grouped + callees"


def sc_recall(d):
    git_repo(d)
    os.makedirs(os.path.join(d, ".claude"), exist_ok=True)
    rc = script("recall", "recall.py")
    run([rc, "save", "where is encoding handled",
         "Encoder.encode in mod.py:13 dispatches to encode_string at mod.py:17"], d)
    # baseline: re-derive it -- the rg calls plus the file slices an agent reads
    baseline = rg(["-n", "-C", "3", "encode", "."], d)
    src = open(os.path.join(d, "mod.py"), encoding="utf-8").read().splitlines(True)
    baseline += "".join(src[0:40])
    out = run([rc, "ask", "where is encoding handled"], d)
    return baseline, out, "re-deriving the answer with rg + reads", "saved answer, refs revalidated"


def sc_budget(d):
    p = os.path.join(d, "build.log")
    raw = log_file(p)
    bg = script("budget", "budget.py")
    out = run([bg, "predict", f"cat {p}"], d)
    return raw, out, "running the command and flooding context", "predicted size, denied before the flood"


SCENARIOS = [
    ("hashpatch", "Edit one function in a 60-function file", sc_hashpatch),
    ("hashpatch-fair", "Same edit, disciplined ranged read", sc_hashpatch_fair),
    ("probe", "Learn a module's API", sc_probe),
    ("rerun", "Second run of a 300-line suite", sc_rerun),
    ("seen", "Re-showing output already seen", sc_seen),
    ("alias", "rg hits across a deep tree", sc_alias),
    ("believe", "Confirm 4 facts about a file", sc_believe),
    ("refactor", "Rename a symbol across 6 files", sc_refactor),
    ("mine", "A 4,000-line build log", sc_mine),
    ("shape", "A 400-item JSON response", sc_shape),
    ("trace", "The same crash twice", sc_trace),
    ("sdiff", "Review a mixed change", sc_sdiff),
    ("q", "Structural question over 5 files", sc_q),
    ("blast", "Find callers before an edit", sc_blast),
    ("recall", "Re-answer a past investigation", sc_recall),
    ("budget", "Predict a flood before running it", sc_budget),
]


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    md = "--markdown" in argv
    want = [a for a in argv if not a.startswith("-")]
    rows = []
    for name, task, fn in SCENARIOS:
        if want and name not in want:
            continue
        d = tempfile.mkdtemp(prefix=f"bench-{name}-")
        try:
            base, skill, bdesc, sdesc = fn(d)
            bt, st = toks(base), toks(skill)
            saved = 0 if bt == 0 else (bt - st) / bt * 100
            rows.append((name, task, bdesc, sdesc, bt, st, saved))
        except Exception as e:
            rows.append((name, task, "ERROR", repr(e)[:60], 0, 0, 0.0))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    if md:
        print("| skill | task | baseline | with skill | baseline tok | skill tok | saved |")
        print("|---|---|---|---|---|---|---|")
        for n, task, bd, sd, bt, st, sv in rows:
            print(f"| **{n}** | {task} | {bd} | {sd} | {bt:,} | {st:,} | **{sv:.0f}%** |")
    else:
        print(f"{'skill':<16} {'baseline':>9} {'skill':>8} {'saved':>7}  task")
        for n, task, bd, sd, bt, st, sv in rows:
            print(f"{n:<16} {bt:>9,} {st:>8,} {sv:>6.0f}%  {task}")
        good = [r for r in rows if r[4]]
        if good:
            tb = sum(r[4] for r in good)
            ts = sum(r[5] for r in good)
            print(f"\n{'TOTAL':<16} {tb:>9,} {ts:>8,} {(tb-ts)/tb*100:>6.0f}%  "
                  f"across {len(good)} scenarios")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
