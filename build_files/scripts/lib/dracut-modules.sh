# shellcheck shell=bash
# Sourced library fragment — caller owns `set -euo pipefail`; do not set here.
#
# Canonical dracut module list shared by every initramfs (re)build path.
# Source this file instead of hard-coding `--add` lists so a new module only
# needs to be added once:
#
#   source "${SCRIPT_DIR}/lib/dracut-modules.sh"   # or the /ctx|/src equivalent
#   dracut ... --add "${KYTH_DRACUT_MODULES}" ...
#
# KYTH_DRACUT_MODULES mirrors the `add_dracutmodules` line that
# build_base/plymouth/kyth-plymouth-configure writes to 99-kyth.conf, so
# explicit `--add` callers and conf-driven rebuilds (bootc first-deploy
# regeneration, `dracut --regenerate-all`) converge on the same module set.
#
# Consumers:
#   build_files/scripts/kernel-repair.sh
#   build_files/scripts/plymouth-initramfs.sh
#   build_files/scripts/repair-current-plymouth-initramfs.sh
#   installer/build.sh (plus KYTH_DRACUT_LIVE_EXTRA below)
#   build_base/build.sh (isolated Docker context — cannot bind-mount this
#     file, so it inlines the same list; keep in sync when editing here)
#   src/kyth-shared-rs/src/system/plymouth.rs (Rust cannot source shell —
#     keep KYTH_DRACUT_MODULES const in sync when editing here)

# shellcheck disable=SC2034  # consumed by the scripts that source this file
KYTH_DRACUT_MODULES="drm plymouth ostree kyth-plymouth"

# Live ISO only: squashfs root needs the dmsquash modules on top of the base
# set. Installed systems never boot from squashfs, so this stays out of
# KYTH_DRACUT_MODULES.
# shellcheck disable=SC2034
KYTH_DRACUT_LIVE_EXTRA="dmsquash-live dmsquash-live-autooverlay"
