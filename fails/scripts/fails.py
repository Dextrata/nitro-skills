#!/usr/bin/env python3
"""fails: run tests, linters or type checkers; print only what failed and what changed.
Executed, never read.

  fails.py CMD...           run CMD; print the summary, each failure once, and the delta
                            (new / still / fixed) against the previous run of the same CMD
  fails.py --stdin          parse piped output:  some-cmd 2>&1 | fails.py --stdin
  fails.py --file F         parse a saved log
  fails.py --all CMD...     do not cap the list at 20 failures
  fails.py --show F3        the full raw block of failure F3 from the last run
  fails.py --forget CMD...  drop the stored failure set for CMD

Understands pytest, unittest, jest, vitest, mocha, go test, cargo test, dotnet test,
and the file:line diagnostics of tsc, eslint, ruff, flake8, pylint, mypy, pyright,
rustc/clippy and gcc/clang. Anything else prints the exit code and the last lines.
Each failure is keyed (test id; file + rule + message for a diagnostic, so line shifts
do not count as changes) and compared with the last run of the same command.
"""
import sys, os, re, json, hashlib, subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CACHE = os.environ.get("NITRO_CACHE") or os.path.join(os.path.expanduser("~"), ".cache", "nitro")
ROOT = os.path.join(CACHE, "fails", hashlib.md5(os.path.normcase(os.path.abspath(os.getcwd())).lower().encode()).hexdigest()[:8])
os.makedirs(ROOT, mode=0o700, exist_ok=True)
CAP = 20

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
VENDOR = re.compile(r"site-packages|dist-packages|node_modules|[\\/]\.venv[\\/]|[\\/]venv[\\/]|[\\/]lib[\\/]python\d|node:internal|"
                    r"<anonymous>|internal/|[\\/]vendor[\\/]|[\\/]\.cargo[\\/]|rustc[\\/]|[\\/]go[\\/]src[\\/]|[\\/]usr[\\/]lib[\\/]|"
                    r"<frozen |importlib[\\/]|_pytest[\\/]|pluggy[\\/]|[\\/]unittest[\\/]|jest-|[\\/]vitest[\\/]|[\\/]mocha[\\/]|"
                    r"System\.|Microsoft\.|Xunit\.|NUnit\.", re.I)
FRAME_RX = [
    ("py", re.compile(r'File "(?P<f>[^"]+)", line (?P<l>\d+), in (?P<fn>\S+)')),
    ("pt", re.compile(r"^(?P<f>(?:[A-Za-z]:)?[^\s:]+\.py):(?P<l>\d+): ?(?:in (?P<fn>\S+)|(?P<msg>[A-Z]\w*.*))?$")),
    ("js", re.compile(r"^\s*at (?:(?P<fn>[^\s(]+) \()?(?P<f>[^\s()]+?):(?P<l>\d+):\d+\)?$")),
    ("vt", re.compile(r"^\s*❯ (?:(?P<fn>\S+) )?(?P<f>[^\s:]+?):(?P<l>\d+):\d+")),
    ("go", re.compile(r"^\s+(?P<f>(?:[A-Za-z]:)?[^\s:]+\.go):(?P<l>\d+): ")),
    ("rs", re.compile(r"panicked at (?P<f>[^\s:]+):(?P<l>\d+):\d+")),
    ("cs", re.compile(r"^\s*at (?P<fn>\S+) in (?P<f>.+?):line (?P<l>\d+)")),
    ("rb", re.compile(r"(?P<f>[^\s:]+\.rb):(?P<l>\d+):in [`'](?P<fn>[^']+)'")),
]
MSG_HINT = re.compile(r"(Error|Exception|assert|Expected|Received|expect\(|panicked|left:|right:|failed|mismatch|Message|Actual|"
                      r"Difference|toBe|toEqual|should|got |want |\bnil\b|undefined|None)", re.I)
