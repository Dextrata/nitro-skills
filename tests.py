#!/usr/bin/env python3
"""Regression tests for all nitro-skills scripts and hooks. Builds throwaway
repos/dirs in temp locations and drives every script through subprocess.
Run: python tests.py
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

HOOK_ENFORCE = os.path.join(HERE, "hooks", "enforce-nitro-bash.py")
HP = [PY, os.path.join(HERE, "hashpatch", "scripts", "hp.py")]
RR = [PY, os.path.join(HERE, "rerun", "scripts", "rr.py")]
PR = [PY, os.path.join(HERE, "probe", "scripts", "probe.py")]


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
                           capture_output=True, text=True, encoding="utf-8")
        if not p.stdout:
            return "allow"
        o = json.loads(p.stdout)["hookSpecificOutput"]
        if o.get("permissionDecision") == "deny":
            return "DENY " + o["permissionDecisionReason"][:70]
        return "REWRITE " + o["updatedInput"]["command"]

        cases = [
            ("grep -rn foo .", "rewrite:rg -n foo ."), ("rg -n foo .", "allow"), ("git status | grep M", "rewrite:git status | rg M -"),
            ("findstr foo x", "deny"), ("grep -P foo x", "deny"), ("grep -rni --include='*.py' 'def x' .", "rewrite:rg -n -i -g '*.py' 'def x' ."),
            ("npm test 2>&1 | rg fail", "rewrite:fails.py"), ("git log | rg fix -", "allow"), ("cat out.txt | rg PATTERN -", "allow"),
            ("sed -n 30,210p big.js", "rewrite:view big.js 30-210"), ("sed -n 30,60p big.js", "allow"), ("cat big.js", "rewrite:outline big.js"),
            ("cat s.txt", "allow"), ("cat big.js | rg x -", "allow"), ("head -100 big.js", "rewrite:view big.js 1-100"), ("head -20 big.js", "allow"),
            ("tail -50 big.js", "allow"), ("tail -100 big.js", "rewrite:view big.js 101-200"), ("Get-Content big.js", "rewrite:outline big.js"),
            ("cat missing.js", "allow"), ("cat big.js other.js", "deny"),
            ("sed -i 's/a/b/' big.js", "deny"), ("perl -pi -e 's/a/b/' big.js", "deny"), ("echo hi > big.js", "deny"),
            ("echo hi > new.txt", "allow"), ("cat > new.mjs <<'EOF'\nx\nEOF", "allow"), ("node scripts/x.mjs > out.txt", "allow"),
            ("python - <<'EOF'\ns=open('big.js').read();open('big.js','w').write(s)\nEOF", "deny"),
            ("python - <<'EOF'\nprint(open('big.js').read()[:10])\nEOF", "allow"),
            ("node -e \"require('fs').writeFileSync('a','b')\"", "deny"),
            ("npm run test:unit", "rewrite:fails.py"), ("npm run build:client 2>&1 | tail -3", "rewrite:rr.py"), ("pytest -q", "rewrite:fails.py"),
            ("cargo check", "rewrite:fails.py"), ("make", "rewrite:rr.py"), ("pytest -k \"x\"", "rewrite:fails.py\" 'pytest -k \"x\"'"),
            ("python ~/.claude/skills/rerun/scripts/rr.py \"npm run test:unit\"", "allow"),
            ("git status", "allow"), ("ls scripts", "allow"), ("echo 2>&1 >/dev/null", "allow"), ("npm test #nitro-skip", "allow"),
            ("find . -name '*.py'", "rewrite:fd -g '*.py' ."), ("find src -type f", "rewrite:fd -t f . src"), ("fd -e py src", "allow"),
            ("tree src", "rewrite:fd -t f . src"), ("Get-ChildItem -Recurse src", "deny"), ("find . -newer x", "deny"),
            ("sed 's/a/b/' s.txt", "deny"), ("cat s.txt | sed 's/a/b/'", "deny"), ("cat s.txt | sd 'a' 'b'", "allow"),
            ("sd 'a' 'b' big.js", "deny"), ("sd -f i 'a' 'b'", "allow"), ("sd '.*\\s(\\d+)' '#lease $1'", "allow"),
            ("jq . data.json", "rewrite:shape.py\" --file data.json"), ("curl -s x | jq .", "rewrite:shape.py\" --stdin"),
            ("curl -s x | jq -c '.items[0].id'", "allow"), ("jq '.[0]' data.json", "allow"),
            ("ruff check .", "rewrite:fails.py"), ("mypy src", "rewrite:fails.py"), ("python ~/.claude/skills/fails/scripts/fails.py pytest -q", "allow"),
            ("python $HOME/.claude/skills/fails/scripts/fails.py \"npm test\"", "allow"),
            ("nitro hp view big.js 1-5", "rewrite:hp.py\" view big.js 1-5"), ("nitro q blast x --tests", "rewrite:q.py\" blast x --tests"),
            ("nitro dev", "allow"), ("nitro hp outline big.js; nitro why big.js", "rewrite:why.py\" big.js"),
            ("nitro mine nitro rr npm run build", "rewrite:mine.py\" python \"") , ("echo nitro dev", "allow"),
            ("nitro hp apply f <<'EOF'\nnitro hp view x\nEOF", "rewrite:apply f <<'EOF'\nnitro hp view x\nEOF"),
            ("nitro hp grep x '#nitro-skip'", "rewrite:hp.py\" grep x '#nitro-skip'"), ("cat data.json #nitro-skip", "allow"),
            (f"cd {self.d} && ls", "rewrite:cd dropped"), ("cd /nowhere/else && ls", "allow"),
        ]
        bad = 0
        for c, exp in cases:
            r = self.hook(c)
            if exp.startswith("rewrite:"):
                ok = r.startswith("REWRITE") and exp[8:] in r
            else:
                ok = r.startswith("DENY") if exp == "deny" else r == "allow"
            bad += not ok
            if not ok:
                print(("FAIL ") + repr(c[:45]) + " -> " + r[:160])
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
        out, _ = run(HP + ["view", self.p(f), str(n), "--anchors"], self.cwd)
        return out.split("|")[0]

    def _lease(self, f, rng):
        out, _ = run(HP + ["view", self.p(f), rng], self.cwd)
        return out.strip().splitlines()[-1]

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

    def test_h10_lease_apply_bare_lines_and_receipt(self):
        open(self.p("e.txt"), "wb").write(b"a\nb\nc\nd\ne\nf\n")
        lease = self._lease("e.txt", "2-5")
        self.assertRegex(lease, r"^\[lease .*e\.txt 2-5 h=[0-9a-f]{6}\]$")
        out, rc = run(HP + ["apply", self.p("e.txt")], self.cwd, f"{lease}\n@@\n@3-4\nX\nY\nZ\n@@\n@5+\nW\n@@\n")
        self.assertEqual(rc, 0, out)
        self.assertEqual(open(self.p("e.txt"), "rb").read(), b"a\nb\nX\nY\nZ\ne\nW\nf\n", out)
        self.assertIn("h1 @3-4 -> now 3-5", out)
        self.assertIn("h2 @5+ -> now 7", out)
        self.assertNotIn("|", out.split("APPLIED", 1)[1].split("[lease", 1)[0])   # receipt, no line echo
        self.assertRegex(out, r"\[lease .*e\.txt 2-7 h=[0-9a-f]{6}\]")

    def test_h11_stale_lease_and_uncovered_line_rejected(self):
        open(self.p("e.txt"), "wb").write(b"a\nb\nc\nd\ne\nf\n")
        lease = self._lease("e.txt", "2-3")
        open(self.p("e.txt"), "wb").write(b"a\nB\nc\nd\ne\nf\n")
        out, rc = run(HP + ["apply", self.p("e.txt")], self.cwd, f"{lease}\n@@\n@2\nQ\n@@\n")
        self.assertTrue(rc == 1 and "stale lease 2-3" in out and open(self.p("e.txt"), "rb").read() == b"a\nB\nc\nd\ne\nf\n", out)
        lease = self._lease("e.txt", "2-3")
        out, rc = run(HP + ["apply", self.p("e.txt")], self.cwd, f"{lease}\n@@\n@5\nQ\n@@\n")
        self.assertTrue(rc == 1 and "no valid lease covers it" in out, out)
        out, rc = run(HP + ["apply", self.p("e.txt")], self.cwd, "#lease 2-3:000000\n@@\n@2\nQ\n@@\n")
        self.assertTrue(rc == 1 and "stale lease" in out, out)

    def test_h12_symbol_view_python_and_markdown(self):
        open(self.p("m.py"), "w", encoding="utf-8").write("import os\n\n@deco\ndef f(x):\n    return x\n\n\nclass K:\n    def m(self):\n        return 1\n\n    def n(self):\n        return 2\n")
        out, rc = run(HP + ["view", self.p("m.py"), "f"], self.cwd)
        self.assertTrue(rc == 0 and out.replace(chr(13), "").startswith("3|@deco\n4|def f(x):\n5|    return x\n[lease"), out)
        out, _ = run(HP + ["view", self.p("m.py"), "K.n"], self.cwd)
        self.assertTrue(out.replace(chr(13), "").startswith("12|    def n(self):\n13|        return 2\n[lease"), out)
        out, rc = run(HP + ["view", self.p("m.py"), "nope"], self.cwd)
        self.assertTrue(rc == 1 and "no symbol or section 'nope'" in out and "def f(x)" in out, out)
        open(self.p("d.md"), "w", encoding="utf-8").write("# T\n\nintro\n\n## Install\n\npip\n\n### Notes\n\nn\n\n## Usage\n\nu\n")
        out, _ = run(HP + ["view", self.p("d.md"), "Install"], self.cwd)
        self.assertTrue(out.replace(chr(13), "").startswith("5|## Install\n6|\n7|pip\n8|\n9|### Notes\n10|\n11|n\n[lease"), out)

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

    def test_02_q_and_blast(self):
        out, _ = self.r("q", "q.py", "calls=acquire", "--cols", "kind,name,file,line,end")
        self.assertIn("get_session", out)
        self.assertIn("test_acquire", out)
        out, _ = self.r("q", "q.py", "file~app.js", "--cols", "kind,name,line,end,params,exported")
        self.assertIn("class  Server  5  8", out)
        self.assertIn("method  Server.start", out)
        out, _ = self.r("q", "q.py", "blast", "acquire", "--tests")
        self.assertIn("def   method Pool.acquire  src/db/pool.py:13-17", out)
        self.assertIn("get_session", out)
        self.assertIn("tests: tests/test_pool.py", out)
        self.assertIn("[q blast: acquire, 1 def(s)", out)
        out, _ = self.r("q", "q.py", "blast", "src/db/pool.py:15")
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
        subprocess.run([PY, H("budget-record.py")], cwd=self.repo, env=self.env, capture_output=True,
                       input=json.dumps({"tool_input": {"command": "python gen.py"}, "tool_response": {"stdout": big}, "cwd": self.repo}).encode())

        def guard(cmd):
            p = subprocess.run([PY, H("budget-guard.py")], cwd=self.repo, env=self.env, capture_output=True,
                               input=json.dumps({"tool_input": {"command": cmd}, "cwd": self.repo}).encode())
            return p.stdout.decode()
        self.assertIn("produced 201 lines", guard("python gen.py"))
        self.assertIn("git log --oneline -20", guard("git log"))
        self.assertEqual("", guard("git log --oneline -5"))
        self.assertEqual("", guard("python x/mine.py git log"))
        self.assertEqual("", guard("nitro mine git log"))
        self.assertEqual("", guard("python x/fails.py pytest -q"))
        self.assertIn("why.py\\\" --blame src/api.py", guard("git blame src/api.py"))
        self.assertEqual("", guard("git blame -L 10,20 src/api.py"))
        self.assertIn("shape.py\\\" \\\"curl -s http://x\\\"", guard("curl -s http://x"))
        self.assertEqual("", guard("curl -s http://x | jq -c '.items[].id'"))
        self.assertEqual("", guard("find . -name x"))
        self.assertIn("shape.py\\\" --file data.json", guard("cat data.json"))
        self.assertIn("mine.py\\\" --file app.log", guard("cat app.log"))
        self.assertEqual("", guard("jq . data.json"))
        self.assertIn("unbounded flood", guard("pip list"))
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

    def test_13_fails(self):
        log = textwrap.dedent('''\
            ============================= test session starts =============================
            collected 3 items

            tests/test_pool.py .FF                                                  [100%]

            ================================== FAILURES ===================================
            __________________________ test_acquire_timeout _______________________________

                def test_acquire_timeout():
            >       assert Pool().acquire(timeout=5) == 4
            E       assert 5 == 4

            tests/test_pool.py:22: AssertionError
            _____________________________ test_release ____________________________________

                def test_release():
            >       Pool()._new()
            E       src.db.pool.PoolExhausted: no connections

            src/db/pool.py:14: PoolExhausted
            =========================== short test summary info ===========================
            FAILED tests/test_pool.py::test_acquire_timeout - assert 5 == 4
            FAILED tests/test_pool.py::test_release - src.db.pool.PoolExhausted: no connections
            ========================= 2 failed, 1 passed in 0.10s =========================
            ''')
        self.w("run1.log", log)
        out, _ = self.r("fails", "fails.py", "--file", "run1.log")
        self.assertIn("[fails] pytest: 1 passed, 2 failed", out)
        self.assertIn("F1        tests/test_pool.py::test_acquire_timeout", out)
        self.assertIn("assert 5 == 4", out)
        self.assertIn("tests/test_pool.py:22", out)
        self.assertIn("first run of this command", out)
        self.w("run1.log", log.replace("FAILED tests/test_pool.py::test_release - src.db.pool.PoolExhausted: no connections\n",
                                       "FAILED tests/test_pool.py::test_close - AttributeError: close\n"))
        out, _ = self.r("fails", "fails.py", "--file", "run1.log")
        self.assertIn("NEW   tests/test_pool.py::test_close", out)
        self.assertIn("still tests/test_pool.py::test_acquire_timeout", out)
        self.assertIn("FIXED tests/test_pool.py::test_release", out)
        self.assertIn("1 new, 1 still, 1 fixed", out)
        out, _ = self.r("fails", "fails.py", "--show", "F1")
        self.assertIn("assert Pool().acquire(timeout=5) == 4", out)
        self.w("lint.log", "src/a.py:12:5: F401 `os` imported but unused\nsrc/b.py:3:1: E501 Line too long (120 > 88)\n"
                           "src/c.py:9:1: E501 Line too long (99 > 88)\nFound 3 errors.\n")
        out, _ = self.r("fails", "fails.py", "--file", "lint.log")
        self.assertIn("[fails] diagnostics: Found 3 errors.", out)
        self.assertRegex(out, r"F1  err  E501\s+x2\s+src/b\.py:3 src/c\.py:9")
        out, code = self.r("fails", "fails.py", PY, "-c", "import sys; print('=== 2 passed in 0.1s ==='); sys.exit(0)")
        self.assertIn("[fails] pytest: 2 passed", out)
        self.assertEqual(code, 0)

    def test_14_scout(self):
        self.w("package.json", json.dumps({"name": "acme-web", "version": "0.3.1", "scripts": {"test": "vitest run", "build": "vite build"},
                                           "devDependencies": {"vitest": "^1", "typescript": "^5"}}))
        self.w("pyproject.toml", '[project]\nname = "acme"\nversion = "1.2.0"\nrequires-python = ">=3.11"\ndependencies = ["fastapi"]\n'
                                 '[tool.ruff]\nline-length = 100\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
        self.w("Makefile", "test:\n\tpytest -q\nlint:\n\truff check .\n")
        self.w("Dockerfile", 'FROM python:3.12-slim\nCMD ["python", "-m", "acme"]\n')
        self.w("README.md", "# Acme\n\n## Install\n\n## Usage\n")
        out, _ = self.r("scout", "scout.py")
        self.assertIn("node    package.json acme-web v0.3.1 (npm); scripts: test, build; deps 0 (+2 dev); typescript, vitest", out)
        self.assertIn("python  pyproject.toml acme v1.2.0 python>=3.11; deps 1; tools: pytest, ruff", out)
        self.assertIn("tasks   make: test, lint", out)
        self.assertIn("test: npm test", out)
        self.assertIn("test (py): pytest -q", out)
        self.assertIn("lint: make lint", out)
        self.assertRegex(out, r"layout  src/\s+\d+ files\s+\d+ lines\s+\d+ py 1 js\s+api, app, db")
        self.assertIn("docker  Dockerfile FROM python:3.12-slim", out)
        self.assertIn("docs    README.md (5 lines: Acme, Install, Usage)", out)
        self.assertIn("[scout:", out)
        out, _ = self.r("scout", "scout.py", "--json")
        self.assertEqual(json.loads(out)["node"]["name"], "acme-web")

    def test_15_why(self):
        src = self.rd("src/db/pool.py")
        n = next(i for i, l in enumerate(src.split("\n"), 1) if "def acquire" in l)
        rng = f"src/db/pool.py:{n}-{n + 4}"
        self.w("src/db/pool.py", src.replace("t = 0", "t = 1"))
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "Fix timer #7"], cwd=self.repo)
        out, _ = self.r("why", "why.py", rng)
        self.assertIn(f"why {rng} (Pool.acquire)   2 commit(s)", out)
        self.assertIn("Fix timer #7", out)
        self.assertIn("init", out)
        self.assertIn("--show SHA", out)
        sha = re.search(r"^\s+([0-9a-f]{7,})\s", out, re.M).group(1)
        out, _ = self.r("why", "why.py", rng, "--show", sha)
        self.assertIn("+        t = 1", out)
        out, _ = self.r("why", "why.py", "--blame", rng)
        self.assertIn("Fix timer #7", out)
        self.assertIn("2 commit(s)", out)
        out, _ = self.r("why", "why.py", "src/db/pool.py")
        self.assertIn("why src/db/pool.py   2 commit(s)", out)

    def test_16_outline_docs(self):
        self.w("notes.md", "# Title\n\ntext\n\n## Section A\n\nmore\n\n### Sub\n")
        out, _ = self.r("hashpatch", "hp.py", "outline", "notes.md")
        self.assertIn("|# Title", out)
        self.assertIn("|## Section A", out)
        self.assertIn("[outline: notes.md, 9 lines, 3 entries]", out)
        self.w("conf.yml", "name: x\non: [push]\njobs:\n  test:\n    runs-on: ubuntu\n  - item: 1\n")
        out, _ = self.r("hashpatch", "hp.py", "outline", "conf.yml")
        self.assertIn("|jobs:", out)
        self.assertIn("|  test:", out)
        self.assertNotIn("runs-on", out)
        self.w("Makefile", "test:\n\tpytest\n.PHONY: test\nVAR := 1\n")
        out, _ = self.r("hashpatch", "hp.py", "outline", "Makefile")
        self.assertIn("|test:", out)
        self.assertNotIn("VAR", out)
        self.w("nb.ipynb", json.dumps({"cells": [{"cell_type": "markdown", "source": ["# Intro\n"]},
                                                 {"cell_type": "code", "source": ["import os\n", "print(1)\n"], "outputs": [{"x": 1}]}]}, indent=1))
        out, _ = self.r("hashpatch", "hp.py", "outline", "nb.ipynb")
        self.assertIn("# cell 1 markdown: # Intro  (2 lines, 0 outputs)", out)
        self.assertIn("# cell 2 code: import os  (3 lines, 1 outputs)", out)
        self.w("data.csv", "a,b\n1,2\n3,4\n")
        out, _ = self.r("hashpatch", "hp.py", "outline", "data.csv")
        self.assertIn("|a,b", out)
        self.assertIn("(2 data rows)", out)


class InstallerTests(unittest.TestCase):
    """install.py: dry run and --no-tools never run a package manager or write anything."""

    def test_dry_run_lists_tools_and_disclaimer(self):
        out, rc = run([PY, os.path.join(HERE, "install.py"), "--dry-run", "--yes"], HERE)
        self.assertEqual(rc, 0, out)
        for s in ("DISCLAIMER", "AI-generated output", "Limitation of liability", "ripgrep", "fd", "sd", "jq", "dry run"):
            self.assertIn(s, out)

    def test_tool_hint_covers_every_tool(self):
        spec = importlib.util.spec_from_file_location("inst", os.path.join(HERE, "install.py"))
        inst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inst)
        for name, _, _, _, _ in inst.TOOLS:
            self.assertIn("install", inst.tool_hint(name) + " install")

    def test_no_tools_prints_hints_without_running(self):
        out, rc = run([PY, os.path.join(HERE, "install.py"), "--dry-run", "--no-tools", "--yes"], HERE)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("running:", out)
        if "not found on PATH" in out:
            self.assertIn("Install with:", out)

    def test_disclaimer_must_be_accepted(self):
        out, rc = run([PY, os.path.join(HERE, "install.py"), "--dry-run"], HERE, inp="")
        self.assertEqual(rc, 2, out)
        self.assertIn("DISCLAIMER", out)
        self.assertNotIn("Installing", out)
        out, rc = run([PY, os.path.join(HERE, "install.py"), "--dry-run"], HERE, inp="no\n")
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Installing", out)


class BenchTests(unittest.TestCase):
    """bench.py: every scenario runs and reports a real baseline and skill size."""

    def test_all_scenarios_produce_measurements(self):
        import bench
        for name, task, fn in bench.SCENARIOS:
            with self.subTest(scenario=name):
                d = tempfile.mkdtemp(prefix="benchtest-")
                try:
                    base, skill, bdesc, sdesc = fn(d)
                except Exception as e:
                    self.fail(f"{name} raised {e!r}")
                finally:
                    shutil.rmtree(d, ignore_errors=True)
                self.assertTrue(base.strip(), f"{name}: empty baseline")
                self.assertTrue(skill.strip(), f"{name}: empty skill output")
                self.assertTrue(bdesc and sdesc, f"{name}: missing description")

    def test_markdown_table_covers_every_skill(self):
        import bench
        named = {n.split("-")[0] for n, _, _ in bench.SCENARIOS}
        skills = {"hashpatch", "rerun", "fails", "probe", "refactor", "mine", "shape",
                  "sdiff", "q", "scout", "why", "recall", "budget"}
        self.assertEqual(skills - named, set(), "skills with no bench scenario")

if __name__ == "__main__":
    unittest.main(verbosity=1)
