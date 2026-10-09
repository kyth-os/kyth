# ── Shared variables ─────────────────────────────────────────────────────────
# Imported by Justfile and by build.just/vm.just/_internal.just directly, so
# each stays a valid standalone justfile. `just` deduplicates repeated imports
# of the same file, so importing this from both Justfile and its imports is
# safe — the variables are only ever defined once.

export image_name := env("IMAGE_NAME", "kyth")
export default_tag := env("DEFAULT_TAG", "latest")
export bib_image := env("BIB_IMAGE", "quay.io/centos-bootc/bootc-image-builder@sha256:2b52843ea2bfda73b0a08d97e76b734393b1d3a804681b9fabb26723bd3a2f0b")
# Default is digest-pinned to match build_base/Dockerfile for reproducible
# builds. Override via BASE_IMAGE env (must be digest-qualified).
export default_base_image := env("BASE_IMAGE", "quay.io/fedora/fedora-kinoite:45@sha256:38217fdbefe3363882b3e4b35b77b3bc3488b2ad848c57ac97ee7a16d2b9b204")
