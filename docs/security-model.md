# Security Model

This document describes what KythOS tries to protect, where its trust
boundaries are, and how the project argues that its security expectations are
met. It is a living document, not a completed third-party audit.

## Security Goals

- Users can obtain release artifacts over authenticated channels.
- Users can verify ISO and image provenance before installation.
- Installed systems can update atomically and roll back from bad deployments.
- The live installer does not expose disk-writing actions to the network.
- System Hub helpers avoid logging or publishing credentials and tokens.
- Public bug-reporting paths warn users not to include secrets.
- Vulnerability reports can be submitted privately.

## Non-Goals

- KythOS does not make incompatible Windows kernel anti-cheat work on Linux.
- KythOS does not protect users from intentionally installing untrusted software.
- KythOS does not replace upstream security support from Fedora, KDE, browser,
  driver, kernel, Flatpak, or package maintainers.
- KythOS does not claim that every optional third-party tool has been audited by
  the project.

## Assets

- Release artifacts: OCI images, ISO files, checksums, signatures, provenance,
  and SBOMs.
- Release credentials: GitHub tokens, R2 credentials, signing identity, optional
  Secure Boot signing material.
- User data: local files, installed games, VPN credentials, cloud tokens,
  network-share credentials, browser data, and migration data.
- Privileged operations: install-to-disk, update/rebase, Secure Boot enrollment,
  systemd unit management, mount creation, and repair actions.

## Trust Boundaries

### Source and CI

The GitHub repository and GitHub Actions workflows are trusted release inputs.
Workflows use explicit permissions where practical, pinned third-party actions,
source validation, keyless signing, and provenance attestations.

### Release Distribution

GHCR and GitHub releases are authoritative release channels. Cloudflare R2 is a
download mirror for ISO artifacts. Users should verify checksums, Cosign bundles,
and GitHub attestations as documented in `README.md`.

All external fetches (ublue-os base, RPMFusion/Terra/COPR, `umu`/`proton-cachyos` via `resolve-versions.py`) are digest-pinned by CI; `cosign verify` on the base image and Syft/Grype SBOM scans run on every build. Local `podman` builds reuse only layer cache, not CI remote cache — CI `build.yml` is the source of truth for supply-chain pinning.

### Live Installer

The installer serves a local web UI on `127.0.0.1`. It uses a session token for
state-changing requests and is designed for a live session where the user is
physically present. The main sensitive action is writing a target disk.

### System Hub and Runtime Helpers

System Hub is a local desktop application. It starts privileged operations
through installed helpers and standard authentication paths. Helpers should
validate inputs, quote shell arguments, avoid interpolating untrusted strings
into shell code where possible, and avoid logging secrets.

### Credentials and Tokens

Network-share passwords, cloud OAuth tokens, VPN credentials, BitLocker recovery
keys, and browser/session data are sensitive user data. Migration and diagnostic
tools should exclude or redact them by default.

## Dependency and Upstream Risk

KythOS is an integration project. It inherits much of its security posture from
Fedora, Universal Blue, KDE, bootc, GitHub Actions, and the package ecosystems
used to build the image. KythOS monitors dependencies through Renovate,
Dependabot, SBOM generation, and Grype CVE scans, then rebuilds to pick up fixed
upstream packages.

## Secure Design Practices

- Prefer upstream packages and standard system components over custom security
  mechanisms.
- Keep secrets in GitHub secrets or user-owned credential stores, not in source.
- Use HTTPS/TLS and signed release metadata for distribution.
- Use keyless Cosign signing and GitHub provenance for release identity.
- Keep privileged helpers small and purpose-specific.
- Prefer allowlisted options for installers, kernel flavors, channels, and
  helper commands.
- Treat user-provided logs and diagnostics as sensitive.
- Preserve rollback paths for risky OS changes.

## Known Risk Areas

- The project currently has a small maintainer base.
- Some validation requires real hardware and cannot be fully represented by CI.
- Optional third-party repositories and tools can change independently of KythOS.
- ISO and image builds include timestamps and upstream package state, so
  reproducibility must be documented carefully.
- Desktop automation flows sometimes interact with user credentials and must be
  reviewed conservatively.

## Assurance Case

KythOS meets its security goals through layered controls:

- Release integrity is supported by SHA-256 checksums, Cosign signatures,
  signature bundles, GitHub provenance attestations, and signed OCI artifacts.
- Supply-chain visibility is supported by Syft SBOM generation and Grype scans.
- Source risk is reduced by validation workflows, CodeQL, Scorecard, pinned
  workflow actions, ShellCheck, hadolint, systemd verification, and unit/fuzz
  tests.
- Runtime safety is supported by atomic `bootc` deployments, rollback,
  smoke-check tooling, SELinux enforcing, and conservative stable-channel
  promotion.
- Vulnerability handling is supported by private GitHub vulnerability reporting,
  documented response expectations, and advisory publication when users need to
  take action.

## Security Review Cadence

The threat model and assurance case should be reviewed at least annually and
whenever KythOS changes its installer, release pipeline, privileged helper
model, signing process, or credential-handling behavior.

For the OpenSSF Best Practices Passing security checklist, see
`docs/bestpractices-security.md`.
