# shellcheck shell=bash
# ── Locale + IME preset ──────────────────────────────────────────────────
# locale.toml hash-gated, localectl + fcitx5, offline
if command -v localectl >/dev/null 2>&1; then
    : # locale preset applied via locale_preset.apply_locale at first boot
fi
