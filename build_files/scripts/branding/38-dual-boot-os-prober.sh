# shellcheck shell=bash
# ── Dual-boot: enable os-prober for the GRUB menu ─────────────────────────────
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
