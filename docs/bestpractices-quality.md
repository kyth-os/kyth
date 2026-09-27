# OpenSSF Best Practices: Passing Quality Evidence

This document maps the OpenSSF Best Practices Passing quality criteria for
KythOS to project evidence. It is intended to support the badge entry at
bestpractices.dev and to keep the justifications reviewable in the repository.

Badge form entries can use the short "Recommended entry" text below. Longer
evidence is included so the answers remain auditable after the form is updated.

## Working Build System

### `build`

Recommended status: Met

Recommended entry: KythOS has an automated build system in `Justfile`,
`Dockerfile`, `build_base/Dockerfile`, and GitHub Actions. `just build-base`,
`just build`, and `just build-live-iso` rebuild the OS image and ISO from source
and repository build inputs. CI builds and publishes images and ISOs from the
same tracked source.

Evidence:

- `README.md` documents local build commands.
- `CONTRIBUTING.md` documents local build expectations.
- `.github/workflows/build.yml` builds container images.
- `.github/workflows/build-live-iso.yml` builds ISO artifacts.
- `.github/workflows/validation.yml` validates source inputs before release.

### `build_common_tools`

Recommended status: Met

Recommended entry: KythOS uses common build tools for this type of Linux OS
image project: `just`, Docker/BuildKit, Podman, bootc, bootc-image-builder,
Titanoboa for live ISO assembly, GitHub Actions, shell scripts, and Python.

Evidence:

- `Justfile` is the local task runner entry point.
- `README.md` lists build requirements and common recipes.
- CI workflows use standard GitHub Actions, Docker Buildx, Podman, and bootc
  tooling.

### `build_floss_tools`

Recommended status: Met

Recommended entry: KythOS is buildable with FLOSS tools on Linux. The build
uses tracked source, Fedora/Universal Blue/bootc components, shell, Python,
just, Podman or Docker Engine/BuildKit, bootc-image-builder, and GitHub Actions
workflow definitions. Proprietary Docker Desktop is not required.

Evidence:

- `README.md` allows Docker or Podman-based local builds.
- CI builds run on Ubuntu-hosted GitHub Actions using open source tooling.
- Release artifacts include provenance, signed metadata, and SBOMs.

## Automated Test Suite

### `test`

Recommended status: Met

Recommended entry: KythOS has FLOSS automated tests in `tests/`. The suite is
documented in `CONTRIBUTING.md`, exposed as `just test`, and run in the
Validation workflow with `python3 -m unittest discover -s tests`.

Evidence:

- `tests/test_kyth_hub_web_actions.py`
- `CONTRIBUTING.md` documents the test command.
- `.github/workflows/validation.yml` runs the test suite.
- `Justfile` provides `just test`.

### `test_invocation`

Recommended status: Met

Recommended entry: The Python tests are invocable using the standard library
test runner: `python3 -m unittest discover -s tests`. The project also provides
the convenience command `just test`.

Evidence:

- `CONTRIBUTING.md`
- `.github/workflows/validation.yml`
- `Justfile`

### `test_most`

Recommended status: Unmet

Recommended entry: The current automated test suite covers important pure
parser/helper paths and System Hub action contracts, but it does not cover
every project behavior. KythOS expands coverage as major behavior changes
land; hardware, installer, live ISO, and full OS integration behavior still
require manual or VM validation.

Evidence:

- `tests/test_kyth_hub_web_actions.py` covers selected Hub action behavior.
- `docs/daily-driver-validation.md` documents runtime validation that cannot be
  fully represented by unit tests.

### `test_continuous_integration`

Recommended status: Met

Recommended entry: KythOS uses GitHub Actions CI. Pull requests and pushes to
`main` and `testing` run the Validation workflow, including workflow checks,
container linting, ShellCheck, Python syntax checks, unit tests, configuration
parsing, systemd verification, and Justfile parsing. CodeQL analysis also runs
through GitHub Actions.

Evidence:

- `.github/workflows/validation.yml`
- `.github/workflows/codeql.yml`
- `.github/workflows/build.yml`

## New Functionality Testing

### `test_policy`

Recommended status: Met

Recommended entry: `CONTRIBUTING.md` requires major behavior changes to add or
update automated tests. If a change cannot be tested automatically, contributors
must explain why and include the manual validation performed.

Evidence:

- `CONTRIBUTING.md` "What Makes a Good PR" section.
- `.github/pull_request_template.md` asks whether major behavior changes include
  tests or a documented rationale.

### `tests_are_added`

Recommended status: Met

Recommended entry: The current quality-improvement change adds the first Python
unit test suite for pure System Hub parser behavior and wires it into CI. Future
major behavior changes are expected to follow the documented policy by adding
tests or documenting why automation is not practical.

Evidence:

- `tests/test_kyth_hub_web_actions.py`
- `.github/workflows/validation.yml` unit test step.
- `.github/pull_request_template.md` test checklist item.

### `tests_documented_added`

Recommended status: Met

Recommended entry: The contribution instructions and pull request template
document that major behavior changes should add or update automated tests, or
include a rationale and manual validation when automation is not practical.

Evidence:

- `CONTRIBUTING.md`
- `.github/pull_request_template.md`

## Warning Flags and Linters

### `warnings`

Recommended status: Met

Recommended entry: KythOS uses multiple linter/static validation tools:
ShellCheck for shell scripts, `bash -n`, hadolint for container build files,
actionlint and zizmor for GitHub Actions, Python AST parsing, JSON/TOML parsing,
systemd unit verification, Justfile parsing, CodeQL for Python, and a
high-confidence committed-secret scan.

Evidence:

- `.github/workflows/validation.yml`
- `.github/workflows/codeql.yml`
- `Justfile` `lint` and `check` recipes.

### `warnings_fixed`

Recommended status: Met

Recommended entry: The validation workflow treats unexpected warnings/errors
from linting and parsing tools as failures. Local verification for this evidence
showed ShellCheck and `bash -n` passing for tracked shell scripts, Python syntax
passing, unit tests passing, tracked configuration parsing, Justfile checks, and
the committed-secret scan passing.

Evidence:

- `.github/workflows/validation.yml` exits nonzero on validation failures.
- `CONTRIBUTING.md` requires relevant checks before pushing.

### `warnings_strict`

Recommended status: Met

Recommended entry: KythOS uses strict validation where practical for a
shell-heavy OS image: ShellCheck at `--severity=error`, hadolint with
`--failure-threshold error`, CodeQL security-extended queries, zizmor with
medium-or-higher severity, fatal Python syntax parsing, fatal JSON/TOML parsing,
fatal Justfile syntax/format checks, and fatal unexpected systemd verifier
diagnostics. Full `shfmt -d` enforcement is documented for contributors but not
yet a CI gate because existing shell formatting drift is being handled
separately.

Evidence:

- `.github/workflows/validation.yml`
- `.github/workflows/codeql.yml`
- `CONTRIBUTING.md`
