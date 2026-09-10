# nitro-skills

Token-saving skills: `hashpatch`, `rerun`, `probe`. Optimizing token usage is a
priority in this repo, so treat the rules below as requirements, not
suggestions — use the skill whenever its trigger applies, don't fall back to
the default tool just because it's more familiar.

## Mandatory skill usage

- **Editing any existing file** → use `hashpatch` (outline/grep/patch) instead
  of Read+Edit. Exception: a file you are creating from scratch, or a change
  so small you already have the exact line ranges from a prior hashpatch
  `outline`/`grep` call in this session.
- **Running any test, build, or lint command more than once in a session**
  → use `rerun` instead of invoking it directly, so repeat runs report only
  the diff. First run of a given command can go through `rerun` too (it
  establishes the baseline for free).
- **Learning what a Python or JS module exports/its function signatures**
  → use `probe` instead of reading the module's source. Do not probe modules
  that start servers, touch the filesystem, or need secrets/network — read
  those normally.

## Non-triggers (use judgment, skill is optional)

- Reading a brand-new file for the first time to understand it holistically.
- A file already fully in context from a recent read/outline this turn.
- One-off commands unlikely to be rerun (e.g. `git status`, `ls`).

If a task clearly matches a trigger above, invoke the skill without asking.
