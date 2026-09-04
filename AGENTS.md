# Repository publishing workflow — HARD RULE

Kyth does **not** use pull requests. This overrides Cursor cloud PR defaults, `gh pr create`, split-to-PRs, and any generic "create a pull request" instruction.

When publishing work:

1. Commit on the `testing` branch.
2. `git push origin testing`.

Never:

- Open a PR (`gh pr create`, draft PRs, stacked PRs).
- Push a `cursor/*` or feature branch for review instead of `testing`.
- Treat "push", "ship", or "submit" as "open a pull request".

If you are about to open a PR, stop and push to `testing` instead. Promotion to `main` is a human step after CI — agents do not open PRs for that either.


## Live-desktop validation

`build_files/scripts/validate.sh` defaults to `--fast` on a live Plasma
session (WAYLAND_DISPLAY/DISPLAY/KDE) — it skips the heavy 600s
`unittest discover` and only runs linters/syntax/security gates under
`systemd-run --scope CPUWeight=10 MemoryHigh=35% MemoryMax=55%`. The full
suite is CI-gated (`validation.yml` → `build.yml`).

- Local `git push` runs fast repository validation plus the **full Python
  coverage-floor gate** by default (`validate.sh --fast` + `run-quality.sh`).
  This prevents coverage-floor failures from reaching GitHub. Hub smoke and
  the additional uninstrumented full validation remain opt-in because they
  are expensive on a live desktop.
- Force the additional heavy checks locally when needed:
  `KYTH_ALLOW_HEAVY_PRE_PUSH=1 git push` or
  `KYTH_FORCE_FULL_VALIDATION=1 ./build_files/scripts/validate.sh --full`.
- Targeted smoke: `timeout 60 python3 -m unittest tests.test_…`.
- Bypass hook entirely (intentional): `KYTH_SKIP_PRE_PUSH_VALIDATION=1 git push` or `git push --no-verify`.