SKIP_MSG = re.compile(r"^(Traceback \(most recent call last\)|\s*at |\s*❯ |\s*>?\s*\d+\s*\||\s*>\s|\s*[-_=~⎯]{3,}|\s*\^+\s*$|"
                      r"note: run with|Stack Trace:|Error Message:|failures:|\s*\d+ \||\s*\||\s*[-+] (Expected|Received)\s*$|"
                      r"\s*\+ expected - actual\s*$|\s*Difference:\s*$)")


def short(p):
    p = p.replace("\\", "/")
    parts = p.split("/")
    return "/".join(parts[-3:]) if len(parts) > 3 else p


def frames(block):
    out = []
    for i, l in enumerate(block):
        for tag, rx in FRAME_RX:
            m = rx.search(l)
            if not m:
                continue
            f = m.group("f")
            if VENDOR.search(f):
                break
            gd = m.groupdict()
            fn = (gd.get("fn") or "").strip()
            src = ""
            if tag == "py" and i + 1 < len(block) and not FRAME_RX[0][1].search(block[i + 1]) and not block[i + 1].lstrip().startswith("File "):
                src = block[i + 1].strip()
            if tag == "js" and fn in ("Object.<anonymous>", "Context.<anonymous>", "Proxy.<anonymous>"):
                fn = ""
            out.append((short(f), m.group("l"), fn, src))
            break
    return out


def pick(frs):
    """The raise site plus the test frame when they differ, at most two lines."""
    uniq = []
    for fr in frs:
        if not any(fr[0] == u[0] and fr[1] == u[1] for u in uniq):
            uniq.append(fr)
    if not uniq:
        return []
    chosen = [uniq[-1]]
    if len(uniq) > 1 and uniq[0][0] != uniq[-1][0]:
        chosen.append(uniq[0])
    out = []
    for f, l, fn, src in chosen:
        fn = fn[:-2] if fn.endswith("()") else fn
        s = f"{f}:{l}" + (f" {fn}()" if fn else "") + (f"  {src[:100]}" if src else "")
        out.append(s)
    return out


def messages(block, limit=3):
    cands, pref, after_frame = [], [], False
    for l in block:
        s = l.rstrip()
        if not s.strip():
            continue
        if any(rx.search(s) for _, rx in FRAME_RX):
            after_frame = FRAME_RX[0][1].search(s) is not None  # a Python File frame is followed by its source line
            continue
        if after_frame or SKIP_MSG.match(s):
            after_frame = False
            continue
        m = re.match(r"^E\s{2,}(.*)$", s)
        if m:
            pref.append(m.group(1).strip())
            continue
        s = s.strip()
        (pref if MSG_HINT.search(s) else cands).append(s)
    out = []
    for s in pref + (cands[-2:] if not pref else []):
        if s not in out:
            out.append(s[:220])
    return out[:limit]


def fail(key, title, block, msgs=None):
    return {"key": key, "title": title, "msgs": (msgs if msgs is not None else messages(block)), "frames": frames(block), "block": block}


def sections(lines, start_rx, end_rx, keep_start=False):
    """Split lines into (title, block) pairs; a section ends at the next start or an end line."""
    out, cur, buf = [], None, []
    for l in lines:
        m = start_rx.match(l)
        if m:
            if cur is not None:
                out.append((cur, buf))
            cur, buf = m, ([l] if keep_start else [])
            continue
        if cur is not None:
            if end_rx and end_rx.match(l):
                out.append((cur, buf))
                cur, buf = None, []
                continue
            buf.append(l)
    if cur is not None:
        out.append((cur, buf))
    return out


# ------------------------------------------------------------------ parsers
COUNT_WORDS = r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|warnings?|deselected|passing|failing|pending|todo|total|ignored)"


def counts_in(text):
    c = {}
    for n, k in re.findall(COUNT_WORDS, text):
        k = {"errors": "error", "warnings": "warning"}.get(k, k)
        c[k] = c.get(k, 0) + int(n)
    return c


def fmt_counts(c, order=("passed", "failed", "error", "skipped", "xfailed", "xpassed", "warning")):
    parts = [f"{c[k]} {k}" for k in order if k in c and (c[k] or k in ("passed", "failed"))]
    parts += [f"{v} {k}" for k, v in c.items() if k not in order and k != "total" and v]
    return ", ".join(parts)


