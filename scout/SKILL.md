---
name: scout
description: REQUIRED at the start of work in a repo you have not oriented in this session, and whenever you would otherwise read package.json, pyproject.toml, Cargo.toml, go.mod, Makefile, Dockerfile, CI config or the README "to see what this project is". One call prints the stack, the test/build/lint/run commands, entry points, the top-level layout with sizes, CI, tooling, docs and the biggest files. Do not cat manifests or ls around first; scout, then open only what it names.
---

# scout

The first ten minutes in a repo are spent reading manifests, listing directories and skimming the README to answer "what is this and how do I run its tests". Those reads are 2,000-5,000 tokens and the answer is 20 lines. `scout` reads the manifests and prints the answer.

`nitro scout` is the short form; the nitro hook expands `nitro scout` to `python $HOME/.claude/skills/scout/scripts/scout.py`. Without the hook installed, type that path (`$HOME`, never `~`: PowerShell does not expand `~` inside quotes).

- `nitro scout` - the current repo. `nitro scout path/to/dir` - another tree (a monorepo package, for instance).
- `nitro scout --dirs 25` - more top-level directories in the layout. `nitro scout --json` - the same facts as JSON.

Output:
```
repo    acme   git main @9f3c1ab (412 commits, clean, last 2026-03-02)   1,284 files, 96,410 lines
langs   python 61,200 lines / 410 files · typescript 30,100 / 220   (+ markdown 40, yaml 12, json 9)
node    package.json acme-web v0.3.1 (pnpm); scripts: dev, build, test, lint; deps 12 (+9 dev); react, vite, typescript, vitest, eslint
python  pyproject.toml acme v1.2.0 python>=3.11 [hatchling]; deps 14 (+6 dev); tools: mypy, pytest, ruff
tasks   make: test, lint, build, migrate
run     test: pnpm run test  |  build: pnpm run build  |  lint: pnpm run lint  |  test (py): pytest -q  |  typecheck: mypy .  |  install: uv sync
entry   console_scripts acme=acme.cli:main, src/app.py, src/cli.py, web/src/index.ts
layout  src/                    410 files   61,200 lines  400 py 10 sql        api, db, jobs, models, cli (+3)
        web/                    220 files   30,100 lines  200 ts 20 tsx        src, public
        tests/                  120 files    9,800 lines  120 py               unit, integration
docker  Dockerfile FROM python:3.12-slim; docker-compose.yml services: api, db, redis
ci      ci.yml "CI" on push,pull_request; jobs test, lint, e2e
tools   tsconfig.json, vitest.config.ts, eslint.config.js, .pre-commit-config.yaml, .env.example
docs    README.md (310 lines: Install, Usage, Architecture, Deploy)  CONTRIBUTING.md (80 lines)  docs/ (24 files)
big     src/db/models.py 2,140 · src/api/routes.py 1,880 · web/src/App.tsx 1,200
[scout: 1,284 files, 96,410 lines, 6 languages; hashpatch outline/probe for any file named here]
```

## Rules
1. Scout once per repo per session, before any manifest read. If a `nitro rc ask` about the project already answers you, skip it.
2. The `run` line is inferred from scripts, Makefile targets and tool configs. Use those commands through `nitro fails` (tests, lint, typecheck) or `nitro rr` (build).
3. Everything named in the output is a pointer: `nitro hp outline` for a big file, `nitro probe` for a module's API, `nitro q` for symbols. Do not follow up with `cat`.
4. Counts skip gitignored paths (fd) and stop counting lines above 6,000 files; the tag says so when that happens.
