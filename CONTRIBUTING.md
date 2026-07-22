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

# Lint and format shell scripts before pushing
just lint
just format

# Run Python unit tests
python3 -m unittest discover -s tests
# Or use the task runner
just test
```

Feature flags let you skip optional build steps:

```bash
ENABLE_SCX=0 just build
```

## What Makes a Good PR

- **Packages**: justify why it belongs in a base OS image, not a Flatpak
- **COPRs**: link to the COPR, explain the update cadence, note if it's a
  known-stable maintainer (e.g. `xxmitsu/mesa-git`)
- **Scripts in `build_files/scripts/`**: must pass `shellcheck --severity=error`
  and `shfmt -d` (run `just lint && just format` locally)
- **Python**: must pass `python3 -c "import ast; ast.parse(open('file.py').read())"`
  and `python3 -m unittest discover -s tests`; CodeQL runs on every PR for
  security issues
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

All PRs run:

- **Validation** — actionlint, hadolint, shellcheck, Python AST, TOML/JSON,
  Python unit tests, systemd unit verify, Justfile parse
- **Lint** — shellcheck on changed `.sh` files
- **CodeQL** — static analysis of Python code

The build and supply-chain workflows run on merge to `main`/`testing`, not on PRs,
to avoid burning CI minutes on draft work.

## Reporting Bugs

Use the issue templates — they ask for the right information up front. For
security issues, see [SECURITY.md](SECURITY.md).
