#!/usr/bin/env python3
"""probe: learn a module's API by executing it, not reading it. Executed, never read.

  probe.py py  MODULE[:name]      python: import and introspect (signatures + 1-line docs)
  probe.py js  PATH_OR_PKG[:name] node: require()/import and list exports with arity
  probe.py py  MODULE --all       include private (_x) members
  probe.py py  MODULE --deep      also expand classes' methods (default: top-level only)

Output is one line per symbol:  kind name(signature)  # first doc line
Runtime introspection sees re-exports, decorators, generated members, and
C-extension signatures that reading source would miss, at ~5% of the tokens.
"""
import sys, os, subprocess, inspect, importlib

def first_doc(o):
    d = inspect.getdoc(o)
    return ("  # " + d.strip().splitlines()[0][:100]) if d else ""

def sig(o):
    try: return str(inspect.signature(o))
    except (ValueError, TypeError): return "(...)"

def py(target, show_all=False, deep=False):
    sys.path.insert(0, os.getcwd())
    mod_name, _, attr = target.partition(":")
    mod = importlib.import_module(mod_name)
    root = getattr(mod, attr) if attr else mod
    print(f"# {target}  ({getattr(mod, '__file__', 'builtin')})")
    if attr and callable(root) and not inspect.isclass(root):
        print(f"def {attr}{sig(root)}{first_doc(root)}"); return
    if inspect.isclass(root) or attr:
        deep = True
    names = getattr(root, "__all__", None) or [n for n in dir(root) if show_all or not n.startswith("_")]
    for n in names:
        try: o = getattr(root, n)
        except Exception: continue
        if inspect.ismodule(o): continue
        if inspect.isclass(o):
            bases = ",".join(b.__name__ for b in o.__bases__ if b is not object)
            print(f"class {n}{'(' + bases + ')' if bases else ''}{sig(o)}{first_doc(o)}")
            if deep:
                for mn, m in inspect.getmembers(o):
                    if (show_all or not mn.startswith("_") or mn in ("__init__", "__call__")) and callable(m) and mn in vars(o):
                        print(f"  def {mn}{sig(m)}{first_doc(m)}")
                for pn, p in vars(o).items():
                    if isinstance(p, property) and (show_all or not pn.startswith("_")):
                        print(f"  prop {pn}{first_doc(p)}")
        elif callable(o):
            print(f"def {n}{sig(o)}{first_doc(o)}")
        else:
            r = repr(o)
            print(f"{type(o).__name__} {n} = {r[:60] + ('...' if len(r) > 60 else '')}")

JS = r"""
const target = process.argv[1];
// split on the LAST colon only when what follows is a bare identifier (so C:\path survives)
const mm = target.match(/^(.*):([A-Za-z_$][\w$]*)$/);
const [spec, attr] = mm && !/^[A-Za-z]$/.test(mm[1]) ? [mm[1], mm[2]] : [target, undefined];
const path = require('path');
(async () => {
  let m;
  const p = spec.startsWith('.') || path.isAbsolute(spec) ? path.resolve(spec) : spec;
  const local = spec.startsWith('.') || path.isAbsolute(spec);
  try { m = require(p); } catch (e) { m = await import(local ? require('url').pathToFileURL(p).href : p); }
  if (attr) m = m[attr];
  console.log('# ' + target);
  const describe = (name, v, indent = '') => {
    if (typeof v === 'function') {
      const isClass = /^class\s/.test(Function.prototype.toString.call(v));
      console.log(`${indent}${isClass ? 'class' : 'fn'} ${name}(${v.length} arg${v.length === 1 ? '' : 's'})`);
      if (isClass || attr) for (const mn of Object.getOwnPropertyNames(v.prototype || {})) {
        if (mn === 'constructor') continue;
        const d = Object.getOwnPropertyDescriptor(v.prototype, mn);
        if (typeof d.value === 'function') console.log(`${indent}  method ${mn}(${d.value.length})`);
        else if (d.get || d.set) console.log(`${indent}  prop ${mn}`);
      }
      for (const sn of Object.getOwnPropertyNames(v)) if (!['length','name','prototype'].includes(sn) && typeof v[sn] === 'function') console.log(`${indent}  static ${sn}(${v[sn].length})`);
    } else if (v && typeof v === 'object') {
      const keys = Object.keys(v);
      console.log(`${indent}obj ${name} {${keys.slice(0, 12).join(', ')}${keys.length > 12 ? ', ...' : ''}}`);
    } else {
      const r = JSON.stringify(v); console.log(`${indent}${typeof v} ${name} = ${r && r.length > 60 ? r.slice(0, 60) + '...' : r}`);
    }
  };
  if (typeof m === 'function' || Array.isArray(m) || m === null || typeof m !== 'object') describe(attr || 'default', m);
  else for (const k of Object.keys(m).sort()) describe(k, m[k]);
})().catch(e => { console.error('probe failed: ' + e.message); process.exit(1); });
"""

def js(target):
    subprocess.run(["node", "-e", JS, target], check=False)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if len(a) < 2: sys.exit(__doc__)
    if a[0] == "py": py(a[1], "--all" in a, "--deep" in a)
    elif a[0] == "js": js(a[1])
    else: sys.exit(__doc__)
