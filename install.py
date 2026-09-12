#!/usr/bin/env python3
"""Install nitro-skills into the global Claude directory (~/.claude).

Copies every skill folder into ~/.claude/skills/, wires the hooks into
~/.claude/settings.json, and checks for the external CLI tools the skills and
hooks rely on (ripgrep, fd, sd; jq optional), printing an install command for
your platform for anything missing. Safe to re-run.

Usage:
    python install.py            # install skills, hooks, and any missing tools
    python install.py --no-hooks # copy skills only, skip settings.json
    python install.py --no-tools # do not run package managers; only print hints
    python install.py --dry-run  # show what would happen, change nothing
    python install.py --yes      # accept the disclaimer non-interactively (CI/scripts)
"""
import json
import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = [
    "hashpatch", "rerun", "probe", "seen", "alias", "believe", "refactor",
    "mine", "shape", "trace", "sdiff", "q", "blast", "recall", "budget",
]
CLAUDE_HOME = os.path.join(os.path.expanduser("~"), ".claude")
SKILLS_DIR = os.path.join(CLAUDE_HOME, "skills")
SETTINGS_PATH = os.path.join(CLAUDE_HOME, "settings.json")

DRY = "--dry-run" in sys.argv
NO_HOOKS = "--no-hooks" in sys.argv
NO_TOOLS = "--no-tools" in sys.argv
YES = "--yes" in sys.argv or "-y" in sys.argv
ACCEPT = "I AGREE"


def say(msg):
    print(msg)


def copy_skills():
    say(f"Installing {len(SKILLS)} skills into {SKILLS_DIR}")
    os.makedirs(SKILLS_DIR, exist_ok=True) if not DRY else None
    for name in SKILLS:
        src = os.path.join(HERE, name)
        dst = os.path.join(SKILLS_DIR, name)
        if not os.path.isdir(src):
            say(f"  ! skipping {name}: not found at {src}")
            continue
        say(f"  {name} -> {dst}")
        if DRY:
            continue
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def hook_path(name):
    # Hooks are invoked with `python <path>`, so the path must resolve from
    # wherever settings.json is read, hence the absolute ~/.claude location.
    return os.path.join(CLAUDE_HOME, "hooks", name)


def copy_hooks():
    src_dir = os.path.join(HERE, "hooks")
    dst_dir = os.path.join(CLAUDE_HOME, "hooks")
    say(f"Installing hooks into {dst_dir}")
    if not DRY:
        os.makedirs(dst_dir, exist_ok=True)
    for name in os.listdir(src_dir):
        if not name.endswith(".py"):
            continue
        src = os.path.join(src_dir, name)
        dst = os.path.join(dst_dir, name)
        say(f"  {name} -> {dst}")
        if not DRY:
            shutil.copy2(src, dst)


def python_cmd():
    # Whichever interpreter is running this script is guaranteed to work,
    # so hooks are wired with the same command the user just used.
    return "python" if sys.executable and "python" in os.path.basename(sys.executable).lower() else sys.executable


def build_hook_entry(name):
    return {"type": "command", "command": f'python "{hook_path(name)}"'}


def merge_hooks(settings):
    hooks = settings.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    post = hooks.setdefault("PostToolUse", [])

    def find_matcher(entries, matcher):
        for e in entries:
            if e.get("matcher") == matcher:
                return e
        e = {"matcher": matcher, "hooks": []}
        entries.append(e)
        return e

    def ensure_hook(entry, hook_name):
        target = f'"{hook_path(hook_name)}"'
        for h in entry["hooks"]:
            if target in h.get("command", ""):
                return
        entry["hooks"].append(build_hook_entry(hook_name))

    bash_pre = find_matcher(pre, "Bash|PowerShell")
    for hook_name in ("enforce-nitro-bash.py", "expand-aliases.py", "budget-guard.py"):
        ensure_hook(bash_pre, hook_name)

    read_pre = find_matcher(pre, "Read")
    ensure_hook(read_pre, "block-whole-file-reads.py")

    bash_post = find_matcher(post, "Bash|PowerShell")
    ensure_hook(bash_post, "budget-record.py")

    return settings


