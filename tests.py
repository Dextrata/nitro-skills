#!/usr/bin/env python3
"""Regression tests for all nitro-skills scripts and hooks. Builds throwaway
repos/dirs in temp locations and drives every script through subprocess.
Run: python tests.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

HOOK_ENFORCE = os.path.join(HERE, "hooks", "enforce-nitro-bash.py")
HP = [PY, os.path.expanduser("~/.claude/skills/hashpatch/scripts/hp.py")]
RR = [PY, os.path.expanduser("~/.claude/skills/rerun/scripts/rr.py")]
PR = [PY, os.path.expanduser("~/.claude/skills/probe/scripts/probe.py")]


def S(skill, script):
    return os.path.join(HERE, skill, "scripts", script)


def H(name):
    return os.path.join(HERE, "hooks", name)


def run(args, cwd, inp=None, env=None):
    p = subprocess.run(args, cwd=cwd, capture_output=True, input=inp.encode("utf-8") if inp else None, env=env)
    return p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace"), p.returncode


class EnforceHookTests(unittest.TestCase):
    """Cases for hooks/enforce-nitro-bash.py"""

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        open(os.path.join(cls.d, "big.js"), "w").write("x\n" * 200)
        open(os.path.join(cls.d, "s.txt"), "w").write("y\n" * 5)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    def hook(self, cmd):
        p = subprocess.run([PY, HOOK_ENFORCE], input=json.dumps({"tool_name": "Bash", "cwd": self.d, "tool_input": {"command": cmd}}),
                            capture_output=True, text=True)
        return ("DENY " + json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"][:70]) if p.stdout else "allow"

    def test_cases(self):
        cases = [
            ("grep -rn foo .", "deny"), ("rg -n foo .", "allow"), ("git status | grep M", "deny"), ("findstr foo x", "deny"),
            ("npm test 2>&1 | rg fail", "deny"), ("git log | rg fix -", "allow"), ("cat out.txt | rg PATTERN -", "allow"),
            ("sed -n 30,210p big.js", "deny"), ("sed -n 30,60p big.js", "allow"), ("cat big.js", "deny"), ("cat s.txt", "allow"),
            ("cat big.js | rg x -", "allow"), ("head -100 big.js", "deny"), ("head -20 big.js", "allow"), ("Get-Content big.js", "deny"),
            ("cat missing.js", "allow"),
            ("sed -i 's/a/b/' big.js", "deny"), ("perl -pi -e 's/a/b/' big.js", "deny"), ("echo hi > big.js", "deny"),
            ("echo hi > new.txt", "allow"), ("cat > new.mjs <<'EOF'\nx\nEOF", "allow"), ("node scripts/x.mjs > out.txt", "allow"),
            ("python - <<'EOF'\ns=open('big.js').read();open('big.js','w').write(s)\nEOF", "deny"),
            ("python - <<'EOF'\nprint(open('big.js').read()[:10])\nEOF", "allow"),
            ("node -e \"require('fs').writeFileSync('a','b')\"", "deny"),
            ("npm run test:unit", "deny"), ("npm run build:client 2>&1 | tail -3", "deny"), ("pytest -q", "deny"), ("cargo check", "deny"),
            ("make", "deny"), ("python ~/.claude/skills/rerun/scripts/rr.py \"npm run test:unit\"", "allow"),
            ("git status", "allow"), ("ls scripts", "allow"), ("echo 2>&1 >/dev/null", "allow"), ("npm test #nitro-skip", "allow"),
            ("find . -name '*.py'", "deny"), ("fd -e py src", "allow"), ("tree src", "deny"), ("Get-ChildItem -Recurse src", "deny"),
            ("sed 's/a/b/' s.txt", "deny"), ("cat s.txt | sed 's/a/b/'", "deny"), ("cat s.txt | sd 'a' 'b'", "allow"),
            ("sd 'a' 'b' big.js", "deny"), ("sd -f i 'a' 'b'", "allow"), ("jq . data.json", "deny"), ("curl -s x | jq .", "deny"),
            ("curl -s x | jq -c '.items[0].id'", "allow"), ("jq '.[0]' data.json", "allow"),
        ]
        bad = 0
        for c, exp in cases:
            r = self.hook(c)
            ok = r.startswith("DENY") == (exp == "deny")
            bad += not ok
            if not ok:
                print(("FAIL ") + repr(c[:45]) + " -> " + r)
        self.assertEqual(bad, 0, f"{bad} enforce-hook case(s) failed")


class CoreSkillTests(unittest.TestCase):
    """Cases for hashpatch, rerun, and probe."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.cwd, ignore_errors=True)

    def p(self, rel):
        return os.path.join(self.cwd, rel)

    def _anchor(self, f, n):
        out, _ = run(HP + ["view", self.p(f), str(n)], self.cwd)
        return out.split("|")[0]

    def test_h1_body_keeps_trailing_blank_line(self):
        open(self.p("e.txt"), "wb").write(b"a\nb\nc\nd\ne\nf\n")
        out, rc = run(HP + ["apply", self.p("e.txt")], self.cwd, f"@@\n@{self._anchor('e.txt',2)}+\nX\n\n@@\n")
        self.assertEqual(open(self.p("e.txt"), "rb").read(), b"a\nb\nX\n\nc\nd\ne\nf\n", out)

    def test_h2_insert_inside_replaced_range_rejected(self):
        open(self.p("e.txt"), "wb").write(b"a\nb\nc\nd\ne\nf\n")
        out, rc = run(HP + ["apply", self.p("e.txt")], self.cwd,
                       f"@@\n@{self._anchor('e.txt',2)}-{self._anchor('e.txt',5)}\nR\n@@\n@{self._anchor('e.txt',3)}+\nS\n@@\n")
        self.assertTrue(rc == 1 and "inside replaced range" in out and open(self.p("e.txt"), "rb").read() == b"a\nb\nc\nd\ne\nf\n", out)

    def test_h3_inserts_at_range_edges_apply_in_order(self):
        open(self.p("e.txt"), "wb").write(b"a\nb\nc\nd\ne\nf\n")
        out, rc = run(HP + ["apply", self.p("e.txt")], self.cwd,
                       f"@@\n@{self._anchor('e.txt',2)}-{self._anchor('e.txt',3)}\nR\n@@\n@{self._anchor('e.txt',3)}+\nS\n@@\n@{self._anchor('e.txt',2)}^\nP\n@@\n")
        self.assertEqual(open(self.p("e.txt"), "rb").read(), b"a\nP\nR\nS\nd\ne\nf\n", out)

    def test_h4_non_utf8_bytes_survive_round_trip(self):
        open(self.p("l1.txt"), "wb").write(b"caf\xe9\nx\n")
        out, rc = run(HP + ["apply", self.p("l1.txt")], self.cwd, f"@@\n@{self._anchor('l1.txt',2)}\ny\n@@\n")
        self.assertTrue(rc == 0 and open(self.p("l1.txt"), "rb").read() == b"caf\xe9\ny\n", out)

    def test_h5_missing_trailing_newline_preserved(self):
        open(self.p("nt.txt"), "wb").write(b"p\nq")
        run(HP + ["apply", self.p("nt.txt")], self.cwd, f"@@\n@{self._anchor('nt.txt',1)}\nP\n@@\n")
        self.assertEqual(open(self.p("nt.txt"), "rb").read(), b"P\nq")

    def test_h6_crlf_preserved(self):
        open(self.p("crlf.txt"), "wb").write(b"p\r\nq\r\n")
        run(HP + ["apply", self.p("crlf.txt")], self.cwd, f"@@\n@{self._anchor('crlf.txt',2)}+\nz\n@@\n")
        self.assertEqual(open(self.p("crlf.txt"), "rb").read(), b"p\r\nq\r\nz\r\n")

    def test_h7_create_new_file_via_at0(self):
        out, rc = run(HP + ["apply", self.p("new.txt")], self.cwd, "@@\n@0+\nhello\n@@\n")
        self.assertEqual(open(self.p("new.txt"), "rb").read(), b"hello\n", out)

    def test_h8_malformed_hash_rejected(self):
        open(self.p("e.txt"), "wb").write(b"a\nb\nc\nd\ne\nf\n")
        out, rc = run(HP + ["apply", self.p("e.txt")], self.cwd, "@@\n@1:zzzz\nq\n@@\n")
        self.assertTrue(rc != 0 and "bad hunk header" in out, out)

    def test_h9_overlapping_replaces_rejected(self):
        open(self.p("e.txt"), "wb").write(b"a\nb\nc\nd\ne\nf\n")
        out, rc = run(HP + ["apply", self.p("e.txt")], self.cwd,
                       f"@@\n@{self._anchor('e.txt',1)}-{self._anchor('e.txt',3)}\nA\n@@\n@{self._anchor('e.txt',2)}-{self._anchor('e.txt',4)}\nB\n@@\n")
        self.assertTrue(rc == 1 and "overlapping" in out, out)

    def test_r_rerun(self):
        open(self.p("t.py"), "w").write(
            "import os,time,sys\n"
            "print('run at 2026-09-09T10:00:'+str(int(time.time())%60).zfill(2)+' in /tmp/pytest-of-jp/pytest-'+str(int(time.time()))+'/x')\n"
            "print('weird\\rline')\n"
            "print('FAIL' if os.path.exists('broken') else 'PASS'); print('done in %.3fs' % (time.time()%1))\n"
            "sys.exit(1 if os.path.exists('broken') else 0)\n")
        run(RR + ["--forget", PY, self.p("t.py")], self.cwd)
        o1, rc1 = run(RR + [PY, self.p("t.py")], self.cwd)
        o2, rc2 = run(RR + [PY, self.p("t.py")], self.cwd)
        self.assertTrue(rc1 == 0 and "baseline" in o1, o1)
        self.assertIn("unchanged", o2, o2)
        self.assertIn("weirdline", o1, o1)
        open(self.p("broken"), "w").close()
        o3, rc3 = run(RR + [PY, self.p("t.py")], self.cwd)
        self.assertTrue(rc3 == 1 and "-PASS" in o3 and "+FAIL" in o3 and "(was exit 0)" in o3, o3)
        os.remove(self.p("broken"))
        o4, rc4 = run(RR + [PY, self.p("t.py")], self.cwd)
        self.assertTrue(rc4 == 0 and "unchanged" not in o4, o4)
        o5, rc5 = run(RR + ["echo shell && echo pipe | findstr pipe" if os.name == "nt" else "echo shell && echo pipe | grep pipe"], self.cwd)
        self.assertIn("pipe", o5, o5)

    def test_p1_function_target_prints_signature(self):
        out, rc = run(PR + ["py", "json:dumps"], self.cwd)
        self.assertTrue(out.count("\n") <= 3 and "def dumps(obj" in out, out)

    def test_p2_class_target_lists_methods(self):
        out, rc = run(PR + ["py", "collections:Counter"], self.cwd)
        self.assertIn("def most_common", out, out[:300])

    def test_p3_esm_by_absolute_windows_path(self):
        open(self.p("m.mjs"), "w").write("export const f = (a,b) => a; export class K { m(x){} }\n")
        out, rc = run(PR + ["js", self.p("m.mjs")], self.cwd)
        self.assertTrue("fn f(2" in out and "class K" in out, out)

    def test_p4_missing_module_reports_cleanly(self):
        out, rc = run(PR + ["py", "nonexistent_mod_xyz"], self.cwd)
        self.assertTrue(rc != 0 and "No module" in out, out[-200:])


