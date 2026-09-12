#!/usr/bin/env python3
"""budget: per-command token ledger and output-size predictor. Executed, never read.

  budget.py report [N]        top N commands by tokens spent this workspace (default 20)
  budget.py predict "CMD"     predicted output lines for CMD from history
  budget.py reset             clear history for this workspace

History is written by hooks/budget-record.py (PostToolUse) and consulted by
hooks/budget-guard.py (PreToolUse), which denies a command predicted to exceed
the line cap unless it is routed through a shaping skill.
"""
import sys, os, re, json, hashlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def hist_path(cwd=None):
    cwd = cwd or os.getcwd()
    d = os.path.join(os.path.expanduser("~"), ".cache", "nitro", "budget")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return os.path.join(d, hashlib.md5(os.path.normcase(os.path.abspath(cwd)).lower().encode()).hexdigest()[:8] + ".json")


def norm(cmd):
    """Command shape: strip paths/numbers/quotes so similar commands share history."""
    c = cmd.strip()
    c = re.sub(r"#nitro-skip\s*$", "", c)
    c = re.sub(r"\"[^\"]*\"|'[^']*'", "'…'", c)
    c = re.sub(r"\b\d+\b", "N", c)
    c = re.sub(r"(?:[\w.-]+[\\/])+[\w.-]+", "PATH", c)
    return c[:200]


def load(cwd=None):
    try:
        return json.load(open(hist_path(cwd), encoding="utf-8"))
    except Exception:
        return {}


def save(h, cwd=None):
    json.dump(h, open(hist_path(cwd), "w", encoding="utf-8"))


def record(cmd, lines, chars, cwd=None):
    h = load(cwd)
    e = h.setdefault(norm(cmd), {"n": 0, "lines": [], "chars": 0, "last": ""})
    e["n"] += 1
    e["lines"] = (e["lines"] + [lines])[-8:]
    e["chars"] += chars
    e["last"] = cmd[:160]
    save(h, cwd)


def predict(cmd, cwd=None):
    h = load(cwd)
    e = h.get(norm(cmd))
    if e and e["lines"]:
        return max(e["lines"]), "history"
    return None, "unknown"


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if a[0] == "reset":
        save({})
        print("[budget: reset]")
        return 0
    if a[0] == "predict":
        n, why = predict(" ".join(a[1:]))
        print(f"{n if n is not None else '?'} lines ({why})")
        return 0
    if a[0] == "report":
        top = int(a[1]) if len(a) > 1 else 20
        h = load()
        rows = sorted(h.items(), key=lambda kv: -kv[1]["chars"])
        total = sum(e["chars"] for _, e in rows)
        print(f"{'tokens':>8} {'runs':>4} {'max ln':>6}  command")
        for k, e in rows[:top]:
            print(f"{e['chars'] // 4:>8} {e['n']:>4} {max(e['lines']) if e['lines'] else 0:>6}  {e['last'][:90]}")
        print(f"[budget: ~{total // 4} tokens of command output over {sum(e['n'] for _, e in rows)} runs]")
        return 0
    print(f"unknown command {a[0]}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