PY_SUM = re.compile(r"^=+ (.*?) in [\d.]+s?.*=+$")
PY_SEC = re.compile(r"^_{3,} (.+?) _{3,}$")
PY_END = re.compile(r"^(={3,} |-{3,} Captured|-{3,} generated|FAILED \S+::|ERROR \S+(::| - ))")
PY_SHORT = re.compile(r"^(FAILED|ERROR) (\S+?)(?: - (.*))?$")


def p_pytest(lines):
    if any(re.match(r"^Ran \d+ tests? in", l) for l in lines):
        return None
    sums = [m.group(1) for l in lines if (m := PY_SUM.match(l))]
    secs = sections(lines, PY_SEC, PY_END)
    if not sums and not secs:
        return None
    shorts = [m for l in lines if (m := PY_SHORT.match(l)) and ("::" in m.group(2) or m.group(2).endswith(".py"))]
    counts = counts_in(sums[-1]) if sums else {}

    def sec_for(tid):
        name = tid.split("::")[-1]
        base = re.sub(r"\[.*\]$", "", name)
        cls = ".".join(tid.split("::")[-2:])
        for m, b in secs:
            t = re.sub(r"^ERROR at \w+ of ", "", m.group(1))
            if t in (name, base, cls) or t.endswith("." + name) or t.endswith("." + base):
                return b
        return []

    fails, seen = [], set()
    for m in shorts:
        kind, tid, msg = m.groups()
        if tid in seen:
            continue
        seen.add(tid)
        b = sec_for(tid)
        msgs = messages(b)
        if msg and not any(msg[:60] in x for x in msgs):
            msgs = [msg[:220]] + msgs[:2]
        fails.append(fail(tid, ("ERROR " if kind == "ERROR" else "") + tid, b, msgs))
    if not shorts:
        for m, b in secs:
            fails.append(fail(m.group(1), m.group(1), b))
    return {"runner": "pytest", "kind": "tests", "summary": fmt_counts(counts) or (sums[-1] if sums else f"{len(fails)} failed"),
            "failures": fails}


UT_SEC = re.compile(r"^(FAIL|ERROR): (\S+) \(([^)]+)\)")


def p_unittest(lines):
    ran = next((m for l in lines if (m := re.match(r"^Ran (\d+) tests? in", l))), None)
    if not ran:
        return None
    fails, cur, buf = [], None, []
    for l in lines:
        m = UT_SEC.match(l)
        if m:
            if cur:
                fails.append((cur, buf))
            dotted = m.group(3) if "." in m.group(3) else m.group(3) + "." + m.group(2)
            cur, buf = (m.group(1), dotted), []
            continue
        if cur and (re.match(r"^[-=]{10,}$", l) and any(x.strip() for x in buf) or l.startswith("Ran ")):
            fails.append((cur, buf))
            cur, buf = None, []
            continue
        if cur and not re.match(r"^[-=]{10,}$", l):
            buf.append(l)
    if cur:
        fails.append((cur, buf))
    total = int(ran.group(1))
    tail = next((l for l in lines if re.match(r"^(FAILED|OK)\b", l)), "")
    c = {k: int(v) for k, v in re.findall(r"(failures|errors|skipped|expected failures|unexpected successes)=(\d+)", tail)}
    counts = {"passed": total - sum(c.values()), "failed": c.get("failures", 0), "error": c.get("errors", 0)}
    if c.get("skipped"):
        counts["skipped"] = c["skipped"]
    out = [fail(key, ("ERROR " if kind == "ERROR" else "") + key, b) for (kind, key), b in fails]
    return {"runner": "unittest", "kind": "tests", "summary": fmt_counts(counts), "failures": out}


JEST_SEC = re.compile(r"^\s*● (.+?)\s*$")
JEST_END = re.compile(r"^(Test Suites:|Tests:|Snapshots:|Time:|Ran all test suites)")
VT_SEC = re.compile(r"^ FAIL  (.+?)\s*$")
VT_END = re.compile(r"^\s*(⎯{5,}|Test Files\s|Tests\s+\d)")


