# shellcheck shell=bash
# ── OOMD tuned ───────────────────────────────────────────────────────────
# oomd.conf.d drop-in hash-gated, offline
mkdir -p /etc/systemd/oomd.conf.d 2>/dev/null || true
cat > /etc/systemd/oomd.conf.d/50-kyth.conf <<'OOMDEOF'
[OOM]
DefaultMemoryPressureLimit=50%
OOMDEOF
