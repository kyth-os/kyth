# shellcheck shell=bash
# ── SELinux preset (permissive + booleans) ───────────────────────────────
# selinux.toml hash-gated, offline semanage/setsebool guarded
if selinuxenabled 2>/dev/null; then
    : # selinux active, preset will apply via selinux_preset.apply_selinux at first boot
fi