def p_jest(lines):
    text = "\n".join(lines)
    jest = re.search(r"^Tests:\s+.*\btotal\b", text, re.M) or re.search(r"^Test Suites:", text, re.M)
    vitest = re.search(r"^\s*Tests\s+\d+ (failed|passed)", text, re.M) or re.search(r"^ FAIL  \S", text, re.M)
    if not (jest or vitest):
        return None
    sumline = next((l for l in lines if re.match(r"^\s*Tests:?\s+\d", l)), "")
    counts = counts_in(sumline)
    counts.pop("total", None)
    fails = []
    secs = sections(lines, VT_SEC, VT_END) if vitest and not jest else sections(lines, JEST_SEC, JEST_END)
    seen = set()
    for m, b in secs:
        title = re.sub(r"\s+\d+\s*ms$", "", m.group(1)).strip()
        if title in seen:
            continue
        seen.add(title)
        fails.append(fail(title, title, b))
    return {"runner": "vitest" if vitest and not jest else "jest", "kind": "tests", "summary": fmt_counts(counts) or sumline.strip(),
            "failures": fails}


MOCHA_SEC = re.compile(r"^\s*(\d+)\) (.+?)\s*$")


def p_mocha(lines):
    idx = next((i for i, l in enumerate(lines) if re.match(r"^\s*\d+ (passing|failing)\b", l)), None)
    if idx is None:
        return None
    head = "\n".join(lines[idx:idx + 4])
    counts = counts_in(head)
    counts = {{"passing": "passed", "failing": "failed", "pending": "skipped"}.get(k, k): v for k, v in counts.items()}
    fails = []
    for m, b in sections(lines[idx:], MOCHA_SEC, None):
        title = m.group(2)
        if b and b[0].strip().endswith(":") and not MSG_HINT.search(b[0]):
            title += " " + b[0].strip().rstrip(":")
            b = b[1:]
        fails.append(fail(title, title, b))
    return {"runner": "mocha", "kind": "tests", "summary": fmt_counts(counts), "failures": fails}


GO_SEC = re.compile(r"^\s*--- FAIL: (\S+) ")
GO_END = re.compile(r"^\s*(--- (PASS|SKIP|FAIL)|=== |FAIL\s*$|FAIL\s+\S|ok\s+\S|PASS\s*$|\?\s+\S)")
GO_LOG = re.compile(r"^\s+(?:[A-Za-z]:)?[^\s:]+\.go:\d+: (.*)$")


def p_go(lines):
    if not any(re.match(r"^(--- FAIL:|FAIL\s+\S+|ok\s+\S+\s+[\d.]+s|ok\s+\S+\s+\(cached\))", l) for l in lines):
        return None
    # with -v the t.Log lines come between "=== RUN X" and "--- FAIL: X"; without it they follow the FAIL line
    runbuf, cur_run, fails, i = {}, None, [], 0
    while i < len(lines):
        l = lines[i]
        m = re.match(r"^\s*=== RUN\s+(\S+)", l)
        if m:
            cur_run = m.group(1)
            runbuf[cur_run] = []
            i += 1
            continue
        m = GO_SEC.match(l)
        if m:
            name = m.group(1)
            b = list(runbuf.get(name, []))
            j = i + 1
            while j < len(lines) and not GO_END.match(lines[j]):
                b.append(lines[j])
                j += 1
            msgs = [x.group(1) for l2 in b if (x := GO_LOG.match(l2))] + [l2.strip() for l2 in b if l2.startswith("panic:")]
            fails.append(fail(name, name, b, msgs[:3]))
            i = j
            continue
        if cur_run is not None and not re.match(r"^\s*--- (PASS|SKIP)", l):
            runbuf[cur_run].append(l)
        i += 1
    okp = sum(1 for l in lines if re.match(r"^ok\s+\S", l))
    badp = sum(1 for l in lines if re.match(r"^FAIL\s+\S", l))
    passed = sum(1 for l in lines if re.match(r"^\s*--- PASS:", l))
    parts = [f"{len(fails)} failed"] + ([f"{passed} passed"] if passed else []) + [f"{okp} ok / {badp} FAIL packages"]
    return {"runner": "go test", "kind": "tests", "summary": ", ".join(parts), "failures": fails}


