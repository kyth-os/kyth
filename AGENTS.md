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

`build_files/scripts/validate.sh` runs full `unittest discover` (600s) under
`systemd-run --scope CPUWeight=20`. On a live Plasma desktop this still risks
kwin starvation — local `--no-verify` push is intentional; CI `validation.yml`
is the required gate before `build.yml`. Use targeted `python -m unittest tests.test_…` with `timeout` for pre-push smoke.
