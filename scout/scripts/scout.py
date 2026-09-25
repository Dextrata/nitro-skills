#!/usr/bin/env python3
"""scout: one-screen orientation in a repo. Executed, never read.

  scout.py [DIR]        stack, commands, entry points, layout, CI, docs, biggest files:
                        the six to ten reads an agent does at the start of a session, in one call
  scout.py --dirs N     show N top-level directories (default 14)
  scout.py --json       the same facts as JSON

Reads the manifests (package.json, pyproject.toml, setup.cfg, requirements*.txt, Cargo.toml,
go.mod, pom.xml, build.gradle*, *.csproj, Gemfile, composer.json, mix.exs, pubspec.yaml,
Makefile, justfile, Dockerfile, docker-compose*.yml, CI workflows, tool configs) and prints
what they say instead of their contents. Files come from fd when installed (gitignore-aware),
os.walk otherwise. Nothing is written.
"""
import sys, os, re, json, subprocess, shutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".cache", "target", ".next", "coverage",
             ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "vendor", ".idea", ".vscode", "bin", "obj", ".terraform", ".gradle"}
LANG = {".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".rb": "ruby",
        ".cs": "csharp", ".php": "php", ".swift": "swift", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp",
        ".scala": "scala", ".ex": "elixir", ".exs": "elixir", ".dart": "dart", ".lua": "lua", ".sh": "shell", ".bash": "shell",
        ".ps1": "powershell", ".sql": "sql", ".html": "html", ".css": "css", ".scss": "css", ".vue": "vue", ".svelte": "svelte",
        ".md": "markdown", ".rst": "markdown", ".yml": "yaml", ".yaml": "yaml", ".json": "json", ".toml": "toml", ".xml": "xml",
        ".tf": "terraform", ".proto": "proto", ".graphql": "graphql", ".ipynb": "notebook"}
DOCS_RX = re.compile(r"^(README|CLAUDE|AGENTS|CONTRIBUTING|CHANGELOG|ARCHITECTURE|DESIGN|TODO|SECURITY|HACKING|DEVELOPMENT|GEMINI)(\.\w+)?$", re.I)
TOOLS = ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", ".pre-commit-config.yaml",
         ".editorconfig", ".env.example", ".env.sample", ".tool-versions", ".nvmrc", ".python-version", ".ruby-version", "Procfile",
         "Vagrantfile", "Taskfile.yml", "CMakeLists.txt", "tsconfig.json", "jest.config.js", "jest.config.ts", "jest.config.mjs",
         "vitest.config.ts", "vitest.config.js", "vitest.config.mts", ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.cjs",
         "eslint.config.js", "eslint.config.mjs", "eslint.config.ts", ".prettierrc", ".prettierrc.json", "prettier.config.js",
         "pytest.ini", "tox.ini", "setup.cfg", "ruff.toml", ".ruff.toml", "mypy.ini", ".flake8", "pyrightconfig.json", "noxfile.py",
         "conftest.py", "webpack.config.js", "vite.config.ts", "vite.config.js", "next.config.js", "next.config.mjs", "next.config.ts",
         "nuxt.config.ts", "svelte.config.js", "angular.json", "babel.config.js", ".babelrc", "rollup.config.js", "turbo.json",
         "nx.json", "lerna.json", "pnpm-workspace.yaml", ".github/dependabot.yml", "renovate.json", "sonar-project.properties",
         "Jenkinsfile", ".gitlab-ci.yml", ".circleci/config.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml", ".travis.yml",
         "netlify.toml", "vercel.json", "fly.toml", "app.yaml", "serverless.yml", "manage.py", "alembic.ini", "Brewfile", "flake.nix",
         "shell.nix", "devbox.json", ".devcontainer/devcontainer.json", "MANIFEST.in", "codecov.yml", ".codecov.yml"]
FD = next((shutil.which(x) for x in ("fd", "fdfind") if shutil.which(x)), None)
MAX_COUNT = 6000