RS_SEC = re.compile(r"^---- (\S+) stdout ----$")
RS_END = re.compile(r"^(failures:$|test result:)")


def p_cargo(lines):
    res = [l for l in lines if l.startswith("test result: ")]
    if not res:
        return None
    counts = {}
    for l in res:
        for n, k in re.findall(r"(\d+) (passed|failed|ignored)", l):
            counts[k] = counts.get(k, 0) + int(n)
    fails = [fail(m.group(1), m.group(1), b) for m, b in sections(lines, RS_SEC, RS_END)]
    if not fails:
        fails = [fail(m.group(1), m.group(1), []) for l in lines if (m := re.match(r"^test (\S+) \.\.\. FAILED$", l))]
    return {"runner": "cargo test", "kind": "tests", "summary": fmt_counts(counts, ("passed", "failed", "ignored")), "failures": fails}


NET_SEC = re.compile(r"^\s*Failed (\S+)( \[[^\]]*\])?\s*$")
NET_END = re.compile(r"^\s*((Passed|Skipped) \S+|(Failed|Passed)!\s+-)")


def p_dotnet(lines):
    sumline = next((l for l in lines if re.match(r"^\s*(Failed|Passed)!\s+- Failed:", l)), None)
    if not sumline:
        return None
    c = {k.lower(): int(v) for k, v in re.findall(r"(Failed|Passed|Skipped|Total):\s+(\d+)", sumline)}
    counts = {"passed": c.get("passed", 0), "failed": c.get("failed", 0)}
    if c.get("skipped"):
        counts["skipped"] = c["skipped"]
    fails = []
    for m, b in sections(lines, NET_SEC, NET_END):
        msgs = []
        grab = False
        for l in b:
            if l.strip() == "Error Message:":
                grab = True
                continue
            if l.strip() == "Stack Trace:":
                break
            if grab and l.strip():
                msgs.append(l.strip()[:220])
        fails.append(fail(m.group(1), m.group(1), b, msgs[:3]))
    return {"runner": "dotnet test", "kind": "tests", "summary": fmt_counts(counts), "failures": fails}


DIAG = [
    re.compile(r"^(?P<f>(?:[A-Za-z]:)?[^\s:(]+)\((?P<l>\d+),\d+\): (?P<s>error|warning) (?P<c>TS\d+): (?P<m>.*)$"),
    re.compile(r"^(?P<f>(?:[A-Za-z]:)?[^\s:]+?):(?P<l>\d+)(?::\d+)? - (?P<s>error|warning) (?P<c>TS\d+): (?P<m>.*)$"),
    re.compile(r"^\s*(?P<f>(?:[A-Za-z]:)?[^\s:]+?):(?P<l>\d+):\d+ - (?P<s>error|warning|information): (?P<m>.*?)(?: \((?P<c>[\w-]+)\))?$"),
    re.compile(r"^(?P<f>(?:[A-Za-z]:)?[^\s:]+?):(?P<l>\d+)(?::\d+)?: (?P<s>error|warning|note|fatal error): (?P<m>.*?)(?:\s+\[(?P<c>[\w./-]+)\])?$"),
    re.compile(r"^(?P<f>(?:[A-Za-z]:)?[^\s:]+?):(?P<l>\d+):\d+: (?P<c>[A-Z]{1,4}\d{2,4}): (?P<m>.*?)(?: \((?P<r>[\w-]+)\))?$"),
    re.compile(r"^(?P<f>(?:[A-Za-z]:)?[^\s:]+?):(?P<l>\d+):(?:\d+:)? (?P<c>[A-Z]{1,4}\d{2,4}) (?P<m>.*)$"),
    re.compile(r"^\s+(?P<l>\d+):\d+\s+(?P<s>error|warning)\s+(?P<m>.*?)\s{2,}(?P<c>[\w@/-]+)$"),
    re.compile(r"^(?P<s>error|warning)(?:\[(?P<c>E\d+)\])?: (?P<m>.*)$"),
]
FILE_HDR = re.compile(r"^(?:[A-Za-z]:)?[\w./\\-]+\.(?:[cm]?[jt]sx?|vue|svelte|py|rs|go|java|kt|cs|rb|php)$")
DIAG_SUM = re.compile(r"(✖ \d+ problems?.*|Found \d+ errors?.*|\d+ errors?(?:, \d+ warnings?)?(?:, \d+ infos?)?|error: could not compile.*|"
                      r"warning: .* generated \d+ warnings?|Success: no issues found.*|All checks passed!.*|No errors!?)")


