---
name: push-via-tmp-clone
description: DEPRECATED - Use direct git push. Toolbox has .git rw; tmp clone no longer needed.
---

# Push Direct (Simplified - Toolbox)

## Publishing invariants

- Never create or open a pull request for this repository.
- Commit approved changes directly to the `testing` branch.
- Push only to `origin/testing`; never infer another destination from the current clone.
- Require an explicit user request before committing or pushing.

## Context

We work **inside the kyth-ai-dev toolbox** where VS Code and Muse are installed.
In the toolbox `.git` is **always writable** (`rw`). The previous tmp-clone
workaround for `Read-only file system` on `.git` is **deprecated** and must not
be used.

If you are inside the Muse bwrap sandbox and see
`fatal: Unable to create .../.git/index.lock: Read-only file system`,
escape the sandbox via `flatpak-spawn --host` instead of tmp-clone:

```bash
flatpak-spawn --host git status
flatpak-spawn --host git add <files>
flatpak-spawn --host git commit -m "fix(scope): message"
flatpak-spawn --host git push origin testing
```

## Steps (direct - no tmp clone)

1. Verify branch and status (toolbox, .git rw):

   ```bash
   git status
   git diff --stat
   git log --oneline -3
   ```

   If sandbox shows ro, use `flatpak-spawn --host git ...` for the same
   commands — do not create a tmp clone.

2. Stage and commit directly:

   ```bash
   git add <changed-files>
   git config user.name "mrtrick37"
   git config user.email "261214137+mrtrick37@users.noreply.github.com"
   git commit -m "fix(scope): one-line"
   ```

3. Push directly:

   ```bash
   git push origin testing
   git ls-remote origin testing | head
   ```

   If sandboxed, prefix with `flatpak-spawn --host`.

4. Optional validation (same as CI):

   ```bash
   ./build_files/scripts/validate.sh
   ```

   Run before push when touching CI-sensitive areas.

## Notes

- Do not `rm -rf /tmp/kyth-push`, do not `git clone --depth 1 --branch testing`,
  do not `git apply` — all tmp-clone steps are removed.
- Do not `sudo mount -o remount,rw` — use the toolbox/host spawn instead.
- Prefer `flatpak-spawn --host git ...` over tmp-clone when bwrap shows ro.
