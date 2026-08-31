# System Hub Rust release checklist

Use this checklist before shipping a KythOS image that makes the Rust/Slint
System Hub the default launcher. The checklist is intentionally separate from
the migration roadmap: a green Rust build does not by itself demonstrate
runtime parity on an installed image.

## Pre-build gates

- [x] Dashboard and Updates command ledger is present.
- [x] Frontend/Rust contract tests pass.
- [x] Rust command modules compile and their unit tests pass.
- [x] Privileged operations are allowlisted and validate inputs centrally.
- [x] Frontend confirms privileged and destructive actions without displaying
      BitLocker secrets.
- [ ] CI `hub-shell` job is green on the release commit.
- [ ] `npm ci` succeeds from the lockfile in a clean build environment.
- [ ] `cargo build --locked` succeeds for the Tauri shell and shared crate.
- [ ] The asset-embed assertion finds every built JS/CSS asset in the binary.

## Image and runtime gates

- [ ] The image contains `/usr/bin/kyth-hub-native` and the launcher selects it.
- [ ] `kyth-welcome-launch --page` routes to every destination and section.
- [ ] A second launch focuses the existing shell and forwards its page.
- [ ] Dashboard renders honest degraded states with probe services absent.
- [ ] Updates check, stage, rollback, and restart guidance are truthful.
- [ ] Guardian, Hardware, App Store, and Gaming actions complete or report
      bounded failures on a real installed image.
- [x] Native system-changing controls have an explicit two-step confirmation
      gate; secret-bearing and argument-bearing workflows remain withheld from
      the native surface until dedicated controls exist.
- [ ] Privileged actions require the expected local authorization and leave no
      secret in the UI status, audit detail, or process arguments.

## Python retirement gate

Do not delete or stop installing the Python Hub/services until all image and
runtime gates above pass on both stable and testing images. The Python pieces
that remain authorities or compatibility fallbacks are:

- `kyth-probe` and `kyth-guardian` headless services used by the Rust shell;
- the Python launcher fallback for old images without the Rust binary; and
- any workflow whose Rust command is not yet listed in the command ledger.

## Rollback triggers

Keep the Python launcher fallback and revert the Rust default if any of these
occur after an image build:

- the shell fails to start or does not render its embedded frontend;
- a deep link opens the wrong page or a second launch opens another window;
- a privileged action bypasses confirmation, leaks a secret, or executes an
  operation outside the allowlist; or
- an update, Guardian, hardware, application, or gaming workflow reports
  success before the underlying action has completed.

## Validation commands

The canonical CI/image gate is:

```text
build_files/scripts/check-hub-web-shell.sh
```

It runs the clean frontend install, production build, frontend/Rust contract
tests, shared Rust tests, Tauri build, and embedded-asset assertion.