def p_diag(lines):
    items, cur_file, pending = [], None, None
    for l in lines:
        s = l.rstrip()
        if pending is not None:
            m = re.match(r"^\s*--> (?P<f>(?:[A-Za-z]:)?[^\s:]+):(?P<l>\d+):\d+", s)
            if m:
                pending.update(f=m.group("f"), l=m.group("l"))
                items.append(pending)
                pending = None
                continue
            pending = None
        if FILE_HDR.match(s.strip()) and " " not in s.strip():
            cur_file = s.strip()
            continue
        for rx in DIAG:
            m = rx.match(s)
            if not m:
                continue
            gd = {k: v for k, v in m.groupdict().items() if v}
            code = gd.get("c") or gd.get("r") or ""
            sev = (gd.get("s") or ("warning" if code[:1] in "CRW" else "error")).lower()
            if sev == "note":
                break
            rule = gd.get("r") or code or " ".join(gd["m"].split()[:4])
            it = {"f": gd.get("f") or cur_file or "?", "l": gd.get("l", "?"), "sev": sev, "rule": rule, "m": gd["m"].strip()}
            if rx is DIAG[-1]:
                pending = it
            else:
                items.append(it)
            break
    if not items:
        return None
    for it in items:
        it["key"] = f"{short(it['f'])}|{it['rule']}|{re.sub(r'\d+', '#', it['m'])[:80]}"
    sumline = next((m.group(1) for l in reversed(lines) if (m := DIAG_SUM.search(l))), None)
    errs = sum(1 for i in items if i["sev"] == "error")
    warns = len(items) - errs
    files = len({i["f"] for i in items})
    summary = sumline or (f"{errs} errors, {warns} warnings in {files} files")
    return {"runner": "diagnostics", "kind": "diag", "summary": summary, "items": items}


PARSERS = [p_unittest, p_pytest, p_jest, p_mocha, p_go, p_cargo, p_dotnet, p_diag]


def parse(text):
    lines = [ANSI.sub("", l).replace("\r", "") for l in text.split("\n")]
    for p in PARSERS:
        r = p(lines)
        if r:
            return r
    tail = [l for l in lines if l.strip() and not (any(rx.search(l) for _, rx in FRAME_RX) and VENDOR.search(l))]
    return {"runner": "unknown", "kind": "none", "summary": f"{len(lines)} lines, no runner recognized", "tail": tail[-25:]}


# ------------------------------------------------------------------ render
def keyset(res):
    if res["kind"] == "tests":
        return [f["key"] for f in res["failures"]]
    if res["kind"] == "diag":
        return sorted({i["key"] for i in res["items"]})
    return []


