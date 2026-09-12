---
name: probe
description: REQUIRED before reading a Python or JS module's source just to learn its API — what it exports, a function's parameters, or a class's methods. Runs the module and prints signatures instead of the whole file. Do not Read a module for this purpose first. Skip only for modules whose import has side effects (starts a server, touches disk/network, needs secrets) — use hashpatch outline on those instead.
---

# probe

Reading a 400-line module to learn six function signatures costs 400 lines. Importing it and asking the runtime costs six. `probe` does runtime introspection and prints one line per symbol: kind, name, signature, first doc line.

`PROBE="python $HOME/.claude/skills/probe/scripts/probe.py"`

Use `$HOME`, never `~`: PowerShell does not expand `~` inside quotes. `$HOME` expands in Bash and PowerShell alike.

- `$PROBE py package.module` - top-level exports of a Python module (respects `__all__`).
- `$PROBE py package.module:ClassName` - a class with its methods and properties.
- `$PROBE py module --deep` - expand every class's methods. `--all` includes private names.
- `$PROBE js ./src/utils.js` or `$PROBE js lodash` or `$PROBE js ./lib:Router` - Node exports with arity; classes list methods and statics.

Runs from the current directory, so local packages import as they would in the project. Works on installed dependencies too, which is the cheapest way to answer "what does this library's function actually take".

## Rules
1. Probe first, read second. Only open the source when you need the *body* of a specific function, and then use hashpatch `view` on that range.
2. Import side effects are real. Do not probe modules whose top level starts servers, mutates files, or needs secrets. Use hashpatch `outline` for those.
3. If import fails with a missing dependency, that is itself the answer to "is this set up". Report it rather than reading around it.