def wire_settings():
    say(f"Updating {SETTINGS_PATH}")
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError:
                say("  ! existing settings.json is not valid JSON, leaving hooks untouched")
                return
    else:
        settings = {}

    settings = merge_hooks(settings)

    if DRY:
        say("  (dry run, not writing)")
        return

    os.makedirs(CLAUDE_HOME, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    say("  done")


DISCLAIMER = """\
DISCLAIMER - READ BEFORE CONTINUING

What this installer does:
  * copies the nitro-skills skill folders into ~/.claude/skills/
  * copies the hook scripts into ~/.claude/hooks/
  * merges PreToolUse/PostToolUse hook entries into ~/.claude/settings.json
  * checks whether ripgrep (rg), fd, sd and jq are on your PATH and, for any
    that are missing, RUNS your system package manager (winget / Chocolatey /
    Scoop on Windows, Homebrew on macOS, apt / dnf / pacman / zypper / apk on
    Linux, cargo as a fallback) to install them. Linux package managers are
    invoked with sudo and may prompt for your password. Pass --no-tools to
    only print the commands instead, or --dry-run to change nothing.

Third-party software. ripgrep, fd, sd, jq, and any package manager (Homebrew,
apt, dnf, pacman, zypper, apk, winget, Chocolatey, Scoop, cargo) you use to
obtain them are independent third-party projects that are not developed,
distributed, audited, endorsed, or controlled by the nitro-skills authors. Any
suggested install command is provided for convenience only. You alone are
responsible for verifying the source, integrity, licence, and security of any
software you install, and for any vulnerability, defect, malware, supply-chain
compromise, data loss, or other harm arising from it.

AI-generated output. nitro-skills is used by AI coding agents. AI systems make
mistakes: they can misread code, produce incorrect or insecure edits, delete or
overwrite data, run unintended commands, and report success when something has
failed. Nothing produced with or by these skills should be relied upon without
independent human review. Always inspect diffs, run your own tests, and keep
backups and version control. You are solely responsible for every change made
in your environment while these skills and hooks are in use.

No warranty. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, ACCURACY, AND
NON-INFRINGEMENT. No advice or information, whether oral or written, obtained
from the authors or through the software creates any warranty.

Limitation of liability. TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN
NO EVENT SHALL THE AUTHORS, CONTRIBUTORS, OR COPYRIGHT HOLDERS BE LIABLE FOR
ANY CLAIM, DAMAGES, OR OTHER LIABILITY WHATSOEVER - WHETHER IN AN ACTION OF
CONTRACT, TORT (INCLUDING NEGLIGENCE), STRICT LIABILITY, OR OTHERWISE - INCLUDING
WITHOUT LIMITATION DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
CONSEQUENTIAL, OR PUNITIVE DAMAGES, LOSS OF DATA, LOSS OF PROFITS, BUSINESS
INTERRUPTION, SECURITY BREACHES, OR THE COST OF SUBSTITUTE GOODS OR SERVICES,
ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE, ANY THIRD-PARTY
SOFTWARE IT REFERENCES, ANY OUTPUT OF AN AI SYSTEM USING IT, OR THE USE OF OR
OTHER DEALINGS IN THE SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
DAMAGES. Some jurisdictions do not allow certain exclusions or limitations, in
which case the above applies to the fullest extent permitted.

Indemnity. You agree to indemnify and hold harmless the authors, contributors,
and copyright holders from any claim, demand, loss, or expense (including
reasonable legal fees) arising out of your use of the software, third-party
tools, or AI-generated output.

Nothing has been installed yet. To accept this disclaimer and continue, type
exactly  I AGREE  at the prompt below. Anything else aborts the installer.
Pass --yes to accept non-interactively (for scripts and CI); doing so is the
same acceptance as typing it.
"""


def accept_disclaimer():
    if YES:
        say("(disclaimer accepted via --yes)")
        return
    if not sys.stdin or not sys.stdin.isatty():
        say("No interactive terminal to accept the disclaimer on. Re-run with --yes to accept it, or run from a terminal.")
        sys.exit(2)
    try:
        answer = input(f"Type {ACCEPT} to accept and continue: ").strip()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer != ACCEPT:
        say("Disclaimer not accepted. Nothing was changed.")
        sys.exit(2)
    say("")

# (name, executables to look for, required, per-package-manager package id,
#  release page). fd is `fdfind` on Debian/Ubuntu; the skills accept both, but
# the hook messages say `fd`, so a symlink or alias is recommended there.
TOOLS = [
    ("ripgrep", ("rg",), True, {
        "brew": "ripgrep", "apt": "ripgrep", "dnf": "ripgrep", "pacman": "ripgrep",
        "zypper": "ripgrep", "apk": "ripgrep", "winget": "BurntSushi.ripgrep.MSVC",
        "choco": "ripgrep", "scoop": "ripgrep", "cargo": "ripgrep",
    }, "https://github.com/BurntSushi/ripgrep/releases"),
    ("fd", ("fd", "fdfind"), True, {
        "brew": "fd", "apt": "fd-find", "dnf": "fd-find", "pacman": "fd",
        "zypper": "fd", "apk": "fd", "winget": "sharkdp.fd",
        "choco": "fd", "scoop": "fd", "cargo": "fd-find",
    }, "https://github.com/sharkdp/fd/releases"),
    ("sd", ("sd",), True, {
        "brew": "sd", "apt": None, "dnf": None, "pacman": "sd",
        "zypper": None, "apk": "sd", "winget": "chmln.sd",
        "choco": "sd-cli", "scoop": "sd", "cargo": "sd",
    }, "https://github.com/chmln/sd/releases"),
    ("jq", ("jq",), False, {
        "brew": "jq", "apt": "jq", "dnf": "jq", "pacman": "jq",
        "zypper": "jq", "apk": "jq", "winget": "jqlang.jq",
        "choco": "jq", "scoop": "jq", "cargo": None,
    }, "https://jqlang.github.io/jq/download/"),
]
LINUX_MANAGERS = (
    ("apt", "sudo apt install {}"), ("dnf", "sudo dnf install {}"),
    ("pacman", "sudo pacman -S {}"), ("zypper", "sudo zypper install {}"),
    ("apk", "sudo apk add {}"),
)


def install_commands(name):
    """Candidate install commands for this platform, first is preferred."""
    _, _, _, pkgs, releases = next(t for t in TOOLS if t[0] == name)
    system = platform.system()
    cmds = []
    if system == "Darwin":
        if shutil.which("brew") and pkgs.get("brew"):
            cmds.append(["brew", "install", pkgs["brew"]])
    elif system == "Windows":
        for mgr in ("winget", "choco", "scoop"):
            if pkgs.get(mgr) and shutil.which(mgr):
                args = ["install", pkgs[mgr]]
                if mgr == "winget":
                    args += ["--accept-source-agreements", "--accept-package-agreements", "-e"]
                if mgr == "choco":
                    args.append("-y")
                cmds.append([mgr] + args)
    else:
        for mgr, fmt in LINUX_MANAGERS:
            if shutil.which(mgr) and pkgs.get(mgr):
                cmd = fmt.format(pkgs[mgr]).split()
                if mgr in ("apt", "dnf", "zypper"):
                    cmd.append("-y")
                if mgr == "pacman":
                    cmd.append("--noconfirm")
                cmds.append(cmd)
                break
    if pkgs.get("cargo") and shutil.which("cargo"):
        cmds.append(["cargo", "install", pkgs["cargo"]])
    return cmds, releases


def tool_hint(name):
    cmds, releases = install_commands(name)
    if cmds:
        return " ".join(cmds[0]) + (f"   (or: {' / '.join(' '.join(c) for c in cmds[1:])})" if len(cmds) > 1 else "")
    _, _, _, pkgs, _ = next(t for t in TOOLS if t[0] == name)
    system = platform.system()
    if system == "Windows" and pkgs.get("winget"):
        return f"winget install {pkgs['winget']}   (no package manager found on PATH; or download from {releases})"
    if system == "Darwin" and pkgs.get("brew"):
        return f"brew install {pkgs['brew']}   (Homebrew not found on PATH; or download from {releases})"
    return f"download from {releases}" + (f"   (or: cargo install {pkgs['cargo']})" if pkgs.get("cargo") else "")


def find_tool(exes):
    return next((shutil.which(e) for e in exes if shutil.which(e)), None)


def install_tool(name, exes):
    cmds, releases = install_commands(name)
    if not cmds:
        say(f"  no package manager found to install {name}; install it manually: {tool_hint(name)}")
        return None
    for cmd in cmds:
        say(f"  running: {' '.join(cmd)}")
        try:
            rc = subprocess.run(cmd).returncode
        except OSError as e:
            say(f"  could not run {cmd[0]}: {e}")
            continue
        if rc == 0:
            found = find_tool(exes)
            if found:
                return found
            say(f"  {cmd[0]} reported success but {name} is not on PATH yet; open a new terminal after installing.")
            return "installed"
        say(f"  {cmd[0]} exited with {rc}, trying the next option" if cmd is not cmds[-1] else f"  {cmd[0]} exited with {rc}")
    say(f"  could not install {name}; install it manually from {releases}")
    return None


def check_tools():
    missing_required = []
    for name, exes, required, _, _ in TOOLS:
        found = find_tool(exes)
        if not found:
            tag = "required by the hooks and skills" if required else "optional, used for narrowing JSON after `shape`"
            say(f"{name} not found on PATH ({tag}).")
            if DRY or NO_TOOLS:
                say(f"  Install with: {tool_hint(name)}")
            else:
                found = install_tool(name, exes)
            if not found:
                if required:
                    missing_required.append(name)
                continue
            if found == "installed":
                continue
        try:
            out = subprocess.run([found, "--version"], capture_output=True, text=True)
            version = out.stdout.strip().splitlines()[0] if out.stdout.strip() else found
            say(f"{name} found: {version}")
        except OSError:
            say(f"{name} found on PATH ({found}) but could not run it")
        if name == "fd" and os.path.basename(found).lower().startswith("fdfind"):
            say("  note: installed as `fdfind`; add a `fd` symlink or alias so hook messages match: "
                "ln -s \"$(command -v fdfind)\" ~/.local/bin/fd")
    if missing_required:
        say(f"Missing required tools: {', '.join(missing_required)}. Install them before relying on the hooks.")


def check_python_node():
    say(f"Python: {sys.version.split()[0]} ({sys.executable})")
    node = shutil.which("node")
    if node:
        try:
            out = subprocess.run([node, "--version"], capture_output=True, text=True)
            say(f"Node found: {out.stdout.strip()} (needed only for `probe js`)")
        except OSError:
            say(f"Node found on PATH ({node}) but could not run it")
    else:
        say("Node not found (only needed for `probe js`; skip if you don't use JS probing)")


def main():
    say(f"nitro-skills installer ({platform.system()})")
    say("")
    say(DISCLAIMER)
    accept_disclaimer()
    if DRY:
        say("-- dry run: no files will be written --")
    say("")
    check_python_node()
    check_tools()
    say("")
    copy_skills()
    say("")
    if NO_HOOKS:
        say("Skipping hook install (--no-hooks). Skills are copied but not enforced.")
    else:
        copy_hooks()
        say("")
        wire_settings()
    say("")
    say("Done. Restart Claude Code (or start a new session) to pick up the changes.")
    if not NO_HOOKS:
        say(f"Hooks were merged into {SETTINGS_PATH} without removing any existing entries.")


if __name__ == "__main__":
    main()
