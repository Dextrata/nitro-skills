"""Cases for hooks/enforce-nitro-bash.py: python tests_hook.py"""
import json, os, subprocess, sys, tempfile
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hooks", "enforce-nitro-bash.py")
d = tempfile.mkdtemp()
open(os.path.join(d, "big.js"), "w").write("x\n" * 200)
open(os.path.join(d, "s.txt"), "w").write("y\n" * 5)

def hook(cmd):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps({"tool_name": "Bash", "cwd": d, "tool_input": {"command": cmd}}),
                       capture_output=True, text=True)
    return ("DENY " + json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"][:70]) if p.stdout else "allow"

CASES = [
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
]
bad = 0
for c, exp in CASES:
    r = hook(c)
    ok = r.startswith("DENY") == (exp == "deny")
    bad += not ok
    print(("PASS " if ok else "FAIL ") + repr(c[:45]) + " -> " + r)
print("failures:", bad)
sys.exit(1 if bad else 0)
