# Architecture

KythOS is a Fedora Kinoite-based bootc desktop image with a live ISO installer,
atomic updates, and a first-run System Hub for setup and repair.

## Major Components

### Container Image

The operating system is built as an OCI container image and published to GitHub
Container Registry. The image is based on Fedora Kinoite through Universal Blue
base images, then layered with KythOS packages, configuration, services,
helpers, branding, and desktop defaults.

### Base Image Layer

`build_base/` produces the base layer used by the final image. It handles kernel
flavor selection, boot splash assets, dracut configuration, display-manager
defaults, and low-level OS setup that should be shared by final images.

### Final OS Layer

`Dockerfile` builds the KythOS desktop image. It installs packages, copies
helper scripts from `build_files/`, enables systemd units and timers, configures
desktop defaults, and labels the image with source and release metadata.

### Live ISO Installer

`installer/` builds a live payload that boots into a graphical installer. The
installer writes a selected target disk using `bootc install to-disk`, creates
the local user, and installs the standard image offline from the live ISO. The
embedded OCI manifest is checked against release metadata before destructive
storage work (preflight fails closed if `verified` is false). A durable, redacted transaction record (`atomic_write_json` + fsync + parent fsync) tracks the source digest,
phase, safety checks, and outcome; browser progress resumes by event ID after a
temporary UI disconnect.

### System Hub

`build_files/kyth-welcome/` contains the Python/PySide6 System Hub. It provides
first-run setup, update controls, hardware status, gaming setup, software
install helpers, network-share and cloud-storage helpers, VPN flows, diagnostics,
and repair actions.

### Runtime Helpers

`build_files/` contains shell and Python helpers installed into the image, such
as smoke checks, update checks, performance profiles, gamescope wrappers,
controller checks, NVIDIA status checks, VPN helpers, and migration tools.

### CI/CD and Release Workflows

`.github/workflows/` validates source changes, builds images, builds live ISOs,
generates SBOM metadata, signs artifacts, creates provenance attestations, and
runs CVE scans.

## Data Flow

1. A commit lands on `testing` or `main`.
2. Validation checks parse workflows, shell, Python, configuration, systemd
   units, and Just recipes.
3. Build workflows produce OCI images with source labels and metadata.
4. Supply-chain workflows generate SBOMs, sign images and SBOMs, verify
   provenance, and publish image release notes.
5. Live ISO workflows build ISO artifacts from pinned source images, sign them,
   attest them, upload them, and publish channel and immutable releases.
6. Users install from the ISO or rebase/update using `bootc`.

## Trust Boundaries

- GitHub source repository and CI workflows are trusted release inputs.
- GitHub Actions OIDC identity is used for keyless signing and attestations.
- GHCR stores signed OCI image artifacts and attached SBOMs.
- Cloudflare R2 mirrors ISO downloads, while GitHub releases retain signed
  checksums, signature bundles, metadata, and provenance links.
- The live installer exposes a local-only web UI and uses a session token to
  protect installer actions from unrelated local browser requests.
- System Hub invokes privileged actions through narrowly scoped installed
  helpers and the platform's normal authentication paths.

## Update and Rollback Model

Installed systems update atomically through `bootc`. A new deployment is staged
before reboot. If a deployment fails, users can select a previous deployment
from the boot menu. This rollback model is a core design constraint for package,
kernel, installer, and release changes.

## Validation Model

KythOS uses multiple validation layers:

- Static validation for workflows, containers, shell, Python syntax, JSON, TOML,
  systemd units, and Just recipes.
- Python unit tests for pure parser/helper behavior.
- Fuzzing for selected System Hub parsers.
- Image build checks and `bootc container lint`.
- Live ISO build and QEMU boot paths for release confidence.
- Runtime smoke checks on installed systems.

## External Interfaces

- OCI image: `ghcr.io/kyth-os/kyth`.
- ISO downloads: stable and testing channel URLs documented in `README.md`.
- GitHub issues and discussions for public support and bug reporting.
- GitHub private vulnerability reporting for security reports.
- System Hub desktop UI and installed `ujust` commands for local administration.
