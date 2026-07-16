# shellcheck shell=bash
# ── Right-click "New Document" templates for Dolphin ─────────────────────────
# Any file placed in ~/Templates appears in Dolphin's right-click → Create New
# → Document menu. Seeding /etc/skel ensures every new user gets the templates
# on first login.
mkdir -p /etc/skel/Templates
printf '' >"/etc/skel/Templates/Plain Text.txt"
printf '# Title\n\n' >"/etc/skel/Templates/Markdown.md"
printf '#!/usr/bin/env bash\nset -euo pipefail\n\n' >"/etc/skel/Templates/Shell Script.sh"
printf '#!/usr/bin/env python3\n\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n' \
	>"/etc/skel/Templates/Python Script.py"
chmod +x /etc/skel/Templates/"Shell Script.sh"
chmod +x /etc/skel/Templates/"Python Script.py"

install -m 0755 /ctx/kyth-rclone-update /usr/bin/kyth-rclone-update
install -m 0755 /ctx/kyth-session-snapshot /usr/bin/kyth-session-snapshot
install -m 0755 /ctx/kyth-report-issue /usr/bin/kyth-report-issue
install -m 0755 /ctx/kyth-proton-cachyos-update /usr/bin/kyth-proton-cachyos-update
install -m 0755 /ctx/kyth-steam-game-export /usr/bin/kyth-steam-game-export
install -m 0644 /ctx/kyth-proton-cachyos-update.service /usr/lib/systemd/user/kyth-proton-cachyos-update.service
install -m 0644 /ctx/kyth-proton-cachyos-update.timer /usr/lib/systemd/user/kyth-proton-cachyos-update.timer
install -m 0644 /ctx/kyth-flathub-setup.service /usr/lib/systemd/system/kyth-flathub-setup.service
install -m 0644 /ctx/kyth-default-flatpaks.service /usr/lib/systemd/system/kyth-default-flatpaks.service
install -m 0440 /ctx/kyth-bootc-sudo /etc/sudoers.d/kyth-bootc
install -m 0440 /ctx/kyth-sched-sudo /etc/sudoers.d/kyth-sched
install -m 0755 /ctx/kyth-hw-setup /usr/bin/kyth-hw-setup
install -m 0644 /ctx/kyth-hw-setup.service /usr/lib/systemd/system/kyth-hw-setup.service

