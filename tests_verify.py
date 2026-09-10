import subprocess, os, sys, tempfile
HP = [sys.executable, os.path.expanduser("~/.claude/skills/hashpatch/scripts/hp.py")]
RR = [sys.executable, os.path.expanduser("~/.claude/skills/rerun/scripts/rr.py")]
PR = [sys.executable, os.path.expanduser("~/.claude/skills/probe/scripts/probe.py")]
os.chdir(tempfile.mkdtemp())
fails = 0
def run(cmd, inp=None):
    p = subprocess.run(cmd, input=inp, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout + p.stderr
def anchor(f, n):
    return run(HP + ["view", f, str(n)])[1].split("|")[0]
def check(name, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "\n   " + detail))
    fails += not cond

# --- hashpatch
open("e.txt", "wb").write(b"a\nb\nc\nd\ne\nf\n")
rc, out = run(HP + ["apply", "e.txt"], f"@@\n@{anchor('e.txt',2)}+\nX\n\n@@\n")
check("H1 body keeps trailing blank line", open("e.txt","rb").read() == b"a\nb\nX\n\nc\nd\ne\nf\n", out)

open("e.txt", "wb").write(b"a\nb\nc\nd\ne\nf\n")
rc, out = run(HP + ["apply", "e.txt"], f"@@\n@{anchor('e.txt',2)}-{anchor('e.txt',5)}\nR\n@@\n@{anchor('e.txt',3)}+\nS\n@@\n")
check("H2 insert inside replaced range rejected", rc == 1 and "inside replaced range" in out and open("e.txt","rb").read() == b"a\nb\nc\nd\ne\nf\n", out)

rc, out = run(HP + ["apply", "e.txt"], f"@@\n@{anchor('e.txt',2)}-{anchor('e.txt',3)}\nR\n@@\n@{anchor('e.txt',3)}+\nS\n@@\n@{anchor('e.txt',2)}^\nP\n@@\n")
check("H3 inserts at range edges apply in order", open("e.txt","rb").read() == b"a\nP\nR\nS\nd\ne\nf\n", out)

open("l1.txt", "wb").write(b"caf\xe9\nx\n")
rc, out = run(HP + ["apply", "l1.txt"], f"@@\n@{anchor('l1.txt',2)}\ny\n@@\n")
check("H4 non-utf8 bytes survive round trip", rc == 0 and open("l1.txt","rb").read() == b"caf\xe9\ny\n", out)

open("nt.txt", "wb").write(b"p\nq")
run(HP + ["apply", "nt.txt"], f"@@\n@{anchor('nt.txt',1)}\nP\n@@\n")
check("H5 missing trailing newline preserved", open("nt.txt","rb").read() == b"P\nq")

open("crlf.txt", "wb").write(b"p\r\nq\r\n")
run(HP + ["apply", "crlf.txt"], f"@@\n@{anchor('crlf.txt',2)}+\nz\n@@\n")
check("H6 CRLF preserved", open("crlf.txt","rb").read() == b"p\r\nq\r\nz\r\n")

rc, out = run(HP + ["apply", "new.txt"], "@@\n@0+\nhello\n@@\n")
check("H7 create new file via @0+", open("new.txt","rb").read() == b"hello\n", out)

rc, out = run(HP + ["apply", "e.txt"], "@@\n@1:zzzz\nq\n@@\n")
check("H8 malformed hash rejected", rc != 0 and "bad hunk header" in out, out)

rc, out = run(HP + ["apply", "e.txt"], f"@@\n@{anchor('e.txt',1)}-{anchor('e.txt',3)}\nA\n@@\n@{anchor('e.txt',2)}-{anchor('e.txt',4)}\nB\n@@\n")
check("H9 overlapping replaces rejected", rc == 1 and "overlapping" in out, out)

# --- rerun
open("t.py", "w").write(
    "import os,time,sys\n"
    "print('run at 2026-09-09T10:00:'+str(int(time.time())%60).zfill(2)+' in /tmp/pytest-of-jp/pytest-'+str(int(time.time()))+'/x')\n"
    "print('weird\\rline')\n"
    "print('FAIL' if os.path.exists('broken') else 'PASS'); print('done in %.3fs' % (time.time()%1))\n"
    "sys.exit(1 if os.path.exists('broken') else 0)\n")
run(RR + ["--forget", sys.executable, "t.py"])
rc1, o1 = run(RR + [sys.executable, "t.py"])
rc2, o2 = run(RR + [sys.executable, "t.py"])
check("R1 baseline exit code propagated (0)", rc1 == 0 and "baseline" in o1, o1)
check("R2 identical run suppressed despite ts/dur/tmp churn", "unchanged" in o2, o2)
check("R3 CR inside a line does not split it", "weirdline" in o1, o1)
open("broken", "w").close()
rc3, o3 = run(RR + [sys.executable, "t.py"])
check("R4 change shows minimal diff + exit transition", rc3 == 1 and "-PASS" in o3 and "+FAIL" in o3 and "(was exit 0)" in o3, o3)
os.remove("broken")
rc4, o4 = run(RR + [sys.executable, "t.py"])
check("R5 unchanged-but-different-exit is not suppressed", rc4 == 0 and "unchanged" not in o4, o4)
rc5, o5 = run(RR + ["echo shell && echo pipe | findstr pipe" if os.name == "nt" else "echo shell && echo pipe | grep pipe"])
check("R6 single quoted arg runs through shell", "pipe" in o5, o5)

# --- probe
rc, out = run(PR + ["py", "json:dumps"])
check("P1 function target prints signature", out.count("\n") <= 3 and "def dumps(obj" in out, out)
rc, out = run(PR + ["py", "collections:Counter"])
check("P2 class target lists methods", "def most_common" in out, out[:300])
open("m.mjs", "w").write("export const f = (a,b) => a; export class K { m(x){} }\n")
rc, out = run(PR + ["js", os.path.abspath("m.mjs")])
check("P3 ESM by absolute Windows path", "fn f(2" in out and "class K" in out, out)
rc, out = run(PR + ["py", "nonexistent_mod_xyz"])
check("P4 missing module reports cleanly (non-zero)", rc != 0 and "No module" in out, out[-200:])

print(f"\n{fails} failure(s)")
sys.exit(fails)