def render(res, prev, rc, cap):
    keys = keyset(res)
    first = prev is None
    prevset = set(prev or [])
    new = [k for k in keys if k not in prevset]
    fixed = sorted(prevset - set(keys))
    out = [f"[fails] {res['runner']}: {res['summary']}   exit {rc}"]
    labels = {}
    if res["kind"] == "tests":
        for i, f in enumerate(res["failures"][:cap], 1):
            lab = f"F{i}"
            labels[lab] = f
            st = "" if first else ("NEW  " if f["key"] in set(new) else "still")
            out.append(f"{lab:<4}{st:<6}{f['title']}")
            for m in f["msgs"][:3]:
                out.append("          " + m)
            for fr in pick(f["frames"]):
                out.append("          " + fr)
        if len(res["failures"]) > cap:
            out.append(f"    (+{len(res['failures']) - cap} more failures; --all to list them)")
    elif res["kind"] == "diag":
        groups = {}
        for it in res["items"]:
            groups.setdefault((it["sev"], it["rule"]), []).append(it)
        rows = sorted(groups.items(), key=lambda kv: (kv[0][0] != "error", -len(kv[1])))
        for i, ((sev, rule), its) in enumerate(rows[:cap], 1):
            lab = f"F{i}"
            labels[lab] = {"title": rule, "block": [f"{x['f']}:{x['l']} {x['sev']} {x['m']}" for x in its]}
            fresh = sum(1 for x in its if x["key"] in set(new))
            locs = " ".join(f"{short(x['f'])}:{x['l']}" for x in its[:4]) + (f" (+{len(its) - 4})" if len(its) > 4 else "")
            mark = "" if first or not fresh else f" [{fresh} new]"
            out.append(f"{lab:<4}{'warn' if sev == 'warning' else 'err':<5}{rule:<30} x{len(its):<4}{locs}{mark}")
            out.append(f"          {its[0]['m'][:160]}")
        if len(rows) > cap:
            out.append(f"    (+{len(rows) - cap} more rules; --all to list them)")
    else:
        out += ["    " + l[:200] for l in res["tail"]]
    if fixed:
        out.append("FIXED " + ", ".join(k.split("|")[0] + ("|" + k.split("|")[1] if "|" in k else "") for k in fixed[:8])
                   + (f" (+{len(fixed) - 8} more)" if len(fixed) > 8 else ""))
    n = len(keys)
    if first:
        delta = "first run of this command, baseline stored"
    else:
        delta = f"{len(new)} new, {n - len(new)} still" + (f", {len(fixed)} fixed" if fixed else ", nothing fixed")
    hint = "; --show F1 for the full block" if labels else ""
    out.append(f"[fails: {n} failing; {delta}{hint}]")
    return "\n".join(out), labels


def run(argv):
    p = subprocess.run(argv[0] if len(argv) == 1 else argv, shell=(len(argv) == 1), capture_output=True)
    return (p.stdout + p.stderr).decode("utf-8", "replace"), p.returncode


def ckey(name):
    return hashlib.sha1(name.encode("utf-8", "replace")).hexdigest()[:16]


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if a[0] == "--show":
        try:
            last = json.load(open(os.path.join(ROOT, "last.json"), encoding="utf-8"))
            f = last["labels"][a[1]]
        except (OSError, KeyError, ValueError):
            print(f"no failure {a[1] if len(a) > 1 else ''} in the last run")
            return 1
        print(f"{a[1]} {f['title']}")
        print("\n".join(f["block"]) if f["block"] else "(no detail block was captured for it)")
        return 0
    if a[0] == "--forget":
        p = os.path.join(ROOT, ckey(" ".join(a[1:])) + ".json")
        if os.path.exists(p):
            os.remove(p)
        print("forgotten")
        return 0
    cap = CAP
    if a[0] == "--all":
        cap, a = 10 ** 9, a[1:]
    if a[0] == "--stdin":
        text, rc, name = sys.stdin.read(), 0, "stdin"
    elif a[0] == "--file":
        text, rc, name = open(a[1], encoding="utf-8", errors="replace").read(), 0, "file:" + a[1]
    else:
        text, rc = run(a)
        name = " ".join(a)
    res = parse(text)
    store = os.path.join(ROOT, ckey(name) + ".json")
    prev = None
    if os.path.exists(store):
        try:
            prev = json.load(open(store, encoding="utf-8"))["keys"]
        except (OSError, ValueError, KeyError):
            prev = None
    body, labels = render(res, prev, rc, cap)
    json.dump({"cmd": name, "keys": keyset(res)}, open(store, "w", encoding="utf-8"))
    json.dump({"cmd": name, "labels": {k: {"title": v["title"], "block": v["block"]} for k, v in labels.items()}},
              open(os.path.join(ROOT, "last.json"), "w", encoding="utf-8"))
    print(body)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
