---
name: push-via-tmp-clone
description: Push to testing when .git is read-only by cloning to /tmp, applying local changes, committing and pushing.
---

# Push via Tmp Clone

## Publishing invariants

- Never create or open a pull request for this repository.
- Commit approved changes directly to the `testing` branch.
- Push only to `origin/testing`; never infer another destination from the current clone.
- Require an explicit user request before committing or pushing.

Use when `git add`/`commit`/`push` fails with `Read-only file system` on `.git` (or `.agents`) because the sandbox mounts them `ro`. The workspace root is still writable, but git metadata is not. Work around by using a writable clone in `/tmp`.

## When to use

- `git status` shows modifications but `git add` fails: `fatal: Unable to create '.../.git/index.lock': Read-only file system`
- `mount | grep kyth` shows `/.../kyth/.git type btrfs (ro,...)`
- You have an explicit user ask to commit/push to `testing` (per `AGENTS.md` — never push without explicit ask).

## Steps

1. Save the local fix as a patch (so the tmp clone can apply it without needing the ro index):
   ```bash
   git diff -- <changed-files> > /tmp/kyth-fix.patch
   # or for all pending changes:
   git diff > /tmp/kyth-fix.patch
   # also save untracked files if needed: git diff --no-index /dev/null <untracked> >> /tmp/kyth-fix.patch
   ```

2. Shallow-clone `testing` to a writable location:
   ```bash
   rm -rf /tmp/kyth-push
   timeout 60 git clone --depth 1 --branch testing https://github.com/mrtrick37/kyth.git /tmp/kyth-push
   ```

3. Apply the patch inside the tmp clone:
   ```bash
   cp /tmp/kyth-fix.patch /tmp/kyth-push/
   git -C /tmp/kyth-push apply --check /tmp/kyth-fix.patch
   git -C /tmp/kyth-push apply /tmp/kyth-fix.patch
   ```

4. Commit and push from the tmp clone (uses `gh` credential helper):
   ```bash
   git -C /tmp/kyth-push config user.name "mrtrick37"
   git -C /tmp/kyth-push config user.email "261214137+mrtrick37@users.noreply.github.com"
   git -C /tmp/kyth-push add <changed-files>
   git -C /tmp/kyth-push commit -m "fix(scope): <one-line>"
   git -C /tmp/kyth-push push origin testing
   git ls-remote origin testing | head
   ```

5. Always clean up the working tree after push (mandatory — do not leave the original checkout dirty):
   ```bash
   # for each modified file (restores to the old HEAD content so the ro checkout appears clean;
   # the new commit is already on origin/testing and will be visible after the next fetch/pull):
   git show HEAD:"<path>" > "<path>.tmp" && cat "<path>.tmp" > "<path>" && rm "<path>.tmp"
   # for each untracked file that was part of the patch:
   rm <untracked>
   # remove temporary artifacts:
   rm /tmp/kyth-fix.patch
   rm -rf /tmp/kyth-push
   git status --porcelain  # must be clean — if not, repeat for remaining paths
   ```
   Do not skip this step. A dirty working tree after a successful push confuses the next `git diff` / `git status` and risks re-pushing the same changes or hiding new work. If `git status` still shows modifications, you missed a path — enumerate it with `git status --porcelain` and restore it.

## Validation gate (arch #10 — parity with CI)

Always run **exactly** CI's gates before pushing from the tmp clone (tmp clone bypasses `.githooks/pre-push`):

```bash
./build_files/scripts/validate.sh  # includes zizmor/hadolint/shellcheck + 1057 unit tests + portability
./build_files/scripts/run-quality.sh  # ruff + coverage (skip Hub smoke under coverage, it OOMs)
PYTHONPATH=build_files/kyth-installer:build_files/kyth-welcome:build_files/kyth_shared python3 -m unittest tests.test_validation_portability
if python3 -c 'import PySide6' 2>/dev/null; then
  QT_QPA_PLATFORM=offscreen PYTHONPATH=build_files/kyth-welcome:build_files/kyth_shared python3 -m unittest tests.test_kyth_welcome_hub_smoke
else
  echo "Hub smoke unavailable: PySide6 is not installed; blocked-Qt portability remains mandatory"
fi
```

This catches F821/QSS regressions before CI (e.g. 31288193192).

## Notes

- Do not `sudo mount -o remount,rw` — that bypasses the sandbox and violates the git skill's lock safety.
- Do not `rm .git/index.lock` without proving no live git process holds it.
- Prefer `git diff -- <files>` over `git diff` to name only the fix, keeping unrelated dirt out of the push.
- The tmp clone is shallow (`--depth 1`) to avoid timeout on large history.
