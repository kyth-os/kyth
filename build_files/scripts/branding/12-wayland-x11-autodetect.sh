# shellcheck shell=bash
# ── Wayland session + software-compose rescue (runs before PLM on every boot)
# kyth-configure-session rewrites 11-kyth-session.conf to Plasma Wayland so
# leftover SDDM DisplayServer=x11 drop-ins and [Last] Session=plasmax11 values
# migrate on reboot. kyth-greeter-compositor wraps kwin_wayland and enables
# QPainter/llvmpipe when there is no DRM render node, on live media, or with
# nomodeset. [Last] Session= in /var/lib/plasmalogin/state.conf (and leftover
# /var/lib/sddm/state.conf) plus ~/.dmrc X11 values are rewritten too.
# The helper fail-opens: a write error logs a warning and returns 0 so
# ExecStartPre cannot block the greeter — 10-kyth.conf still provides the
# Wayland default in that case.
install -m 0755 /ctx/kyth-configure-session /usr/bin/kyth-configure-session
install -m 0755 /ctx/kyth-greeter-compositor /usr/bin/kyth-greeter-compositor

write_config /usr/lib/systemd/system/plasmalogin.service.d/10-kyth-detect-session.conf <<'PLMDROPINEOF'
[Service]
EnvironmentFile=-/run/kyth-greeter.env
ExecStartPre=/usr/bin/kyth-configure-session
PLMDROPINEOF

# PLM starts kwin as a user unit. Wrap it so nomodeset/live/no-GPU get QPainter.
write_config /usr/lib/systemd/user/plasma-login-kwin_wayland.service.d/10-kyth-compose.conf <<'KWINDROPINEOF'
[Service]
EnvironmentFile=-/run/kyth-greeter.env
ExecStart=
ExecStart=/usr/bin/kyth-greeter-compositor --no-lockscreen --no-global-shortcuts --no-kactivities --inputmethod plasma-keyboard --locale1
KWINDROPINEOF
