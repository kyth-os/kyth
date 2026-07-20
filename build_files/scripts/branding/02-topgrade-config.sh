# shellcheck shell=bash
# ── Topgrade config for all new users ────────────────────────────────────────
# Disable rpm-ostree step: on a bootc system rpm-ostree upgrade pulls from the
# upstream Kinoite ostree remote, not the KythOS container registry.
# Replace it with a bootc upgrade custom step so topgrade does the right thing.
mkdir -p /etc/skel/.config
cat >/etc/skel/.config/topgrade.toml <<'TOPGRADEEOF'
[misc]
# system (dnf5) is read-only on bootc — disable it; bootc upgrade is used instead.
# distrobox: disabled because distrobox-upgrade --all fails without a PTY.
#   Update containers manually with: distrobox-upgrade --all
# containers: podman container updates fail on a bootc read-only system.
# toolbx: kyth-dev is managed via ujust, not topgrade; toolbx version-compat
#   checks will fail the whole topgrade run if the container needs recreation.
# helix: helix editor grammar/update checks fail on read-only system.
# topgrade is baked into the KythOS image; refresh it through image updates.
no_self_update = true
disable = ["system", "distrobox", "containers", "toolbx", "helix"]

[commands]
# -n makes sudo fail fast if it can't run non-interactively, rather than hanging
# waiting for a password. NOPASSWD is granted in /etc/sudoers.d/kyth-bootc.
"KythOS system update" = "sudo -n bootc upgrade"
"KythOS rclone update" = "sudo -n /usr/bin/kyth-rclone-update"
TOPGRADEEOF