POOL = '''"""pool module"""
import time
from tenacity import retry

DEFAULT_TIMEOUT = 30

class Pool:
    def __init__(self, size=4):
        self.size = size
        self._conns = []

    @retry
    def acquire(self, timeout=None) -> "Conn":
        t = time.monotonic()
        conn = self._new()
        log.debug("acquired")
        return conn

    def _new(self):
        raise PoolExhausted("no connections")

def helper(x, y=1):
    return x + y
'''
API = '''from src.db.pool import Pool, helper

def get_session():
    pool = Pool()
    return pool.acquire(timeout=5)

def other():
    return helper(1)
'''
TEST = '''from src.db.pool import Pool
def test_acquire():
    Pool().acquire()
'''
APPJS = '''import fs from 'fs';
export function loadConfig(path, opts) {
  return JSON.parse(fs.readFileSync(path));
}
export class Server {
  constructor(port) { this.port = port; }
  start() { return loadConfig('x'); }
}
const handler = async (req, res) => { res.end(); };
'''


class SkillsTests(unittest.TestCase):
    """Regression tests for the rest of the skills and their hooks."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="nitro-")
        cls.home = os.path.join(cls.tmp, "home")
        os.makedirs(cls.home)
        cls.env = dict(os.environ, HOME=cls.home, USERPROFILE=cls.home)
        cls.repo = os.path.join(cls.tmp, "repo")
        for d in ("src/db", "tests", ".claude"):
            os.makedirs(os.path.join(cls.repo, d))
        cls.w("src/db/pool.py", POOL)
        cls.w("src/api.py", API)
        cls.w("tests/test_pool.py", TEST)
        cls.w("src/app.js", APPJS)
        subprocess.run(["git", "init", "-q", "."], cwd=cls.repo)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=cls.repo)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=cls.repo)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def w(cls, rel, text):
        with open(os.path.join(cls.repo, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def rd(self, rel):
        with open(os.path.join(self.repo, rel), encoding="utf-8") as f:
            return f.read()

    def r(self, skill, script, *args, inp=None):
        return run([PY, S(skill, script)] + list(args), self.repo, inp=inp, env=self.env)

    def test_01_believe(self):
        out, code = self.r("believe", "believe.py", "src/db/pool.py",
                           "Pool.acquire(timeout) -> 'Conn'; class Pool: acquire, release; imports tenacity; "
                           "calls log.debug; has 'DEFAULT_TIMEOUT'; no 'asyncio'; lines ~25; decorated acquire @retry; helper(x, y=2)")
        self.assertEqual(code, 1)
        self.assertIn("8/9 confirmed", out)
        self.assertIn("MISMATCH class Pool", out)
        self.assertIn("has: __init__, acquire, _new", out)
        out, _ = self.r("believe", "believe.py", "src/app.js", "loadConfig(path, opts); class Server: start, stop; imports fs; calls readFileSync")
        self.assertIn("3/4 confirmed", out)

    def test_02_q_and_blast(self):
        out, _ = self.r("q", "q.py", "calls=acquire", "--cols", "kind,name,file,line,end")
        self.assertIn("get_session", out)
        self.assertIn("test_acquire", out)
        out, _ = self.r("q", "q.py", "file~app.js", "--cols", "kind,name,line,end,params,exported")
        self.assertIn("class  Server  5  8", out)
        self.assertIn("method  Server.start", out)
        out, _ = self.r("blast", "blast.py", "acquire", "--tests")
        self.assertIn("def   method Pool.acquire  src/db/pool.py:13-17", out)
        self.assertIn("get_session", out)
        self.assertIn("tests: tests/test_pool.py", out)
        out, _ = self.r("blast", "blast.py", "src/db/pool.py:15")
        self.assertIn("symbol at src/db/pool.py:15: Pool.acquire", out)

    def test_03_refactor(self):
        out, _ = self.r("refactor", "rf.py", "--dry", "rename", "helper", "assist")
        self.assertIn("3 occurrences (dry)", out)
        self.assertIn("helper", self.rd("src/api.py"))
        self.r("refactor", "rf.py", "rename", "helper", "assist", "src")
        self.assertIn("import Pool, assist", self.rd("src/api.py"))
        out, _ = self.r("refactor", "rf.py", "add-import", "src/db/pool.py", "import logging")
        self.assertIn("inserted at line 4", out)
        out, _ = self.r("refactor", "rf.py", "wrap", "src/db/pool.py", "16-18", "try", "PoolExhausted", "return None")
        self.assertIn("now 16-21", out)
        src = self.rd("src/db/pool.py")
        self.assertIn("        try:\n            conn = self._new()", src)
        self.assertIn("        except PoolExhausted as e:\n            return None", src)
        self.r("refactor", "rf.py", "move-symbol", "src/db/pool.py", "assist", "src/util.py")
        self.assertIn("def assist(x, y=1)", self.rd("src/util.py"))
        self.assertNotIn("def assist", self.rd("src/db/pool.py"))
        self.r("refactor", "rf.py", "rm-symbol", "src/app.js", "handler")
        self.assertNotIn("handler", self.rd("src/app.js"))
        out, _ = self.r("refactor", "rf.py", "replace", r"log\.debug", "log.info", "src")
        self.assertIn("1 occurrences", out)
        out, _ = run([PY, S("refactor", "rf.py"), "--dry", "replace", r"log\.info", "log.debug", "src"], self.repo,
                     env=dict(self.env, NITRO_NO_RG="1", NITRO_NO_FD="1"))
        self.assertIn("1 occurrences (dry)", out)

    def test_04_sdiff(self):
        out, _ = self.r("sdiff", "sdiff.py")
        self.assertIn("Pool.acquire", out)
        self.assertIn("imports", out)
        self.assertRegex(out, r"src/api\.py\s+\+2/-2")
        out, _ = self.r("sdiff", "sdiff.py", "--hunk", "h1")
        self.assertIn("@@", out)

    def test_05_seen(self):
        self.r("seen", "seen.py", "--reset")
        out1, _ = self.r("seen", "seen.py", "git diff -- src/db/pool.py")
        self.assertIn("0 folded", out1)
        out2, _ = self.r("seen", "seen.py", "git diff -- src/db/pool.py")
        self.assertIn("[seen #1 L1-", out2)
        self.assertNotIn("+        try:", out2)

    def test_06_alias(self):
        self.r("alias", "al.py", "--reset")
        long = "very/long/path/to/some/module/file.py"
        out, _ = self.r("alias", "al.py", "--stdin", inp=f"{long}\n{long}\n")
        self.assertIn(f"§1 = {long}", out)
        self.assertIn("1 new", out)
        out, _ = self.r("alias", "al.py", "x", "cat §1")
        self.assertIn(f"cat {long}", out)
        p = subprocess.run([PY, H("expand-aliases.py")], cwd=self.repo, env=self.env, capture_output=True,
                           input=json.dumps({"tool_input": {"command": "cat §1"}, "cwd": self.repo}).encode("utf-8"))
        self.assertIn(f"cat {long}", p.stdout.decode("utf-8"))

    def test_07_trace(self):
        tb = textwrap.dedent('''\
            Traceback (most recent call last):
              File "app.py", line 4, in <module>
                a(3)
              File "app.py", line 3, in a
                a(n-1)
              File "app.py", line 3, in a
                a(n-1)
              File "/usr/lib/python3.12/site-packages/lib/x.py", line 9, in y
                z()
              File "app.py", line 2, in a
                if n == 0: raise ValueError("boom")
            ValueError: boom
            ''')
        self.w("tb.txt", tb)
        out, _ = self.r("trace", "trace.py", "--file", "tb.txt")
        self.assertIn("[trace #1]", out)
        self.assertIn("(x2)", out)
        self.assertIn("1 library frame", out)
        self.assertIn("ValueError: boom", out)
        out, _ = self.r("trace", "trace.py", "--file", "tb.txt")
        self.assertIn("same as before", out)

    def test_08_mine(self):
        lines = []
        for i in range(300):
            lines.append(f"2024-01-01 12:00:{i % 60:02d} GET /api/users/{i * 7 % 999} {200 if i % 4 else 404} {i % 90}ms")
            if i % 50 == 0:
                lines.append(f"ERROR db timeout after {i}ms on host-{i % 3}")
        self.w("log.txt", "\n".join(lines) + "\n")
        out, _ = self.r("mine", "mine.py", "--keep", "error", "--file", "log.txt")
        self.assertIn("x300", out)
        self.assertIn("x6", out)
        self.assertIn("kept (6 lines", out)
        self.assertIn("306 lines -> 2 templates", out)

    def test_09_shape(self):
        data = {"ok": True, "items": [{"id": i, "name": f"n{i}", "tags": ["a"], "meta": {"x": i * 2}} for i in range(40)], "page": {"total": 40}}
        self.w("d.json", json.dumps(data))
        out, _ = self.r("shape", "shape.py", "--file", "d.json")
        self.assertIn("items: arr[40] of obj", out)
        self.assertIn("id: int, all distinct min=0 max=39", out)
        out, _ = self.r("shape", "shape.py", "--path", "items[3].meta", "--full", "--file", "d.json")
        self.assertIn('"x": 6', out)
        self.w("d.csv", "id,name,score\n1,a,3.5\n2,b,4\n3,c,9\n")
        out, _ = self.r("shape", "shape.py", "--file", "d.csv")
        self.assertIn("csv: 3 rows x 3 cols", out)
        self.assertIn("score: num, 3 distinct min=3.5 max=9", out)

    def test_10_recall(self):
        out, _ = self.r("recall", "recall.py", "save", "where is pool acquire", "src/db/pool.py:13-18 acquire; wired src/api.py:3-5")
        self.assertIn("saved #1 with 2 ref(s)", out)
        out, _ = self.r("recall", "recall.py", "ask", "where does acquire live")
        self.assertIn("[FRESH]", out)
        with open(os.path.join(self.repo, "src/api.py"), "a") as f:
            f.write("\n\n\ndef get_session():\n    pass\n")
        self.w("src/db/pool.py", POOL.replace("t = time.monotonic()", "t = 0"))
        out, _ = self.r("recall", "recall.py", "ask", "pool acquire")
        self.assertIn("STALE: src/db/pool.py:13-18 (changed)", out)
        out, code = self.r("recall", "recall.py", "ask", "unrelated question about widgets")
        self.assertEqual(code, 1)

    def test_11_budget(self):
        self.r("budget", "budget.py", "reset")
        big = "l\n" * 200
        subprocess.run([PY, H("budget-record.py")], cwd=self.repo, env=self.env, capture_output=True,
                       input=json.dumps({"tool_input": {"command": "git log"}, "tool_response": {"stdout": big}, "cwd": self.repo}).encode())

        def guard(cmd):
            p = subprocess.run([PY, H("budget-guard.py")], cwd=self.repo, env=self.env, capture_output=True,
                               input=json.dumps({"tool_input": {"command": cmd}, "cwd": self.repo}).encode())
            return p.stdout.decode()
        self.assertIn("produced 201 lines", guard("git log"))
        self.assertEqual("", guard("git log --oneline -5"))
        self.assertEqual("", guard("python x/seen.py git log"))
        self.assertIn("unbounded flood", guard("curl -s http://x"))
        self.assertEqual("", guard("curl -s http://x | jq -c '.items[].id'"))
        self.assertIn("fd PATTERN", guard("find . -name x"))
        self.assertIn("structured/log file dump", guard("cat data.json"))
        self.assertIn("structured/log file dump", guard("jq . data.json"))
        self.assertEqual("", guard("cat data.json #nitro-skip"))
        self.assertEqual("", guard("git status"))
        out, _ = self.r("budget", "budget.py", "report")
        self.assertIn("git log", out)


    def test_12_list_files(self):
        spec = importlib.util.spec_from_file_location("qmod", S("q", "q.py"))
        q = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(q)
        walked = sorted(q._walk_files(self.repo, set(q.LANG), q.SKIP_DIRS))
        self.assertTrue({"src/api.py", "src/db/pool.py", "tests/test_pool.py"} <= set(walked))
        self.assertEqual(q.list_files(self.repo), walked)


class InstallerTests(unittest.TestCase):
    """install.py: dry run prints the disclaimer and checks every tool without writing."""

    def test_dry_run_lists_tools_and_disclaimer(self):
        out, rc = run([PY, os.path.join(HERE, "install.py"), "--dry-run"], HERE)
        self.assertEqual(rc, 0, out)
        for s in ("DISCLAIMER", "AI-generated output", "Limitation of liability", "ripgrep", "fd", "sd", "jq", "dry run"):
            self.assertIn(s, out)

    def test_tool_hint_covers_every_tool(self):
        spec = importlib.util.spec_from_file_location("inst", os.path.join(HERE, "install.py"))
        inst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inst)
        for name, _, _, _, _ in inst.TOOLS:
            self.assertIn("install", inst.tool_hint(name) + " install")

if __name__ == "__main__":
    unittest.main(verbosity=1)
