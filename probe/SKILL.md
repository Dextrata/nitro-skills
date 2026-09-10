---
name: probe
description: Learn a Python or JS module's API by executing it instead of reading its source. Use before reading any module just to find out what it exports, what a function's parameters are, or what methods a class has.
---

# probe

Reading a 400-line module to learn six function signatures costs 400 lines. Importing it and asking the runtime costs six. `probe` does runtime introspection and prints one line per symbol: kind, name, signature, first doc line.

`PROBE="python ~/.claude/skills/probe/scripts/probe.py"`

- `$PROBE py package.module` - top-level exports of a Python module (respects `__all__`).
- `$PROBE py package.module:ClassName` - a class with its methods and properties.
- `$PROBE py module --deep` - expand every class's methods. `--all` includes private names.
- `$PROBE js ./src/utils.js` or `$PROBE js lodash` or `$PROBE js ./lib:Router` - Node exports with arity; classes list methods and statics.

Runs from the current directory, so local packages import as they would in the project. Works on installed dependencies too, which is the cheapest way to answer "what does this library's function actually take".

## Rules
1. Probe first, read second. Only open the source when you need the *body* of a specific function, and then use hashpatch `view` on that range.
2. Import side effects are real. Do not probe modules whose top level starts servers, mutates files, or needs secrets. Use hashpatch `outline` for those.
3. If import fails with a missing dependency, that is itself the answer to "is this set up". Report it rather than reading around it.
