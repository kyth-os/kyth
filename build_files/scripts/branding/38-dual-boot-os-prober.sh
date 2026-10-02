# shellcheck shell=bash
# ── Dual-boot: enable os-prober for the GRUB menu ─────────────────────────────
# NOTE (F45/bootc): this drop-in is currently INERT. bootc/ostree never runs
# grub2-mkconfig; the boot menu is bootupd's static grub.cfg plus BLS entries,
# so /etc/default/grub.d is never consumed and dual-boot entries never appear
# from this path. It is kept (harmless) as documentation of intent; a real
# dual-boot implementation needs BLS chainloader entries or bootupd config,
# not a grub.d drop-in. Users dual-booting today must use the firmware boot
# picker (F12/Esc).
# os-prober (installed in packages/05-baseline-desktop-tooling.sh) lets
# grub2-mkconfig detect other installed OSes (e.g. Windows Boot Manager on an
# alongside/resize_ntfs install) and add them to KythOS's own GRUB menu, so
# users get one boot picker instead of having to mash the firmware's own key
# (F12/Esc) to reach Windows. Fedora's grub2 package sources
# /etc/default/grub.d/*.cfg after /etc/default/grub, so this drop-in wins
# regardless of what the base image ships there.
write_config /etc/default/grub.d/50-kyth-os-prober.cfg <<'EOF'
GRUB_DISABLE_OS_PROBER=false
EOF
