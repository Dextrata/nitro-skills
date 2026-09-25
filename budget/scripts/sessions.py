#!/usr/bin/env python3
"""sessions: where the tokens of your real Claude Code sessions went. Executed, never read.

  sessions.py                      every transcript under ~/.claude/projects (>= 50 KB)
  sessions.py --projects DIR       another transcript root
  sessions.py --min 200            only sessions of at least 200 KB

Reads the JSONL transcripts Claude Code keeps per session and prints aggregates only:
real prompt/output tokens from the API usage records, what each prompt is made of, how much
of it is tool traffic older than N calls (the eviction lever), tool output by command kind,
hook deny-and-retry round trips, invocation boilerplate, and the exact replay of the two
hashpatch changes (lease views without per-line hashes, receipts instead of line echoes).
The README's "where the tokens go" numbers come from this script. Tokens are chars/4 except
where the API usage is quoted.
"""
import os, re, sys, json, glob, collections

T = lambda c: c // 4
HP_SUB = re.compile(r"(?:hp\.py\"?|\$\{?HP\}?|nitro\s+hp)\s+(view|outline|grep|apply)\b")
HP_LINE = re.compile(r"^(\d+):([0-9a-f]{4})\|", re.M)
PREFIX = re.compile(r"^\s*(?:cd\s+(?:\"[^\"]*\"|\S+)\s*(?:&&|;)\s*|\w+=(?:\"[^\"]*\"|'[^']*'|\S+)\s*[;&]*\s*|export\s+\w+=\S+\s*[;&]*\s*)+")
KINDS = [
    ("nitro other", r"\b(rr|fails|mine|shape|sdiff|rf|recall|budget|probe|scout|why|q|sessions)\.py\b|\bnitro\s+\w+"),
    ("cat/sed/head/tail", r"^(cat|sed|head|tail|type|Get-Content)\b"), ("rg/grep", r"^(rg|grep|egrep|findstr)\b|\|\s*(rg|grep)\b"),
    ("find/ls/tree/fd", r"^(find|ls|tree|fd|dir|Get-ChildItem)\b"), ("git diff/show/log/blame", r"^git\s+(diff|show|log|blame)\b"), ("git other", r"^git\b"),
    ("tests", r"pytest|npm\s+(run\s+)?test|jest|vitest|cargo\s+test|go\s+test|dotnet\s+test|unittest|mocha"),
    ("build/lint", r"npm\s+run\s+(build|lint)|\btsc\b|eslint|ruff|mypy|cargo\s+(build|check|clippy)|^make\b|go\s+build|dotnet\s+build"),
    ("python/node script", r"^(python3?|node|npx|uv|py)\b"), ("misc shell", r"^(echo|wc|for|while|if|printf|test|\[)\b"),
]
DENY = re.compile(r"PreToolUse:(Bash|PowerShell) hook error|is blocked|budget: .* is an unbounded flood|go through the (rerun|fails) skill")
SKILL_CALL = re.compile(r"(?:python3?\s+)?\"?\$?\{?(?:HOME|USERPROFILE)?\}?[^\s\"]*\.claude[/\\]skills[/\\](\w+)[/\\]scripts[/\\](\w+)\.py\"?")
VARDEF = re.compile(r"\b[A-Z]{1,8}=\"python\s+[^\"]*\.py\"\s*;?\s*")


def ctext(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c if isinstance(b, dict))
    return ""