def list_files(root):
    if FD and os.environ.get("NITRO_NO_FD") != "1":
        args = [FD, "--type", "f", "--color", "never", "--strip-cwd-prefix", "--hidden", "-E", ".git"]
        for d in sorted(SKIP_DIRS):
            args += ["-E", d]
        try:
            p = subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if p.returncode == 0:
                return sorted(l.strip().replace("\\", "/").removeprefix("./") for l in p.stdout.splitlines() if l.strip())
        except OSError:
            pass
    out = []
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and (not x.startswith(".") or x in (".github", ".gitlab", ".circleci", ".devcontainer"))]
        for f in fs:
            out.append(os.path.relpath(os.path.join(d, f), root).replace("\\", "/"))
    return sorted(out)


def read(root, rel, limit=400_000):
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def count_lines(root, rel):
    try:
        with open(os.path.join(root, rel), "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def toml_load(text):
    try:
        import tomllib
        return tomllib.loads(text)
    except Exception:
        pass
    # minimal fallback: [section] headers with key = "value" pairs and key = [ ... ] arrays counted
    return _toml_min(text)


def _toml_min(text):
    data, cur = {}, None
    for l in text.splitlines():
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^\[+\s*([\w.\-\"]+)\s*\]+$", s)
        if m:
            cur = data
            for part in m.group(1).replace('"', "").split("."):
                cur = cur.setdefault(part, {}) if isinstance(cur.get(part, {}), dict) else cur
            continue
        m = re.match(r"^([\w\-]+)\s*=\s*(.*)$", s)
        if m and cur is not None:
            v = m.group(2).strip()
            cur[m.group(1)] = v.strip('"\'') if not v.startswith("[") else [x for x in re.findall(r'"([^"]*)"', v)]
    return data


def git_info(root):
    def g(*a):
        try:
            p = subprocess.run(["git"] + list(a), cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
            return p.stdout.strip() if p.returncode == 0 else None
        except OSError:
            return None
    if g("rev-parse", "--is-inside-work-tree") != "true":
        return None
    branch = g("rev-parse", "--abbrev-ref", "HEAD") or "?"
    sha = g("rev-parse", "--short", "HEAD") or "?"
    n = g("rev-list", "--count", "HEAD") or "?"
    dirty = g("status", "--porcelain")
    last = g("log", "-1", "--format=%ad", "--date=short") or ""
    return {"branch": branch, "sha": sha, "commits": n, "dirty": len(dirty.splitlines()) if dirty else 0, "last": last}


def pkg_json(root, files):
    if "package.json" not in files:
        return None
    try:
        d = json.loads(read(root, "package.json"))
    except ValueError:
        return {"name": "package.json (unparseable)"}
    deps, dev = d.get("dependencies", {}) or {}, d.get("devDependencies", {}) or {}
    fw = [k for k in ("next", "react", "vue", "svelte", "angular", "@angular/core", "express", "fastify", "koa", "nest", "@nestjs/core",
                      "electron", "vite", "typescript", "jest", "vitest", "mocha", "playwright", "@playwright/test", "cypress", "eslint",
                      "prettier", "tailwindcss", "prisma", "@prisma/client", "drizzle-orm", "webpack") if k in deps or k in dev]
    pm = "pnpm" if "pnpm-lock.yaml" in files else "yarn" if "yarn.lock" in files else "bun" if "bun.lockb" in files or "bun.lock" in files else "npm"
    pm = (d.get("packageManager") or pm).split("@")[0]
    return {"name": d.get("name"), "version": d.get("version"), "scripts": d.get("scripts", {}) or {}, "deps": len(deps), "dev": len(dev),
            "frameworks": fw, "pm": pm, "main": d.get("main"), "bin": d.get("bin"), "type": d.get("type"), "workspaces": bool(d.get("workspaces"))}


def pyproject(root, files):
    out = {}
    if "pyproject.toml" in files:
        d = toml_load(read(root, "pyproject.toml"))
        proj = d.get("project", {}) or {}
        poetry = (d.get("tool", {}) or {}).get("poetry", {}) or {}
        out["name"] = proj.get("name") or poetry.get("name")
        out["version"] = proj.get("version") or poetry.get("version")
        out["requires"] = proj.get("requires-python") or (poetry.get("dependencies", {}) or {}).get("python")
        deps = proj.get("dependencies") or list((poetry.get("dependencies") or {}).keys())
        out["deps"] = len(deps) if isinstance(deps, list) else 0
        opt = proj.get("optional-dependencies", {}) or {}
        grp = poetry.get("group", {}) or {}
        out["dev"] = sum(len(v) for v in opt.values() if isinstance(v, list)) + sum(len((g.get("dependencies") or {})) for g in grp.values() if isinstance(g, dict))
        out["scripts"] = proj.get("scripts", {}) or poetry.get("scripts", {}) or {}
        out["tools"] = sorted(k for k in (d.get("tool", {}) or {}).keys() if k not in ("poetry",))
        build = (d.get("build-system", {}) or {}).get("build-backend", "")
        out["build"] = build.split(".")[0] if build else ("poetry" if poetry else "")
    for f in ("setup.py", "setup.cfg", "requirements.txt", "requirements-dev.txt", "requirements/dev.txt", "Pipfile", "environment.yml", "uv.lock", "poetry.lock", "pdm.lock"):
        if f in files:
            out.setdefault("files", []).append(f)
    reqs = [f for f in files if re.match(r"^requirements[\w.-]*\.txt$", f)]
    if reqs and "deps" not in out:
        out["deps"] = sum(1 for f in reqs for l in read(root, f).splitlines() if l.strip() and not l.startswith(("#", "-")))
    return out or None


def cargo(root, files):
    if "Cargo.toml" not in files:
        return None
    d = toml_load(read(root, "Cargo.toml"))
    pkg = d.get("package", {}) or {}
    ws = (d.get("workspace", {}) or {}).get("members")
    bins = [b.get("name") for b in d.get("bin", []) if isinstance(b, dict)]
    return {"name": pkg.get("name"), "version": pkg.get("version"), "edition": pkg.get("edition"), "deps": len(d.get("dependencies", {}) or {}),
            "dev": len(d.get("dev-dependencies", {}) or {}), "bins": bins, "workspace": ws}


def gomod(root, files):
    if "go.mod" not in files:
        return None
    t = read(root, "go.mod")
    m = re.search(r"^module\s+(\S+)", t, re.M)
    v = re.search(r"^go\s+(\S+)", t, re.M)
    return {"module": m.group(1) if m else None, "go": v.group(1) if v else None,
            "deps": len([l for l in t.splitlines() if re.match(r"^\s+\S+ v\S+", l) and "// indirect" not in l])}


def jvm(root, files):
    out = {}
    if "pom.xml" in files:
        t = read(root, "pom.xml")
        m = re.search(r"<artifactId>([^<]+)</artifactId>", t)
        out["maven"] = m.group(1) if m else "pom.xml"
    g = [f for f in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts") if f in files]
    if g:
        out["gradle"] = ", ".join(g)
    return out or None


def dotnet(root, files):
    proj = [f for f in files if f.endswith((".csproj", ".fsproj", ".vbproj")) and f.count("/") <= 2]
    sln = [f for f in files if f.endswith(".sln") and "/" not in f]
    if not proj and not sln:
        return None
    tf = None
    for p in proj[:3]:
        m = re.search(r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>", read(root, p))
        if m:
            tf = m.group(1)
            break
    return {"sln": sln, "projects": proj, "tfm": tf}


def other_manifests(root, files):
    out = []
    for f, label in (("Gemfile", "ruby"), ("composer.json", "php"), ("mix.exs", "elixir"), ("pubspec.yaml", "dart"), ("Package.swift", "swift"),
                     ("build.sbt", "scala"), ("CMakeLists.txt", "cmake"), ("meson.build", "meson"), ("Makefile.PL", "perl"), ("deno.json", "deno"),
                     ("shard.yml", "crystal"), ("rebar.config", "erlang"), ("stack.yaml", "haskell"), ("cabal.project", "haskell")):
        if f in files:
            out.append(f"{label} ({f})")
    return out


def make_targets(root, files):
    out = {}
    for f in ("Makefile", "makefile", "GNUmakefile"):
        if f in files:
            t = [m.group(1) for m in re.finditer(r"^([A-Za-z0-9_.\-/]+)\s*:(?!=)", read(root, f), re.M) if not m.group(1).startswith(".")]
            out["make"] = list(dict.fromkeys(t))
            break
    for f in ("justfile", "Justfile", ".justfile"):
        if f in files:
            out["just"] = [m.group(1) for m in re.finditer(r"^([A-Za-z0-9_\-]+)(?:\s+[\w\s=\"']*)?:(?!=)", read(root, f), re.M)]
            break
    if "Taskfile.yml" in files or "Taskfile.yaml" in files:
        t = read(root, "Taskfile.yml" if "Taskfile.yml" in files else "Taskfile.yaml")
        m = re.search(r"^tasks:\s*$(.*)", t, re.M | re.S)
        out["task"] = re.findall(r"^  ([\w:\-]+):", m.group(1), re.M) if m else []
    return out


def docker(root, files):
    out = {}
    dfs = [f for f in files if os.path.basename(f).startswith("Dockerfile") and f.count("/") <= 1]
    if dfs:
        froms = []
        for f in dfs[:3]:
            froms += [m.group(1) for m in re.finditer(r"^FROM\s+(?:--platform=\S+\s+)?(\S+)", read(root, f), re.M | re.I)]
        out["dockerfiles"] = dfs
        out["from"] = list(dict.fromkeys(froms))[:4]
    comp = [f for f in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml") if f in files]
    if comp:
        t = read(root, comp[0])
        m = re.search(r"^services:\s*$(.*?)(?=^\S|\Z)", t, re.M | re.S)
        out["compose"] = comp[0]
        out["services"] = re.findall(r"^  ([\w.\-]+):\s*$", m.group(1), re.M) if m else []
    return out or None


def ci(root, files):
    out = []
    for f in sorted(x for x in files if x.startswith(".github/workflows/") and x.endswith((".yml", ".yaml"))):
        t = read(root, f)
        name = re.search(r"^name:\s*(.+)$", t, re.M)
        on = re.search(r"^on:\s*(.*)$", t, re.M)
        trig = []
        if on and on.group(1).strip():
            trig = [x.strip(" []") for x in on.group(1).split(",")]
        else:
            m = re.search(r"^on:\s*$(.*?)(?=^\S)", t, re.M | re.S)
            trig = re.findall(r"^  ([\w_]+):", m.group(1), re.M) if m else []
        jobs = re.search(r"^jobs:\s*$(.*)", t, re.M | re.S)
        jn = re.findall(r"^  ([\w\-]+):\s*$", jobs.group(1), re.M) if jobs else []
        out.append(f"{f.split('/')[-1]}" + (f" \"{name.group(1).strip()}\"" if name else "") + (f" on {','.join(trig[:4])}" if trig else "") + (f"; jobs {', '.join(jn[:5])}" if jn else ""))
    for f, label in ((".gitlab-ci.yml", "gitlab"), ("Jenkinsfile", "jenkins"), (".circleci/config.yml", "circleci"), ("azure-pipelines.yml", "azure"),
                     ("bitbucket-pipelines.yml", "bitbucket"), (".travis.yml", "travis"), ("cloudbuild.yaml", "gcp cloud build"), ("buildspec.yml", "aws codebuild")):
        if f in files:
            out.append(f"{label} ({f})")
    return out


def commands(pj, py, cg, go, dn, mk, files, root):
    c = {}
    scripts = (pj or {}).get("scripts", {}) or {}
    pm = (pj or {}).get("pm", "npm")
    runner = f"{pm} run" if pm != "npm" else "npm run"
    for key, names in (("test", ("test", "test:unit", "unit")), ("build", ("build", "compile")), ("lint", ("lint", "check", "typecheck", "lint:fix")),
                       ("dev", ("dev", "start", "serve", "watch")), ("format", ("format", "fmt", "prettier"))):
        for n in names:
            if n in scripts:
                c[key] = f"{runner} {n}" if n not in ("test", "start") or pm != "npm" else f"npm {n}"
                break
    targets = mk.get("make", [])
    for key, names in (("test", ("test", "tests", "check")), ("build", ("build", "all")), ("lint", ("lint", "check", "fmt-check")), ("dev", ("run", "dev", "serve", "start")), ("format", ("fmt", "format"))):
        if key not in c:
            for n in names:
                if n in targets:
                    c[key] = f"make {n}"
                    break
    for n in mk.get("just", []):
        for key in ("test", "build", "lint", "dev", "format"):
            if key not in c and n in (key, "run" if key == "dev" else key, "fmt" if key == "format" else key):
                c[key] = f"just {n}"
    if py:
        tools = set(py.get("tools", []))
        pyfiles = set(py.get("files", []))
        tk = "test" if "test" not in c else "test (py)"
        if "pytest" in tools or "pytest.ini" in files or "conftest.py" in files or "tox.ini" in files or any(f.startswith(("tests/", "test/")) and f.endswith(".py") for f in files):
            c[tk] = "pytest -q"
        elif any(re.match(r"^(tests?|test_\w+|\w+_tests?)\.py$", f) for f in files):
            c[tk] = "python " + next(f for f in sorted(files) if re.match(r"^(tests?|test_\w+|\w+_tests?)\.py$", f))
        elif any(re.match(r"^tests?/.*test.*\.py$", f) for f in files):
            c[tk] = "python -m unittest"
        if "lint" not in c:
            if "ruff" in tools or "ruff.toml" in files or ".ruff.toml" in files:
                c["lint"] = "ruff check ."
            elif ".flake8" in files or "flake8" in tools:
                c["lint"] = "flake8"
        if "typecheck" not in c and ("mypy" in tools or "mypy.ini" in files):
            c["typecheck"] = "mypy ."
        elif "typecheck" not in c and ("pyright" in tools or "pyrightconfig.json" in files):
            c["typecheck"] = "pyright"
        if "format" not in c and ("black" in tools or "ruff" in tools):
            c["format"] = "ruff format ." if "ruff" in tools else "black ."
        if "dev" not in c and "manage.py" in files:
            c["dev"] = "python manage.py runserver"
        if "build" not in c and py.get("build"):
            c["build"] = {"poetry": "poetry build", "hatchling": "hatch build", "setuptools": "python -m build", "flit_core": "flit build", "pdm": "pdm build"}.get(py["build"], "python -m build")
        if "install" not in c:
            c["install"] = "uv sync" if "uv.lock" in files else "poetry install" if "poetry.lock" in files else "pdm install" if "pdm.lock" in files else \
                ("pip install -r requirements.txt" if "requirements.txt" in files else "pip install -e ." if "pyproject.toml" in files or "setup.py" in files else None)
            if not c["install"]:
                del c["install"]
    if cg:
        c.setdefault("test", "cargo test")
        c.setdefault("build", "cargo build")
        c.setdefault("lint", "cargo clippy")
    if go:
        c.setdefault("test", "go test ./...")
        c.setdefault("build", "go build ./...")
        c.setdefault("lint", "go vet ./...")
    if dn:
        c.setdefault("test", "dotnet test")
        c.setdefault("build", "dotnet build")
    if pj and "install" not in c:
        c["install"] = f"{pm} install"
    if pj and "typecheck" not in c and "tsconfig.json" in files and "typescript" in pj.get("frameworks", []):
        c["typecheck"] = "npx tsc --noEmit"
    if "test" not in c and any(f.startswith(".github/workflows/") for f in files):
        for f in files:
            if f.startswith(".github/workflows/"):
                m = re.search(r"^\s+run:\s*(.*(?:test|pytest|jest|vitest|cargo test|go test).*)$", read(root, f), re.M)
                if m:
                    c["test"] = m.group(1).strip() + "  (from CI)"
                    break
    return c


def entry_points(root, files, lines, pj, py, cg):
    out = []
    if pj:
        if pj.get("bin"):
            b = pj["bin"]
            out.append("bin " + (", ".join(f"{k}={v}" for k, v in b.items()) if isinstance(b, dict) else str(b)))
        if pj.get("main"):
            out.append(f"main {pj['main']}")
    if py and py.get("scripts"):
        out.append("console_scripts " + ", ".join(f"{k}={v}" for k, v in list(py["scripts"].items())[:4]))
    if cg and cg.get("bins"):
        out.append("bins " + ", ".join(cg["bins"][:4]))
    names = {"main.py", "app.py", "cli.py", "server.py", "run.py", "wsgi.py", "asgi.py", "manage.py", "__main__.py", "index.js", "index.ts",
             "server.js", "server.ts", "app.js", "app.ts", "main.js", "main.ts", "main.go", "main.rs", "Program.cs", "cmd", "index.html"}
    hits = [f for f in files if os.path.basename(f) in names and f.count("/") <= 2 and not f.startswith(("tests/", "test/", "docs/"))]
    mains = []
    for f in files:
        if f.endswith(".py") and f.count("/") <= 2 and f not in hits and lines.get(f, 0) < 4000 and not f.startswith(("tests/", "test/")):
            if '__name__ == "__main__"' in read(root, f, 200_000) or "__name__ == '__main__'" in read(root, f, 200_000):
                mains.append(f)
    cmd = sorted({f.split("/")[1] for f in files if f.startswith("cmd/") and f.count("/") >= 2})
    if cmd:
        out.append("cmd/ " + ", ".join(cmd[:6]))
    out += hits[:8] + [f"{m} (__main__)" for m in mains[:4] if m not in hits]
    return out


def layout(root, files, lines, ndirs):
    dirs, top_files = {}, []
    for f in files:
        if "/" in f:
            d = f.split("/")[0]
            e = dirs.setdefault(d, {"files": 0, "lines": 0, "ext": {}, "kids": set()})
            e["files"] += 1
            e["lines"] += lines.get(f, 0)
            ext = os.path.splitext(f)[1]
            e["ext"][ext] = e["ext"].get(ext, 0) + 1
            parts = f.split("/")
            e["kids"].add(parts[1] if len(parts) > 2 else os.path.splitext(parts[1])[0])
        else:
            top_files.append(f)
    rows = sorted(dirs.items(), key=lambda kv: (-kv[1]["lines"], -kv[1]["files"], kv[0]))
    out = []
    for d, e in rows[:ndirs]:
        top = sorted(e["ext"].items(), key=lambda kv: -kv[1])[:2]
        kinds = " ".join(f"{n} {x.lstrip('.') or 'noext'}" for x, n in top)
        kids = sorted(e["kids"])
        kid_s = ", ".join(kids[:5]) + (f" (+{len(kids) - 5})" if len(kids) > 5 else "")
        out.append(f"{d + '/':<22}{e['files']:>5} files {e['lines']:>8,} lines  {kinds:<22} {kid_s}")
    if len(rows) > ndirs:
        out.append(f"(+{len(rows) - ndirs} dirs: " + ", ".join(d for d, _ in rows[ndirs:ndirs + 12]) + (", …" if len(rows) > ndirs + 12 else "") + ")")
    return out, top_files


def docs(root, files, lines):
    out = []
    for f in files:
        if "/" in f or not DOCS_RX.match(f):
            continue
        n = lines.get(f, 0)
        if f.lower().startswith("readme") and n:
            heads = [m.group(1).strip() for m in re.finditer(r"^#{1,2} (.+)$", read(root, f), re.M)]
            out.append(f"{f} ({n} lines" + (": " + ", ".join(h[:28] for h in heads[:7]) + (", …" if len(heads) > 7 else "") if heads else "") + ")")
        else:
            out.append(f"{f} ({n} lines)")
    nd = sum(1 for f in files if f.startswith(("docs/", "doc/")))
    if nd:
        out.append(f"docs/ ({nd} files)")
    return out


def main(a):
    if a and a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    ndirs, as_json, root = 14, False, "."
    i = 0
    while i < len(a):
        if a[i] == "--dirs":
            ndirs = int(a[i + 1])
            i += 2
        elif a[i] == "--json":
            as_json = True
            i += 1
        else:
            root = a[i]
            i += 1
    root = os.path.abspath(root)
    files = list_files(root)
    fset = set(files)
    lines = {}
    counted = files if len(files) <= MAX_COUNT else []
    for f in counted:
        ext = os.path.splitext(f)[1]
        if ext in LANG or os.path.basename(f) in ("Makefile", "Dockerfile", "Jenkinsfile"):
            lines[f] = count_lines(root, f)
    langs = {}
    for f, n in lines.items():
        l = LANG.get(os.path.splitext(f)[1])
        if l:
            e = langs.setdefault(l, [0, 0])
            e[0] += n
            e[1] += 1
    code_langs = sorted(((k, v) for k, v in langs.items() if k not in ("markdown", "yaml", "json", "toml", "xml", "html", "css")), key=lambda kv: -kv[1][0])
    pj, py, cg, go, dn = pkg_json(root, fset), pyproject(root, fset), cargo(root, fset), gomod(root, fset), dotnet(root, fset)
    mk = make_targets(root, fset)
    facts = {
        "root": root, "git": git_info(root), "files": len(files), "lines": sum(lines.values()),
        "langs": {k: {"lines": v[0], "files": v[1]} for k, v in sorted(langs.items(), key=lambda kv: -kv[1][0])},
        "node": pj, "python": py, "rust": cg, "go": go, "dotnet": dn, "jvm": jvm(root, fset), "other": other_manifests(root, fset),
        "tasks": mk, "docker": docker(root, fset), "ci": ci(root, fset),
        "tools": [t for t in TOOLS if t in fset and t not in ("Dockerfile", "manage.py", "conftest.py", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")],
        "entry": entry_points(root, files, lines, pj, py, cg),
        "docs": docs(root, files, lines),
    }
    facts["commands"] = commands(pj, py, cg, go, dn, mk, fset, root)
    lay, top_files = layout(root, files, lines, ndirs)
    facts["layout"] = lay
    facts["top_files"] = top_files
    big = sorted(((f, n) for f, n in lines.items() if LANG.get(os.path.splitext(f)[1]) not in (None, "markdown", "json", "yaml", "toml", "xml", "html", "css", "notebook")), key=lambda kv: -kv[1])[:4]
    facts["big"] = big
    if as_json:
        print(json.dumps(facts, indent=1, default=list))
        return 0

    def row(label, text):
        if text:
            print(f"{label:<8}{text}")

    g = facts["git"]
    gs = f"git {g['branch']} @{g['sha']} ({g['commits']} commits, {'clean' if not g['dirty'] else str(g['dirty']) + ' dirty'}, last {g['last']})" if g else "not a git repo"
    row("repo", f"{os.path.basename(root)}   {gs}   {len(files):,} files" + (f", {sum(lines.values()):,} lines" if lines else " (line counts skipped: >%d files)" % MAX_COUNT))
    row("langs", " · ".join(f"{k} {v[0]:,} lines / {v[1]} files" for k, v in code_langs[:5]) + (
        "   (+ " + ", ".join(f"{k} {v[1]}" for k, v in sorted(langs.items(), key=lambda kv: -kv[1][0]) if (k, v) not in code_langs[:5]) + ")" if len(langs) > len(code_langs[:5]) else ""))
    if pj:
        s = ", ".join(list(pj["scripts"].keys())[:9]) + (" …" if len(pj["scripts"]) > 9 else "")
        row("node", f"package.json {pj.get('name') or ''} v{pj.get('version') or '?'} ({pj['pm']}" + (", workspaces" if pj["workspaces"] else "") + (f", {pj['type']}" if pj.get("type") else "")
            + f"); scripts: {s or 'none'}; deps {pj['deps']} (+{pj['dev']} dev)" + (f"; {', '.join(pj['frameworks'][:8])}" if pj["frameworks"] else ""))
    if py:
        bits = []
        if py.get("name"):
            bits.append(f"pyproject.toml {py['name']} v{py.get('version') or '?'}" + (f" python{py['requires']}" if py.get("requires") else "") + (f" [{py['build']}]" if py.get("build") else ""))
        elif py.get("files"):
            bits.append(", ".join(py["files"]))
        if "deps" in py:
            bits.append(f"deps {py['deps']}" + (f" (+{py['dev']} dev)" if py.get("dev") else ""))
        if py.get("tools"):
            bits.append("tools: " + ", ".join(py["tools"][:8]))
        if py.get("files") and py.get("name"):
            bits.append("also " + ", ".join(py["files"][:4]))
        row("python", "; ".join(bits))
    if cg:
        row("rust", f"Cargo.toml {cg.get('name') or 'workspace'} v{cg.get('version') or '?'} edition {cg.get('edition') or '?'}; deps {cg['deps']} (+{cg['dev']} dev)"
            + (f"; bins {', '.join(cg['bins'])}" if cg["bins"] else "") + (f"; workspace {len(cg['workspace'])} members" if cg.get("workspace") else ""))
    if go:
        row("go", f"go.mod {go['module']} go{go['go']}; {go['deps']} direct deps")
    if dn:
        row("dotnet", ", ".join(dn["sln"] + dn["projects"][:5]) + (f"; {dn['tfm']}" if dn["tfm"] else ""))
    if facts["jvm"]:
        row("jvm", "; ".join(f"{k} {v}" for k, v in facts["jvm"].items()))
    if facts["other"]:
        row("also", ", ".join(facts["other"]))
    if mk:
        row("tasks", "; ".join(f"{k}: " + ", ".join(v[:12]) + (" …" if len(v) > 12 else "") for k, v in mk.items() if v))
    if facts["commands"]:
        row("run", "  |  ".join(f"{k}: {v}" for k, v in facts["commands"].items()))
    if facts["entry"]:
        row("entry", ", ".join(facts["entry"][:10]))
    if lay:
        print(f"{'layout':<8}{lay[0]}")
        for l in lay[1:]:
            print(f"{'':<8}{l}")
    if top_files:
        tf = [f for f in top_files if not DOCS_RX.match(f)]
        row("top", ", ".join(tf[:14]) + (f" (+{len(tf) - 14})" if len(tf) > 14 else ""))
    d = facts["docker"]
    if d:
        row("docker", ", ".join(d.get("dockerfiles", [])) + (f" FROM {', '.join(d['from'])}" if d.get("from") else "") + (f"; {d['compose']} services: {', '.join(d['services'][:8])}" if d.get("compose") else ""))
    if facts["ci"]:
        row("ci", "; ".join(facts["ci"][:4]) + (f"; +{len(facts['ci']) - 4} more" if len(facts["ci"]) > 4 else ""))
    if facts["tools"]:
        row("tools", ", ".join(facts["tools"][:16]) + (f" (+{len(facts['tools']) - 16})" if len(facts["tools"]) > 16 else ""))
    if facts["docs"]:
        row("docs", "  ".join(facts["docs"][:5]))
    if big:
        row("big", " · ".join(f"{f} {n:,}" for f, n in big))
    print(f"[scout: {len(files):,} files, {sum(lines.values()):,} lines, {len(langs)} languages; hashpatch outline/probe for any file named here]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
