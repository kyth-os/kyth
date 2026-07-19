import re
import shutil

# __KYTH_GENERATED_IMPORTS__
from .core_base import _apply_install_badge, _restyle
from .services.launch import popen
from .services.security import _is_socket_capable_kali_box
from .services.software import Worker, _finish_worker
from .qt import (  # noqa: E501
    QButtonGroup, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QRadioButton,
    QTextEdit, Qt,
)
from .widgets import _make_card, _set_log_panel


class _KaliContainerMixin:
    """Kali Linux distrobox container lifecycle: create, enter, export apps, remove."""

    def _build_kali_card(self, layout):
        kali_card, kali_layout = _make_card()

        top_row = QHBoxLayout()
        title_lbl = QLabel("Kali Linux Toolbox")
        title_lbl.setObjectName("card-title")
        top_row.addWidget(title_lbl)
        top_row.addStretch()
        self._sec_badge = QLabel()
        self._sec_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(self._sec_badge)
        kali_layout.addLayout(top_row)

        desc = QLabel(
            "Creates a Kali Linux container via distrobox that shares your home directory. "
            "Choose a toolset below — the container image is shared regardless of tier."
        )
        desc.setObjectName("card-copy")
        desc.setWordWrap(True)
        kali_layout.addWidget(desc)

        self._sec_tool_group = QButtonGroup(self)
        self._sec_radio_headless = QRadioButton(
            "Headless  — kali-linux-headless  (~150 CLI tools: nmap, metasploit, hashcat, john, hydra, …)"
        )
        self._sec_radio_headless.setObjectName("card-copy")
        self._sec_radio_headless.setChecked(True)
        self._sec_radio_default = QRadioButton(
            "Default  — kali-linux-default  (headless + GUI tools: Zenmap, Autopsy, Faraday, legion, …)"
        )
        self._sec_radio_default.setObjectName("card-copy")
        self._sec_radio_everything = QRadioButton(
            "Everything  — kali-linux-everything  (every available Kali tool)"
        )
        self._sec_radio_everything.setObjectName("card-copy")
        for rb in (self._sec_radio_headless, self._sec_radio_default, self._sec_radio_everything):
            self._sec_tool_group.addButton(rb)
            kali_layout.addWidget(rb)

        self._sec_everything_warn = QLabel(
            "⚠  kali-linux-everything is extremely large — expect 15–20 GB or more of downloads "
            "and a very long install time. Only choose this if you need every available tool."
        )
        self._sec_everything_warn.setObjectName("card-copy")
        self._sec_everything_warn.setStyleSheet("color: #fbbf24; background: #241808; "
                                                "border: 1px solid #f59e0b; border-radius: 6px; "
                                                "padding: 6px 10px;")
        self._sec_everything_warn.setWordWrap(True)
        self._sec_everything_warn.hide()
        kali_layout.addWidget(self._sec_everything_warn)
        self._sec_radio_everything.toggled.connect(self._sec_everything_warn.setVisible)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._sec_create_btn = QPushButton("Create Kali Box")
        self._sec_create_btn.setObjectName("primary")
        self._sec_create_btn.clicked.connect(self._sec_create_box)
        btn_row.addWidget(self._sec_create_btn)
        self._sec_enter_btn = QPushButton("Launch Kali Terminal")
        self._sec_enter_btn.hide()
        self._sec_enter_btn.clicked.connect(self._sec_enter_box)
        btn_row.addWidget(self._sec_enter_btn)
        self._sec_export_btn = QPushButton("Export Apps to Menu")
        self._sec_export_btn.hide()
        self._sec_export_btn.clicked.connect(self._sec_export_apps)
        btn_row.addWidget(self._sec_export_btn)
        self._sec_remove_btn = QPushButton("Remove Box")
        self._sec_remove_btn.setObjectName("danger")
        self._sec_remove_btn.hide()
        self._sec_remove_btn.clicked.connect(self._sec_remove_box)
        btn_row.addWidget(self._sec_remove_btn)
        btn_row.addStretch()
        kali_layout.addLayout(btn_row)

        self._sec_status_lbl = QLabel()
        self._sec_status_lbl.setObjectName("subheading")
        self._sec_status_lbl.hide()
        kali_layout.addWidget(self._sec_status_lbl)

        self._sec_progress = QProgressBar()
        self._sec_progress.setRange(0, 100)
        self._sec_progress.setValue(0)
        self._sec_progress.hide()
        kali_layout.addWidget(self._sec_progress)

        self._sec_log_toggle = QPushButton("Show details")
        self._sec_log_toggle.setCheckable(True)
        self._sec_log_toggle.hide()
        self._sec_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._sec_log_toggle, self._sec_log, checked)
        )
        kali_layout.addWidget(self._sec_log_toggle)

        self._sec_log = QTextEdit()
        self._sec_log.document().setMaximumBlockCount(5000)
        self._sec_log.setReadOnly(True)
        self._sec_log.setMaximumHeight(150)
        self._sec_log.hide()
        kali_layout.addWidget(self._sec_log)

        layout.addWidget(kali_card)

    def _refresh_sec_kali_status(self):
        if not hasattr(self, "_sec_badge"):
            return
        installed = _is_socket_capable_kali_box(self._SEC_BOX_NAME)
        _apply_install_badge(self._sec_badge, installed,
                             ok_text="Installed", warn_text="Not Installed")
        self._sec_create_btn.setVisible(not installed)
        for rb in (self._sec_radio_headless, self._sec_radio_default, self._sec_radio_everything):
            rb.setVisible(not installed)
        self._sec_everything_warn.setVisible(not installed and self._sec_radio_everything.isChecked())
        self._sec_enter_btn.setVisible(installed)
        self._sec_export_btn.setVisible(installed)
        self._sec_remove_btn.setVisible(installed)

    def _sec_create_box(self):
        if self._sec_worker and self._sec_worker.isRunning():
            return

        if self._sec_radio_everything.isChecked():
            meta = "kali-linux-everything"
        elif self._sec_radio_default.isChecked():
            meta = "kali-linux-default"
        else:
            meta = "kali-linux-headless"
        self._sec_last_install_meta = meta
        has_gui = meta in ("kali-linux-default", "kali-linux-everything")

        self._sec_create_btn.setEnabled(False)
        for rb in (self._sec_radio_headless, self._sec_radio_default, self._sec_radio_everything):
            rb.setEnabled(False)
        self._sec_log.clear()
        sudo_note = (
            f"→ distrobox enter --root {self._SEC_BOX_NAME} -- configure passwordless sudo\n"
        )
        export_note = (
            f"→ distrobox enter --root {self._SEC_BOX_NAME} -- distrobox-export (bulk GUI apps)\n"
            "→ kbuildsycoca6 (refresh KDE application menu)\n"
        ) if has_gui else ""
        size_note = (
            "\n⚠ kali-linux-everything is very large — this may take a long time.\n"
        ) if meta == "kali-linux-everything" else (
            "\nThis pulls the Kali container image and installs the tool metapackage.\n"
            "The first run will take a few minutes depending on your connection.\n"
        )
        self._sec_log.append(
            f"→ distrobox create --root --image {self._SEC_BOX_IMAGE} --name {self._SEC_BOX_NAME}"
            f" --additional-flags '--privileged --security-opt label=disable'\n"
            f"→ distrobox enter --root {self._SEC_BOX_NAME} -- noninteractive apt-get install -y {meta}\n"
            + sudo_note + export_note + size_note
        )
        self._sec_log_toggle.show()
        _set_log_panel(self._sec_log_toggle, self._sec_log, False)
        self._sec_progress.setRange(0, 100)
        self._sec_progress.setValue(2)
        self._sec_progress.show()
        self._sec_status_lbl.setText("Pulling Kali container image…")
        self._sec_status_lbl.setObjectName("subheading")
        self._sec_status_lbl.show()
        _restyle(self._sec_status_lbl)
        self._sec_install_phase = 0
        self._sec_total_packages = 0
        self._sec_unpack_count = 0
        self._sec_setup_count = 0

        export_step = (
            f" && distrobox enter --root {self._SEC_BOX_NAME} --"
            r" bash -c 'for f in /usr/share/applications/*.desktop;"
            r" do app=$(basename $f .desktop);"
            r" distrobox-export --app $app 2>/dev/null || true; done'"
            "\n_d=\"$HOME/.local/share/applications\"\n"
            "for _f in \"$_d/\"*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali' \"$_f\" 2>/dev/null || continue\n"
            "    if grep -q '^Categories=' \"$_f\"; then\n"
            "        sed -i 's|^Categories=.*|Categories=X-KythSecurity;|' \"$_f\"\n"
            "    else\n"
            "        printf '\\nCategories=X-KythSecurity;\\n' >> \"$_f\"\n"
            "    fi\n"
            "    sed -i '/^NoDisplay[[:space:]]*=[[:space:]]*true/Id' \"$_f\"\n"
            "    sed -i '/^OnlyShowIn[[:space:]]*=/d' \"$_f\"\n"
            "    sed -i '/^NotShowIn[[:space:]]*=/d' \"$_f\"\n"
            "    if grep -qE 'pkexec|kdesu|gksu|gksudo' \"$_f\" 2>/dev/null; then\n"
            "        sed -i -E 's/(pkexec|kdesu|gksu|gksudo)[[:space:]]+/sudo -E /g' \"$_f\"\n"
            "    fi\n"
            "done\n"
            "for _f in \"$_d/\"*zenmap*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali' \"$_f\" 2>/dev/null || continue\n"
            "    grep -qiE '^Name=.*root|zenmap-root|su-to-zenmap|pkexec' \"$_f\" 2>/dev/null || continue\n"
            "    grep -q ' sudo ' \"$_f\" && continue\n"
            "    sed -i -E 's|[[:space:]]--[[:space:]]+| -- sudo -E |' \"$_f\"\n"
            "done\n"
            "for _f in \"$_d/\"*zenmap*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali|^Exec=.*sudo -E' \"$_f\" 2>/dev/null || continue\n"
            "    grep -qiE '^Name=.*root|zenmap-root|su-to-zenmap|pkexec|sudo -E' \"$_f\" 2>/dev/null || continue\n"
            "    sed -i -E 's|^Exec=.*$|Exec=kyth-distrobox-root-launch --root kali /usr/bin/zenmap|' \"$_f\"\n"
            "    sed -i -E 's|^TryExec=.*$|TryExec=kyth-distrobox-root-launch|' \"$_f\"\n"
            "done\n"
            "update-desktop-database \"$_d\" 2>/dev/null || true\n"
            "kbuildsycoca6 --noincremental 2>/dev/null || true"
        ) if has_gui else ""
        cmd = [
            "bash", "-c",
            "set -euo pipefail\n"
            f"box={self._SEC_BOX_NAME!r}\n"
            f"image={self._SEC_BOX_IMAGE!r}\n"
            "rootless_exists=0\n"
            "distrobox list --no-color 2>/dev/null | grep -q \"^${box}\\b\" && rootless_exists=1 || true\n"
            "if [[ \"${rootless_exists}\" -eq 1 ]]; then\n"
            "    echo \"Removing rootless ${box}; raw socket tools require a rootful Kali box...\"\n"
            "    distrobox stop \"${box}\" --yes 2>/dev/null || distrobox stop \"${box}\" 2>/dev/null || true\n"
            "    distrobox rm --force \"${box}\" 2>/dev/null || distrobox rm \"${box}\" --yes 2>/dev/null || true\n"
            "    podman rm -f \"${box}\" 2>/dev/null || true\n"
            "fi\n"
            "rootful_exists=0\n"
            "sudo -A podman inspect \"${box}\" >/dev/null 2>&1 && rootful_exists=1 || true\n"
            "if [[ \"${rootful_exists}\" -eq 1 ]]; then\n"
            "    _image=$(sudo -A podman inspect \"${box}\" --format '{{.ImageName}}' 2>/dev/null || true)\n"
            "    _privileged=$(sudo -A podman inspect \"${box}\" --format '{{.HostConfig.Privileged}}' 2>/dev/null || true)\n"
            "    _security_opts=$(sudo -A podman inspect \"${box}\" --format '{{range .HostConfig.SecurityOpt}}{{.}} {{end}}' 2>/dev/null || true)\n"
            "    if [[ \"${_image}\" != *kali* ]] || [[ \"${_privileged}\" != \"true\" ]] || [[ \"${_security_opts}\" != *label=disable* ]]; then\n"
            "        echo \"Recreating ${box} with privileged rootful networking and SELinux label disabled...\"\n"
            "        distrobox stop --root \"${box}\" --yes 2>/dev/null || distrobox stop --root \"${box}\" 2>/dev/null || true\n"
            "        distrobox rm --root --force \"${box}\" 2>/dev/null || distrobox rm --root \"${box}\" --yes 2>/dev/null || true\n"
            "        sudo -A podman rm -f \"${box}\" 2>/dev/null || true\n"
            "        rootful_exists=0\n"
            "    fi\n"
            "fi\n"
            "if [[ \"${rootful_exists}\" -eq 0 ]]; then\n"
            "    distrobox create --root --image \"${image}\" --name \"${box}\" --yes"
            " --additional-flags '--privileged --security-opt label=disable'\n"
            "fi\n"
            f"distrobox enter --root {self._SEC_BOX_NAME} -- bash -c \""
            "export DEBIAN_FRONTEND=noninteractive; "
            "(printf '%s\\n' "
            "'popularity-contest popularity-contest/participate boolean false' "
            "'encfs encfs/security-information boolean true' "
            "'encfs encfs/security-information seen true' "
            "'console-setup console-setup/charmap47 select UTF-8' "
            "'samba-common samba-common/dhcp boolean false' "
            "'macchanger macchanger/automatically_run boolean false' "
            "'kismet-capture-common kismet-capture-common/install-users string' "
            "'kismet-capture-common kismet-capture-common/install-setuid boolean true' "
            "'wireshark-common wireshark-common/install-setuid boolean true' "
            "'sslh sslh/inetd_or_standalone select standalone' "
            "| sudo debconf-set-selections) || true; "
            "sudo -E apt-get install -y "
            "-o Dpkg::Options::=--force-confdef "
            "-o Dpkg::Options::=--force-confold "
            f"{meta}\""
            f" && distrobox enter --root {self._SEC_BOX_NAME} -- bash -c \""
            "echo '${USER} ALL=(root) NOPASSWD: ALL' "
            "| sudo tee /etc/sudoers.d/kali-user-nopasswd > /dev/null; "
            "sudo chmod 0440 /etc/sudoers.d/kali-user-nopasswd; "
            "mkdir -p /root/.config/gtk-3.0; "
            "printf '[Settings]\\ngtk-icon-theme-name = hicolor\\n' > /root/.config/gtk-3.0/settings.ini; "
            "if command -v nmap >/dev/null 2>&1; then "
            "printf '#!/bin/sh\\nexec sudo /usr/bin/nmap \\\"\\$@\\\"\\n' | sudo tee /usr/local/bin/nmap > /dev/null; "
            "sudo chmod 755 /usr/local/bin/nmap; fi\""
            + export_step,
        ]
        self._sec_worker = Worker(cmd)
        self._sec_worker.line.connect(self._sec_on_create_line)
        self._sec_worker.done.connect(self._sec_on_create_done)
        self._sec_worker.start()

    def _sec_on_create_line(self, ln: str):
        self._sec_log.append(ln)
        self._sec_log.ensureCursorVisible()

        lo = ln.lower()
        phase = self._sec_install_phase

        if phase <= 1:
            if any(k in lo for k in (
                "trying to pull", "pulling image", "getting image source",
                "copying blob", "copying config",
            )):
                self._sec_install_phase = 1
                if "copying blob" in lo:
                    digest = ln.split()[-1] if ln.split() else ""
                    short = digest[:19] if digest else ""
                    msg = f"Pulling image layer {short}…" if short else "Pulling Kali image layers…"
                elif "copying config" in lo:
                    msg = "Pulling image config…"
                else:
                    msg = "Pulling kalilinux/kali-rolling from registry…"
                self._sec_status_lbl.setText(msg)
                _restyle(self._sec_status_lbl)
                cur = self._sec_progress.value()
                if cur < 40:
                    self._sec_progress.setValue(cur + 1)
                return
            if "writing manifest" in lo or "storing signatures" in lo:
                self._sec_install_phase = 1
                self._sec_status_lbl.setText("Storing image manifest…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(42)
                return
            if any(k in lo for k in (
                "container kali", "creating container", "starting container",
                "image is now available", "image already present",
            )) or (phase == 1 and "distrobox" in lo and "creat" in lo):
                self._sec_install_phase = 2
                self._sec_status_lbl.setText("Creating Kali distrobox container…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 44))
                return

        if phase == 2:
            if any(k in lo for k in ("installing basic", "bootstrapping", "reading package")):
                self._sec_install_phase = 3
                self._sec_status_lbl.setText("Bootstrapping Kali environment…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 55))
            else:
                cur = self._sec_progress.value()
                if cur < 54:
                    self._sec_progress.setValue(cur + 1)
            return

        if phase == 3:
            if any(k in lo for k in ("reading package lists", "building dependency",
                                     "reading state information")):
                self._sec_status_lbl.setText("Fetching Kali package lists…")
                _restyle(self._sec_status_lbl)
                cur = self._sec_progress.value()
                if cur < 59:
                    self._sec_progress.setValue(cur + 1)
            elif any(k in lo for k in ("following new package", "following additional",
                                       "will be installed")):
                self._sec_status_lbl.setText("Resolving package dependencies…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 58))
            m = re.search(r'(\d+) newly installed', ln)
            if m:
                self._sec_total_packages = int(m.group(1))
            m2 = re.search(r'Need to get (.+?) of archives', ln, re.IGNORECASE)
            if m2:
                self._sec_install_phase = 4
                size_str = m2.group(1)
                count_str = f" ({self._sec_total_packages} packages)" if self._sec_total_packages else ""
                self._sec_status_lbl.setText(f"Downloading {size_str} of packages{count_str}…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 60))
            elif "need to get" in lo and "archive" in lo:
                self._sec_install_phase = 4
                self._sec_status_lbl.setText("Downloading packages…")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 60))
            return

        if phase == 4:
            m = re.match(r'Get:(\d+)\s+\S+\s+\S+\s+\S+\s+(\S+)', ln)
            if m:
                n = int(m.group(1))
                pkg = m.group(2)
                if self._sec_total_packages > 0:
                    frac = min(1.0, n / self._sec_total_packages)
                    self._sec_progress.setValue(max(self._sec_progress.value(),
                                                   int(60 + frac * 15)))
                    self._sec_status_lbl.setText(
                        f"Downloading {pkg}… ({n} / {self._sec_total_packages})"
                    )
                else:
                    cur = self._sec_progress.value()
                    if cur < 74:
                        self._sec_progress.setValue(cur + 1)
                    self._sec_status_lbl.setText(f"Downloading {pkg}…")
                _restyle(self._sec_status_lbl)
            if ln.startswith("Selecting previously") or ln.startswith("Preparing to unpack"):
                self._sec_install_phase = 5
                total_str = f" / {self._sec_total_packages}" if self._sec_total_packages else ""
                self._sec_status_lbl.setText(f"Unpacking packages… (0{total_str})")
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 75))
            return

        if phase == 5:
            if ln.startswith("Unpacking "):
                self._sec_unpack_count += 1
                pkg = ln.split()[1] if len(ln.split()) > 1 else ""
                pkg = pkg.split(":")[0]
                total_str = f" / {self._sec_total_packages}" if self._sec_total_packages else ""
                self._sec_status_lbl.setText(
                    f"Unpacking {pkg}… ({self._sec_unpack_count}{total_str})"
                )
                _restyle(self._sec_status_lbl)
                if self._sec_total_packages > 0:
                    frac = min(1.0, self._sec_unpack_count / self._sec_total_packages)
                    self._sec_progress.setValue(max(self._sec_progress.value(),
                                                   int(75 + frac * 13)))
                else:
                    cur = self._sec_progress.value()
                    if cur < 87:
                        self._sec_progress.setValue(cur + 1)
            if ln.startswith("Setting up "):
                self._sec_install_phase = 6
                pkg = ln.split()[2] if len(ln.split()) > 2 else ""
                pkg = pkg.split(":")[0]
                self._sec_setup_count = 1
                total_str = f" / {self._sec_total_packages}" if self._sec_total_packages else ""
                self._sec_status_lbl.setText(f"Configuring {pkg}… (1{total_str})")
                _restyle(self._sec_status_lbl)
                if self._sec_total_packages > 0:
                    frac = min(1.0, 1 / self._sec_total_packages)
                    self._sec_progress.setValue(max(self._sec_progress.value(),
                                                   int(88 + frac * 10)))
                else:
                    self._sec_progress.setValue(max(self._sec_progress.value(), 88))
            return

        if phase == 6:
            if ln.startswith("Setting up "):
                self._sec_setup_count += 1
                pkg = ln.split()[2] if len(ln.split()) > 2 else ""
                pkg = pkg.split(":")[0]
                total_str = f" / {self._sec_total_packages}" if self._sec_total_packages else ""
                self._sec_status_lbl.setText(
                    f"Configuring {pkg}… ({self._sec_setup_count}{total_str})"
                )
                _restyle(self._sec_status_lbl)
                if self._sec_total_packages > 0:
                    frac = min(1.0, self._sec_setup_count / self._sec_total_packages)
                    self._sec_progress.setValue(max(self._sec_progress.value(),
                                                   int(88 + frac * 10)))
                else:
                    cur = self._sec_progress.value()
                    if cur < 97:
                        self._sec_progress.setValue(cur + 1)
            if "processing triggers" in lo:
                pkg_m = re.search(r'processing triggers for (\S+)', lo)
                trigger_pkg = pkg_m.group(1) if pkg_m else ""
                msg = f"Running post-install triggers ({trigger_pkg})…" if trigger_pkg else "Running post-install triggers…"
                self._sec_status_lbl.setText(msg)
                _restyle(self._sec_status_lbl)
                self._sec_progress.setValue(max(self._sec_progress.value(), 98))

    def _sec_on_create_done(self, code: int):
        self._sec_progress.setValue(100)
        self._sec_progress.hide()
        _finish_worker(self, attr="_sec_worker")
        self._sec_create_btn.setEnabled(True)
        for rb in (self._sec_radio_headless, self._sec_radio_default, self._sec_radio_everything):
            rb.setEnabled(True)
        if code == 0:
            meta = getattr(self, "_sec_last_install_meta", "kali-linux-headless")
            if meta in ("kali-linux-default", "kali-linux-everything"):
                self._sec_status_lbl.setText(
                    "Kali box created. GUI apps exported — check your application menu."
                )
            else:
                self._sec_status_lbl.setText("Kali box created. Launch a terminal to start hacking.")
            self._sec_status_lbl.setObjectName("status-ok")
            self._sec_log.append("\nDone.")
        else:
            self._sec_status_lbl.setText(f"Setup failed (exit {code}). Check the details below.")
            self._sec_status_lbl.setObjectName("status-err")
        _restyle(self._sec_status_lbl)
        self._refresh_sec_kali_status()

    def _sec_enter_box(self):
        terminal = None
        for cmd in (["konsole"], ["xdg-terminal-exec"], ["xterm"]):
            if shutil.which(cmd[0]):
                terminal = cmd[0]
                break
        if terminal is None:
            QMessageBox.warning(self, "Terminal not found",
                                "Could not find a terminal emulator to open.")
            return
        if terminal == "konsole":
            popen(["konsole", "-e", "distrobox", "enter", "--root", self._SEC_BOX_NAME])
        else:
            popen([terminal, "--", "distrobox", "enter", "--root", self._SEC_BOX_NAME])

    def _sec_export_apps(self):
        if self._sec_worker and self._sec_worker.isRunning():
            return
        self._sec_export_count = 0
        self._sec_export_btn.setEnabled(False)
        self._sec_enter_btn.setEnabled(False)
        self._sec_remove_btn.setEnabled(False)
        self._sec_log.clear()
        self._sec_log.append(
            f"→ distrobox enter --root {self._SEC_BOX_NAME} -- distrobox-export (bulk GUI apps)\n"
            f"→ distrobox enter --root {self._SEC_BOX_NAME} -- configure passwordless sudo\n"
            "→ kbuildsycoca6 (refresh KDE application menu)\n\n"
            "Scanning Kali container for GUI apps…\n"
        )
        self._sec_log_toggle.show()
        _set_log_panel(self._sec_log_toggle, self._sec_log, False)
        self._sec_progress.show()
        self._sec_status_lbl.setText("Scanning for GUI apps…")
        self._sec_status_lbl.setObjectName("subheading")
        self._sec_status_lbl.show()
        _restyle(self._sec_status_lbl)

        cmd = [
            "bash", "-c",
            f"distrobox enter --root {self._SEC_BOX_NAME} --"
            r" bash -c '"
            r"shopt -s nullglob; files=(/usr/share/applications/*.desktop);"
            r" if [ ${#files[@]} -eq 0 ]; then exit 2; fi;"
            r" n=0; for f in ${files[@]}; do"
            r"   app=$(basename $f .desktop);"
            r"   distrobox-export --app $app 2>&1 && n=$((n+1)) || echo skip: $app;"
            r" done; echo EXPORTED:$n'"
            "\n_rc=$?; [ \"$_rc\" -eq 2 ] && exit 2\n"
            f"distrobox enter --root {self._SEC_BOX_NAME} -- bash -c \""
            "echo '${USER} ALL=(root) NOPASSWD: ALL' "
            "| sudo tee /etc/sudoers.d/kali-user-nopasswd > /dev/null; "
            "sudo chmod 0440 /etc/sudoers.d/kali-user-nopasswd\"\n"
            "_d=\"$HOME/.local/share/applications\"\n"
            "for _f in \"$_d/\"*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali' \"$_f\" 2>/dev/null || continue\n"
            "    if grep -q '^Categories=' \"$_f\"; then\n"
            "        sed -i 's|^Categories=.*|Categories=X-KythSecurity;|' \"$_f\"\n"
            "    else\n"
            "        printf '\\nCategories=X-KythSecurity;\\n' >> \"$_f\"\n"
            "    fi\n"
            "    sed -i '/^NoDisplay[[:space:]]*=[[:space:]]*true/Id' \"$_f\"\n"
            "    sed -i '/^OnlyShowIn[[:space:]]*=/d' \"$_f\"\n"
            "    sed -i '/^NotShowIn[[:space:]]*=/d' \"$_f\"\n"
            "    if grep -qE 'pkexec|kdesu|gksu|gksudo' \"$_f\" 2>/dev/null; then\n"
            "        sed -i -E 's/(pkexec|kdesu|gksu|gksudo)[[:space:]]+/sudo -E /g' \"$_f\"\n"
            "    fi\n"
            "done\n"
            "for _f in \"$_d/\"*zenmap*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali' \"$_f\" 2>/dev/null || continue\n"
            "    grep -qiE '^Name=.*root|zenmap-root|su-to-zenmap|pkexec' \"$_f\" 2>/dev/null || continue\n"
            "    grep -q ' sudo ' \"$_f\" && continue\n"
            "    sed -i -E 's|[[:space:]]--[[:space:]]+| -- sudo -E |' \"$_f\"\n"
            "done\n"
            "for _f in \"$_d/\"*zenmap*.desktop; do\n"
            "    [[ -f \"$_f\" ]] || continue\n"
            "    grep -qE -- '--name kali|-n kali|^Exec=.*sudo -E' \"$_f\" 2>/dev/null || continue\n"
            "    grep -qiE '^Name=.*root|zenmap-root|su-to-zenmap|pkexec|sudo -E' \"$_f\" 2>/dev/null || continue\n"
            "    sed -i -E 's|^Exec=.*$|Exec=kyth-distrobox-root-launch --root kali /usr/bin/zenmap|' \"$_f\"\n"
            "    sed -i -E 's|^TryExec=.*$|TryExec=kyth-distrobox-root-launch|' \"$_f\"\n"
            "done\n"
            "update-desktop-database \"$_d\" 2>/dev/null || true\n"
            "kbuildsycoca6 --noincremental 2>/dev/null || true",
        ]
        self._sec_worker = Worker(cmd)
        self._sec_worker.line.connect(self._sec_on_export_line)
        self._sec_worker.done.connect(self._sec_on_export_done)
        self._sec_worker.start()

    def _sec_on_export_line(self, ln: str):
        if ln.startswith("EXPORTED:"):
            try:
                self._sec_export_count = int(ln.split(":", 1)[1].strip())
            except ValueError:
                pass
        else:
            self._sec_log.append(ln)
            self._sec_log.ensureCursorVisible()

    def _sec_on_export_done(self, code: int):
        self._sec_progress.hide()
        _finish_worker(self, attr="_sec_worker")
        self._sec_export_btn.setEnabled(True)
        self._sec_enter_btn.setEnabled(True)
        self._sec_remove_btn.setEnabled(True)
        if code == 2:
            self._sec_status_lbl.setText(
                "No GUI apps found. kali-linux-headless only includes CLI tools. "
                "Re-create the box with 'Default' or 'Everything' to get exportable GUI apps."
            )
            self._sec_status_lbl.setObjectName("status-err")
            self._sec_log.append(
                "\nNo .desktop files found inside the Kali container.\n"
                "kali-linux-headless does not ship GUI apps — there is nothing to export.\n"
                "To get GUI apps (Zenmap, Autopsy, Faraday, etc.), remove this box and\n"
                "re-create it with the 'Default' or 'Everything' tier."
            )
        elif code == 0:
            n = getattr(self, "_sec_export_count", 0)
            if n == 0:
                self._sec_status_lbl.setText(
                    "No GUI apps exported. kali-linux-headless contains CLI tools only — "
                    "remove this box and re-create it with 'Default' or 'Everything' "
                    "to get exportable GUI apps (Zenmap, Autopsy, Faraday, etc.)."
                )
                self._sec_status_lbl.setObjectName("status-err")
                _set_log_panel(self._sec_log_toggle, self._sec_log, True)
            else:
                self._sec_status_lbl.setText(
                    f"Exported {n} app(s) — they should appear in your application menu shortly. "
                    "If you don't see them, try logging out and back in."
                )
                self._sec_status_lbl.setObjectName("status-ok")
            self._sec_log.append("\nDone.")
        else:
            self._sec_status_lbl.setText(f"Export failed (exit {code}). Check the details below.")
            self._sec_status_lbl.setObjectName("status-err")
        _restyle(self._sec_status_lbl)

    def _sec_remove_box(self):
        if self._sec_worker and self._sec_worker.isRunning():
            return
        reply = QMessageBox.question(
            self, "Remove Kali Box",
            "Remove the Kali distrobox container?\n\nFiles in your home directory are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._sec_enter_btn.setEnabled(False)
        self._sec_remove_btn.setEnabled(False)
        self._sec_log.clear()
        self._sec_log.append(
            f"→ distrobox stop/rm {self._SEC_BOX_NAME} (rootless and rootful)\n"
            "→ verify removal and clean exported launchers\n"
        )
        self._sec_log_toggle.show()
        _set_log_panel(self._sec_log_toggle, self._sec_log, False)
        self._sec_progress.show()
        self._sec_status_lbl.setText("Stopping and removing Kali box…")
        self._sec_status_lbl.setObjectName("subheading")
        self._sec_status_lbl.show()
        _restyle(self._sec_status_lbl)

        remove_script = f"""
set -euo pipefail
box={self._SEC_BOX_NAME!r}
appdir="${{HOME}}/.local/share/applications"

echo "Stopping ${{box}} if it is running..."
distrobox stop "${{box}}" --yes 2>/dev/null \
    || distrobox stop "${{box}}" 2>/dev/null \
    || true
distrobox stop --root "${{box}}" --yes 2>/dev/null \
    || distrobox stop --root "${{box}}" 2>/dev/null \
    || true

echo "Removing ${{box}}..."
distrobox rm --force "${{box}}" \
    || distrobox rm "${{box}}" --yes \
    || true
distrobox rm --root --force "${{box}}" 2>/dev/null \
    || distrobox rm --root "${{box}}" --yes 2>/dev/null \
    || true

if distrobox list --no-color 2>/dev/null | grep -q "^${{box}}\\b" \
    || sudo -A podman inspect "${{box}}" >/dev/null 2>&1; then
    echo "Distrobox still lists ${{box}}; forcing backend container removal..."
    if command -v podman >/dev/null 2>&1; then
        podman rm -f "${{box}}" 2>/dev/null || true
        sudo -A podman rm -f "${{box}}" 2>/dev/null || true
    fi
    if command -v docker >/dev/null 2>&1; then
        docker rm -f "${{box}}" 2>/dev/null || true
    fi
fi

if distrobox list --no-color 2>/dev/null | grep -q "^${{box}}\\b" \
    || sudo -A podman inspect "${{box}}" >/dev/null 2>&1; then
    echo "ERROR: ${{box}} still exists after removal attempts." >&2
    exit 1
fi

if [[ -d "${{appdir}}" ]]; then
    removed=0
    while IFS= read -r -d "" f; do
        if grep -qE -- "--name[[:space:]]+${{box}}|-n[[:space:]]+${{box}}|kyth-distrobox-root-launch[[:space:]]+${{box}}\\b" "$f" 2>/dev/null; then
            rm -f "$f"
            removed=$((removed + 1))
        fi
    done < <(find "${{appdir}}" -maxdepth 1 -type f -name "*.desktop" -print0)
    echo "Removed ${{removed}} exported launcher(s)."
fi

update-desktop-database "${{appdir}}" 2>/dev/null || true
kbuildsycoca6 --noincremental 2>/dev/null || true
echo "Kali box is stopped and removed."
"""
        self._sec_worker = Worker(["bash", "-c", remove_script])
        self._sec_worker.line.connect(lambda ln: (
            self._sec_log.append(ln),
            self._sec_log.ensureCursorVisible(),
        ))
        self._sec_worker.done.connect(self._sec_on_remove_done)
        self._sec_worker.start()

    def _sec_on_remove_done(self, code: int):
        self._sec_progress.hide()
        _finish_worker(self, attr="_sec_worker")
        self._sec_enter_btn.setEnabled(True)
        self._sec_remove_btn.setEnabled(True)
        if code == 0:
            self._sec_status_lbl.setText("Kali box removed.")
            self._sec_status_lbl.setObjectName("status-ok")
            self._sec_log.append("\nDone.")
        else:
            self._sec_status_lbl.setText(f"Removal failed (exit {code}).")
            self._sec_status_lbl.setObjectName("status-err")
        _restyle(self._sec_status_lbl)
        self._refresh_sec_kali_status()