def main(a):
    root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    min_kb = 50
    i = 0
    while i < len(a):
        if a[i] == "--projects":
            root = a[i + 1]; i += 2
        elif a[i] == "--min":
            min_kb = int(a[i + 1]); i += 2
        elif a[i] in ("-h", "--help"):
            print(__doc__); return 0
        else:
            i += 1
    files = [f for f in glob.glob(os.path.join(root, "*", "*.jsonl")) if os.path.getsize(f) >= min_kb * 1024]
    if not files:
        print(f"no transcripts of {min_kb} KB or more under {root}")
        return 1
    C = collections.Counter
    rows = []
    NITRO_ANY = re.compile(SKILL_CALL.pattern + r"|\bnitro\s+(hp|rr|fails|probe|rf|mine|shape|sdiff|q|scout|why|rc|budget|sessions)\b|nitro-skills[/\\]\w+[/\\]scripts")
    res_k, res_n = C(), C()
    hp_chars, hp_calls, hp_rep = C(), C(), C()
    cat_prompt, old = C(), {10: 0, 30: 0, 100: 0}
    real_prompt = out_tokens = recorded_out = fixed_sum = calls_total = 0
    denials = denial_chars = retry_chars = 0
    skill_calls = prefix_chars = vardef_chars = cd_chars = 0
    view_chars = view_prefix = apply_chars = apply_saved = 0
    for f in files:
        events = []
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
        tool_of, cmd_of, seen_ids, seen_hp = {}, {}, set(), set()
        s_v2 = 0   # this release's savings replayed inside this one session
        items, per_call, boundaries = [], [], set()
        call_idx, first_prompt, last_denied = 0, None, False
        for e in events:
            t = e.get("type")
            m = e.get("message") or {}
            content = m.get("content")
            if t == "summary" or e.get("isCompactSummary") or (t == "user" and isinstance(content, str) and content.startswith("This session is being continued")):
                boundaries.add(call_idx)
            if t == "assistant":
                mid = m.get("id") or e.get("uuid")
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    u = m.get("usage") or {}
                    ctx = int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
                    out_tokens += int(u.get("output_tokens") or 0)
                    call_idx += 1
                    if ctx:
                        per_call.append((call_idx, ctx))
                        if first_prompt is None:
                            first_prompt = ctx
                if isinstance(content, list):
                    for blk in content:
                        bt = blk.get("type")
                        if bt == "text":
                            items.append((call_idx, "assistant text", T(len(blk.get("text", "")))))
                            recorded_out += len(blk.get("text", ""))
                        elif bt == "tool_use":
                            inp = blk.get("input") or {}
                            items.append((call_idx, "tool inputs", T(len(json.dumps(inp)))))
                            recorded_out += len(json.dumps(inp))
                            tool_of[blk.get("id")] = blk.get("name")
                            if blk.get("name") in ("Bash", "PowerShell"):
                                cmd = inp.get("command", "") or ""
                                cmd_of[blk.get("id")] = cmd
                                if last_denied:
                                    retry_chars += len(cmd)
                                    s_v2 += T(len(cmd))
                                    last_denied = False
                                for mm in SKILL_CALL.finditer(cmd):
                                    skill_calls += 1
                                    prefix_chars += len(mm.group(0))
                                    s_v2 += T(len(mm.group(0)))
                                for mm in VARDEF.finditer(cmd):
                                    vardef_chars += len(mm.group(0))
                                    s_v2 += T(len(mm.group(0)))
                                mm = re.match(r"^\s*cd\s+(?:\"[^\"]*\"|\S+)\s*&&\s*", cmd)
                                if mm:
                                    cd_chars += len(mm.group(0))
            elif t == "user":
                if isinstance(content, str):
                    items.append((call_idx, "user text", T(len(content))))
                    continue
                if not isinstance(content, list):
                    continue
                for blk in content:
                    bt = blk.get("type")
                    if bt == "text":
                        items.append((call_idx, "user text", T(len(blk.get("text", "")))))
                    elif bt == "tool_result":
                        tid = blk.get("tool_use_id")
                        name = tool_of.get(tid)
                        txt = ctext(blk.get("content"))
                        n = len(txt)
                        items.append((call_idx, "tool results", T(n)))
                        if name not in ("Bash", "PowerShell"):
                            res_k["(" + str(name) + ")"] += n
                            res_n["(" + str(name) + ")"] += 1
                            continue
                        if DENY.search(txt) and n < 1500:
                            denials += 1
                            denial_chars += n
                            s_v2 += T(n)
                            last_denied = True
                            continue
                        cmd = cmd_of.get(tid, "")
                        subs = HP_SUB.findall(cmd)
                        if subs:
                            sub = subs[0] if len(set(subs)) == 1 else "mixed"
                            hp_chars[sub] += n
                            hp_calls[sub] += 1
                            for line in txt.split("\n"):
                                lm = HP_LINE.match(line)
                                if lm and lm.group(2) != "0000":
                                    key = (lm.group(1), lm.group(2))
                                    if key in seen_hp:
                                        hp_rep[sub] += len(line) + 1
                                    else:
                                        seen_hp.add(key)
                            if sub == "view":
                                view_chars += n
                                view_prefix += sum(len(x[1]) + 1 for x in HP_LINE.findall(txt))
                                s_v2 += T(sum(len(x[1]) + 1 for x in HP_LINE.findall(txt)))
                            elif sub == "apply":
                                apply_chars += n
                                receipt = len(txt.split("\n", 1)[0]) + 14 * max(1, txt.count("\n--"))
                                apply_saved += max(0, n - receipt)
                                s_v2 += T(max(0, n - receipt))
                            res_k["hashpatch"] += n
                            res_n["hashpatch"] += 1
                            continue
                        body = PREFIX.sub("", cmd, count=1).strip()
                        kind = "other"
                        for k, rx in KINDS:
                            if re.search(rx, body, re.I | re.M):
                                kind = k
                                break
                        res_k[kind] += n
                        res_n[kind] += 1
        if not per_call:
            continue
        items.sort(key=lambda x: x[0])
        ptr, live, bidx, last_b = 0, [], 0, 0
        bl = sorted(boundaries)
        shell = sum(1 for v in tool_of.values() if v in ("Bash", "PowerShell", "Read", "Edit", "MultiEdit", "Write", "Grep", "Glob"))
        nit = sum(1 for c in cmd_of.values() if NITRO_ANY.search(c))
        rows.append({"proj": os.path.basename(os.path.dirname(f)), "calls": len(per_call), "prompt": sum(x[1] for x in per_call),
                     "res": sum(t for _, c, t in items if c == "tool results"), "inp": sum(t for _, c, t in items if c == "tool inputs"),
                     "share": nit / shell if shell else 0.0, "shell": shell, "v2": s_v2})
        for ci, real in per_call:
            while ptr < len(items) and items[ptr][0] < ci:
                live.append(items[ptr])
                ptr += 1
            while bidx < len(bl) and bl[bidx] < ci:
                last_b = bl[bidx]
                bidx += 1
            if last_b:
                live = [x for x in live if x[0] >= last_b]
            calls_total += 1
            real_prompt += real
            fixed_sum += first_prompt or 0
            for added, cat, tok in live:
                cat_prompt[cat] += tok
                if cat in ("tool results", "tool inputs"):
                    for N in old:
                        if ci - added > N:
                            old[N] += tok
    tot = sum(res_k.values())
    print(f"sessions {len(files)} (>= {min_kb} KB), api calls {calls_total:,}, prompt tokens {real_prompt / 1e9:.2f}B "
          f"(avg {real_prompt // max(calls_total, 1):,} per call), output tokens {out_tokens / 1e6:.1f}M "
          f"of which not in the transcript (reasoning) {max(0, out_tokens - T(recorded_out)) * 100 // max(out_tokens, 1)}%")
    print()
    print("what a prompt is made of (share of all prompt tokens; the rest is harness-injected text not in transcripts)")
    print(f"  fixed per call (system prompt, tools, CLAUDE.md, skills) {fixed_sum * 100 // max(real_prompt, 1):>3}%")
    for cat, tok in cat_prompt.most_common():
        print(f"  {cat:<16}{tok * 100 // max(real_prompt, 1):>3}%")
    for N, tok in old.items():
        print(f"  tool traffic older than {N:>3} calls, still re-sent: {tok * 100 // max(real_prompt, 1)}%   (the eviction lever; no skill can pull it)")
    print()
    print("tool output entering context, by kind (tokens = chars/4)")
    for k, ch in res_k.most_common(12):
        print(f"  {k:<26}{res_n[k]:>7,} calls {T(ch):>11,} tokens {T(ch) * 100 // max(T(tot), 1):>3}%  avg {T(ch) // max(res_n[k], 1):>5,}")
    print()
    print("hashpatch (repeat = lines already shown this session, blank lines excluded)")
    for sub, ch in hp_chars.most_common():
        print(f"  {sub:<8}{hp_calls[sub]:>7,} calls {T(ch):>10,} tokens  avg {T(ch) // max(hp_calls[sub], 1):>5,}  repeat {hp_rep[sub] * 100 // max(ch, 1)}%")
    print(f"  replay: lease views drop per-line hashes = {T(view_prefix):,} tokens ({view_prefix * 100 // max(view_chars, 1)}% of view output); "
          f"receipts instead of apply echoes = {T(apply_saved):,} tokens ({apply_saved * 100 // max(apply_chars, 1)}% of apply output)")
    print()
    print(f"hook denials {denials:,}: {T(denial_chars):,} tokens of denial text + {T(retry_chars):,} output tokens of retried commands "
          f"(avg round trip {T(denial_chars + retry_chars) // max(denials, 1)})")
    print(f"invocation boilerplate typed by the model: skill paths {T(prefix_chars):,} ({skill_calls:,} calls), VAR=\"python ...\" {T(vardef_chars):,}, "
          f"'cd DIR &&' {T(cd_chars):,} tokens")
    print()
    print("sessions that used nitro vs sessions that did not (>= 20 calls, >= 10 file/shell tool calls, this repo's own sessions excluded)")
    ok = [r for r in rows if r["calls"] >= 20 and r["shell"] >= 10 and "nitro-skills" not in r["proj"]]
    b0 = [r for r in ok if r["share"] == 0]
    b1 = [r for r in ok if r["share"] >= 0.5]
    if b0 and b1:
        pc = lambda b, k: sum(r[k] for r in b) / max(sum(r["calls"] for r in b), 1)
        for label, k in (("tool-result tokens admitted per call", "res"), ("tool-input tokens written per call", "inp")):
            print(f"  {label:<38}{pc(b0, k):>8,.0f} -> {pc(b1, k):>7,.0f}   ({(1 - pc(b1, k) / pc(b0, k)) * 100:.0f}% fewer)   [{len(b0)} vs {len(b1)} sessions]")
        t0, t1 = pc(b0, "res") + pc(b0, "inp"), pc(b1, "res") + pc(b1, "inp")
        v1 = 1 - t1 / t0
        v2t = sum(r["v2"] for r in b1) / max(sum(r["res"] + r["inp"] for r in b1), 1)
        print(f"  {'tool traffic per call':<38}{t0:>8,.0f} -> {t1:>7,.0f}   ({v1 * 100:.0f}% fewer)")
        print(f"  this release replayed on the nitro sessions: a further {v2t * 100:.0f}% of their tool traffic")
        both = 1 - (1 - v1) * (1 - v2t)
        share = (cat_prompt["tool results"] + cat_prompt["tool inputs"]) / max(real_prompt, 1)
        print(f"  => {both * 100:.0f}% of tool traffic, which is {share * 100:.0f}% of a prompt: about {both * share * 100:.0f}% of all prompt tokens (the README headline)")
    else:
        print("  not enough sessions in both buckets to compare")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
