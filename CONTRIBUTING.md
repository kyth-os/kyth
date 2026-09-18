# Contributing to KythOS

Thanks for your interest. KythOS is a personal daily-driver OS — contributions
are welcome but the bar is practical: changes need to work on real hardware and
not break the live ISO boot path.

## Branches

| Branch | Purpose |
|---|---|
| `main` | Stable channel — maps to `:latest` image and `iso-latest` |
| `testing` | Development — maps to `:testing` image and `iso-testing` |

Open PRs against `testing`. After validation on real hardware, tested changes
merge to `main`.

## Local Build

You need Docker (or Podman) and [just](https://github.com/casey/just).

```bash
# Build both the base layer and the final OS image
just build

# Build and boot the live ISO in QEMU (requires SPICE client)
just rebuild-live-iso
just run-live-iso-native

# One-time: wire up the local git hooks (pre-commit, pre-push)
just install-git-hooks

# Lint and format shell scripts before pushing
just lint
just format

# Run the full local validation suite (same gates as CI's validation job)
just validate
# Heaviest local gate: validation + changed-file quality + CodeQL-shaped checks
just ci-preflight

# Run Python unit tests
python3 -m unittest discover -s tests
# Or use the task runner
just test
```

Feature flags and opt-in image profiles:

```bash
ENABLE_SCX=0 just build
ENABLE_GAMING_PERIPHERALS=1 just build
ENABLE_VIRTUALIZATION_HOST=1 just build
ENABLE_KSM=1 just build
```

## What Makes a Good PR

- **Packages**: justify why it belongs in a base OS image, not a Flatpak
- **COPRs**: link to the COPR, explain the update cadence, note if it's a
  known-stable maintainer (e.g. `xxmitsu/mesa-git`)
- **Scripts in `build_files/scripts/`**: must pass `shellcheck
  --severity=warning` and `shfmt -d` (run `just lint && just format`
  locally). The pre-commit hook enforces a `--severity=error` floor on
  staged `.sh` files, but CI and `just validate` gate on warnings — fix
  warnings before pushing, not after CI goes red.
- **Python**: must pass `run-quality.sh` (ruff per `ruff.toml`, the
  coverage-instrumented suite, and the critical-coverage floor) plus
  `python3 -m unittest discover -s tests`; CodeQL runs on every PR for
  security issues. On PRs CI runs quality changed-only; on push to
  `main`/`testing` it runs the full suite.
- **Dockerfiles**: must pass `hadolint --failure-threshold error`
- **Tests**: major behavior changes must add or update automated tests. If a
  change cannot be tested automatically, explain why and include the manual
  validation performed.
- **Breaking changes to the installer or upgrade path**: describe the impact in
  the PR body; include a note if users need to reinstall vs. `bootc upgrade`
- **Contribution authority**: by opening a PR, you assert that you have the
  right to contribute the work under the project license. Use
  `Signed-off-by` / DCO-style commits when requested by the maintainer.

## Review Expectations

Review focuses on user impact, update and rollback safety, install behavior,
security boundaries, maintainability, and whether the change belongs in the base
image. Workflow, installer, privileged-helper, release, and credential-handling
changes require extra scrutiny.

Before merge, maintainers should confirm that relevant validation passed, major
new behavior has tests or a documented test rationale, and the PR explains any
manual hardware or live ISO validation.

## CI Checks

All PRs run the **Validation** workflow (5 jobs):

- **validation** — actionlint, zizmor (auditor, medium+), hadolint, and the
  full `validate.sh` suite (shellcheck at `--severity=warning`, Python
  syntax, TOML/JSON, systemd unit verify, Justfile parse, optimization
  budgets, gaming hash gate, full unit tests)
- **quality (coverage and lint)** — `run-quality.sh`: ruff, blind-except
  audit, coverage-instrumented suite plus the critical-coverage floor;
  changed-only on PRs, full on push. Uploads the coverage report.
- **hub-shell / installer-shell** — frontend + Tauri shell builds
- **rust** — clippy (advisory while the warning burn-down is in progress)
  plus `cargo test --locked`

Tool versions (actionlint, hadolint, just, shellcheck, zizmor, syft, grype)
are pinned — validators in `validation.yml` via
`build_files/scripts/install-validation-tools.sh`, scanners in their own
workflows. **CodeQL** runs static analysis on Python in parallel and does
not block image builds.

The build, supply-chain, CVE-scan, and live-ISO workflows run on merge to
`main`/`testing` (or on their dispatch chain), not on PRs, to avoid burning
CI minutes on draft work.

## Pre-push Gate

With hooks installed (`just install-git-hooks`), every push runs:

1. `validate.sh --fast` (lint, actionlint, zizmor, shell analysis,
   syntax/secrets/systemd — unit tests stay in CI), and
2. `run-quality.sh` **without** `--fast` — the coverage floor is a
   mandatory local gate, including in fast mode.

Set `KYTH_ALLOW_HEAVY_PRE_PUSH=1` to also run the full validation suite
and the Hub headless smoke test. `KYTH_SKIP_PRE_PUSH_VALIDATION=1`
bypasses the gate (emergencies only — CI still gates merge).

## Reporting Bugs

Use the issue templates — they ask for the right information up front. For
security issues, see [SECURITY.md](SECURITY.md).
