"""Security toolbox helpers (Kali distrobox probe + command builders).

Pure — no Qt. UI lives in page_software_security_kali.
"""
from __future__ import annotations

import re

# pylint: disable=unused-import
from .security_container import (  # noqa: F401 — DEFAULT_KALI_IMAGE re-exported; see page_software_security.py
    DEFAULT_KALI_BOX,
    DEFAULT_KALI_IMAGE,
)
from .process import run_command

SEC_HOST_TOOLS = [
    {
        "flatpak": "org.wireshark.Wireshark",
        "name": "Wireshark",
        "desc": "Network packet capture and protocol analyser. Live capture and deep inspection of hundreds of protocols.",
        "launch": ["flatpak", "run", "org.wireshark.Wireshark"],
    },
    {
        "flatpak": "com.portswigger.BurpSuite",
        "name": "Burp Suite Community",
        "desc": "Web application security testing — proxy, scanner, intruder, repeater, and decoder.",
        "launch": ["flatpak", "run", "com.portswigger.BurpSuite"],
    },
]


def _is_socket_capable_kali_box(name: str = DEFAULT_KALI_BOX) -> bool:
    """Legacy patchable seam; new code should use ``security_container``."""
    result = run_command(
        [
            "sudo", "-n", "podman", "inspect", name, "--format",
            "{{.ImageName}}\n{{.HostConfig.Privileged}}\n"
            "{{range .HostConfig.SecurityOpt}}{{.}} {{end}}",
        ],
        timeout=10,
    )
    if result is None or result.returncode != 0:
        return False
    lines = result.stdout.splitlines()
    return (
        len(lines) >= 3 and "kali" in lines[0]
        and lines[1] == "true" and "label=disable" in lines[2]
    )


def is_socket_capable_kali_box(name: str = DEFAULT_KALI_BOX) -> bool:
    return _is_socket_capable_kali_box(name)


# Run once after any bulk `distrobox-export --app ...`: tags Kali-exported
# launchers with a distinct menu category, strips NoDisplay/OnlyShowIn/
# NotShowIn so they actually surface in the host menu, rewrites any
# pkexec/kdesu/gksu escalation to `sudo -E`, and repoints Zenmap through
# kyth-distrobox-root-launch. Lives in build_files/kyth-kali-desktop-fixup
# (installed to /usr/bin) so this GUI flow and the `ujust setup-kali-box`/
# `export-kali-apps` CLI recipes fix up launchers identically instead of
# each keeping an independently-drifting copy of this logic.
_DESKTOP_FILE_REWRITE_SCRIPT = "kyth-kali-desktop-fixup"


def build_kali_create_command(
    box_name: str, box_image: str, meta: str, has_gui: bool,
) -> list[str]:
    """Recreate the box if it exists but isn't rootful/privileged, install the
    chosen tool metapackage with debconf preseeded to avoid install-time
    prompts, grant the container user passwordless sudo, and (GUI tiers only)
    bulk-export .desktop launchers and fix them up for the host menu."""
    export_step = (
        f" && distrobox enter --root {box_name} --"
        r" bash -c 'for f in /usr/share/applications/*.desktop;"
        r" do app=$(basename $f .desktop);"
        r" distrobox-export --app $app 2>/dev/null || true; done'"
        "\n" + _DESKTOP_FILE_REWRITE_SCRIPT
    ) if has_gui else ""
    return [
        "bash", "-c",
        "set -euo pipefail\n"
        f"box={box_name!r}\n"
        f"image={box_image!r}\n"
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
        f"distrobox enter --root {box_name} -- bash -c \""
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
        f" && distrobox enter --root {box_name} -- bash -c \""
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


def build_kali_export_command(box_name: str) -> list[str]:
    """Bulk-export every .desktop file the container ships (exit 2 if none),
    grant passwordless sudo, then fix up the exported launchers for the host
    menu. Mirrors the GUI-tier export step in build_kali_create_command for a
    box that already exists."""
    return [
        "bash", "-c",
        f"distrobox enter --root {box_name} --"
        r" bash -c '"
        r"shopt -s nullglob; files=(/usr/share/applications/*.desktop);"
        r" if [ ${#files[@]} -eq 0 ]; then exit 2; fi;"
        r" n=0; for f in ${files[@]}; do"
        r"   app=$(basename $f .desktop);"
        r"   distrobox-export --app $app 2>&1 && n=$((n+1)) || echo skip: $app;"
        r" done; echo EXPORTED:$n'"
        "\n_rc=$?; [ \"$_rc\" -eq 2 ] && exit 2\n"
        f"distrobox enter --root {box_name} -- bash -c \""
        "echo '${USER} ALL=(root) NOPASSWD: ALL' "
        "| sudo tee /etc/sudoers.d/kali-user-nopasswd > /dev/null; "
        "sudo chmod 0440 /etc/sudoers.d/kali-user-nopasswd\"\n"
        + _DESKTOP_FILE_REWRITE_SCRIPT,
    ]


def build_kali_remove_command(box_name: str) -> list[str]:
    """Stop and remove both a rootless and rootful box by this name, forcing
    backend container removal if distrobox still lists it afterward, then
    delete any exported launchers pointing at it."""
    script = f"""
set -euo pipefail
box={box_name!r}
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
    return ["bash", "-c", script]


class KaliInstallProgressTracker:
    """Tracks distrobox Kali Linux installation log output and updates progress state.

    Pure logic — decoupled from PySide6 widgets.
    """

    def __init__(self) -> None:
        self.phase = 0
        self.total_packages = 0
        self.unpack_count = 0
        self.setup_count = 0
        self.progress_value = 2
        self.status_message: str | None = None

    def _set_status(self, val: str) -> bool:
        if self.status_message != val:
            self.status_message = val
            return True
        return False

    def _set_progress(self, val: int) -> bool:
        if self.progress_value != val:
            self.progress_value = val
            return True
        return False

    def _result(self, msg_changed: bool, progress_changed: bool) -> tuple[str | None, int | None]:
        return (
            self.status_message if msg_changed else None,
            self.progress_value if progress_changed else None,
        )

    def _parse_pull_phase(self, ln: str, lo: str) -> tuple[str | None, int | None] | None:
        """Phase 0/1: pulling the Kali image, storing its manifest, and
        creating the container. Returns None if `ln` doesn't match any
        pattern recognized in this phase, so the caller falls through to
        (None, None) instead of advancing phase/progress."""
        if any(
            k in lo
            for k in (
                "trying to pull",
                "pulling image",
                "getting image source",
                "copying blob",
                "copying config",
            )
        ):
            self.phase = 1
            if "copying blob" in lo:
                digest = ln.split()[-1] if ln.split() else ""
                short = digest[:19] if digest else ""
                msg = (
                    f"Pulling image layer {short}…"
                    if short
                    else "Pulling Kali image layers…"
                )
            elif "copying config" in lo:
                msg = "Pulling image config…"
            else:
                msg = "Pulling kalilinux/kali-rolling from registry…"
            msg_changed = self._set_status(msg)
            progress_changed = False
            if self.progress_value < 40:
                progress_changed = self._set_progress(self.progress_value + 1)
            return self._result(msg_changed, progress_changed)

        if "writing manifest" in lo or "storing signatures" in lo:
            self.phase = 1
            msg_changed = self._set_status("Storing image manifest…")
            progress_changed = self._set_progress(42)
            return self._result(msg_changed, progress_changed)

        if any(
            k in lo
            for k in (
                "container kali",
                "creating container",
                "starting container",
                "image is now available",
                "image already present",
            )
        ) or (self.phase == 1 and "distrobox" in lo and "creat" in lo):
            self.phase = 2
            msg_changed = self._set_status("Creating Kali distrobox container…")
            progress_changed = self._set_progress(max(self.progress_value, 44))
            return self._result(msg_changed, progress_changed)

        return None

    def _parse_bootstrap_phase(self, ln: str, lo: str) -> tuple[str | None, int | None]:
        """Phase 2: bootstrapping the base Kali environment."""
        msg_changed = False
        progress_changed = False
        if any(k in lo for k in ("installing basic", "bootstrapping", "reading package")):
            self.phase = 3
            msg_changed = self._set_status("Bootstrapping Kali environment…")
            progress_changed = self._set_progress(max(self.progress_value, 55))
        elif self.progress_value < 54:
            progress_changed = self._set_progress(self.progress_value + 1)
        return self._result(msg_changed, progress_changed)

    def _parse_package_list_phase(self, ln: str, lo: str) -> tuple[str | None, int | None]:
        """Phase 3: fetching/resolving the apt package list for the chosen
        metapackage, until apt reports how much it needs to download."""
        msg_changed = False
        progress_changed = False
        if any(
            k in lo
            for k in ("reading package lists", "building dependency", "reading state information")
        ):
            msg_changed |= self._set_status("Fetching Kali package lists…")
            if self.progress_value < 59:
                progress_changed |= self._set_progress(self.progress_value + 1)
        elif any(
            k in lo
            for k in ("following new package", "following additional", "will be installed")
        ):
            msg_changed |= self._set_status("Resolving package dependencies…")
            progress_changed |= self._set_progress(max(self.progress_value, 58))

        m = re.search(r"(\d+) newly installed", ln)
        if m:
            self.total_packages = int(m.group(1))

        m2 = re.search(r"need to get (.+?) of archives", ln, re.IGNORECASE)
        if m2:
            self.phase = 4
            size_str = m2.group(1)
            count_str = f" ({self.total_packages} packages)" if self.total_packages else ""
            msg_changed |= self._set_status(f"Downloading {size_str} of packages{count_str}…")
            progress_changed |= self._set_progress(max(self.progress_value, 60))
        elif "need to get" in lo and "archive" in lo:
            self.phase = 4
            msg_changed |= self._set_status("Downloading packages…")
            progress_changed |= self._set_progress(max(self.progress_value, 60))
        return self._result(msg_changed, progress_changed)

    def _parse_download_phase(self, ln: str, lo: str) -> tuple[str | None, int | None]:
        """Phase 4: downloading resolved packages (Get:N lines), until
        dpkg starts unpacking the first one."""
        msg_changed = False
        progress_changed = False
        m = re.match(r"Get:(\d+)\s+\S+\s+\S+\s+\S+\s+(\S+)", ln)
        if m:
            n = int(m.group(1))
            pkg = m.group(2)
            if self.total_packages > 0:
                frac = min(1.0, n / self.total_packages)
                progress_changed |= self._set_progress(max(self.progress_value, int(60 + frac * 15)))
                msg_changed |= self._set_status(f"Downloading {pkg}… ({n} / {self.total_packages})")
            else:
                if self.progress_value < 74:
                    progress_changed |= self._set_progress(self.progress_value + 1)
                msg_changed |= self._set_status(f"Downloading {pkg}…")

        if ln.startswith("Selecting previously") or ln.startswith("Preparing to unpack"):
            self.phase = 5
            total_str = f" / {self.total_packages}" if self.total_packages else ""
            msg_changed |= self._set_status(f"Unpacking packages… (0{total_str})")
            progress_changed |= self._set_progress(max(self.progress_value, 75))
        return self._result(msg_changed, progress_changed)

    def _parse_unpack_phase(self, ln: str, lo: str) -> tuple[str | None, int | None]:
        """Phase 5: dpkg unpacking downloaded packages, until the first
        `Setting up` line starts configuration."""
        msg_changed = False
        progress_changed = False
        if ln.startswith("Unpacking "):
            self.unpack_count += 1
            pkg = ln.split()[1] if len(ln.split()) > 1 else ""
            pkg = pkg.split(":")[0]
            total_str = f" / {self.total_packages}" if self.total_packages else ""
            msg_changed |= self._set_status(f"Unpacking {pkg}… ({self.unpack_count}{total_str})")
            if self.total_packages > 0:
                frac = min(1.0, self.unpack_count / self.total_packages)
                progress_changed |= self._set_progress(max(self.progress_value, int(75 + frac * 13)))
            elif self.progress_value < 87:
                progress_changed |= self._set_progress(self.progress_value + 1)

        if ln.startswith("Setting up "):
            self.phase = 6
            pkg = ln.split()[2] if len(ln.split()) > 2 else ""
            pkg = pkg.split(":")[0]
            self.setup_count = 1
            total_str = f" / {self.total_packages}" if self.total_packages else ""
            msg_changed |= self._set_status(f"Configuring {pkg}… (1{total_str})")
            if self.total_packages > 0:
                frac = min(1.0, 1 / self.total_packages)
                progress_changed |= self._set_progress(max(self.progress_value, int(88 + frac * 10)))
            else:
                progress_changed |= self._set_progress(max(self.progress_value, 88))
        return self._result(msg_changed, progress_changed)

    def _parse_configure_phase(self, ln: str, lo: str) -> tuple[str | None, int | None]:
        """Phase 6: dpkg configuring installed packages, then apt's
        post-install trigger processing."""
        msg_changed = False
        progress_changed = False
        if ln.startswith("Setting up "):
            self.setup_count += 1
            pkg = ln.split()[2] if len(ln.split()) > 2 else ""
            pkg = pkg.split(":")[0]
            total_str = f" / {self.total_packages}" if self.total_packages else ""
            msg_changed |= self._set_status(f"Configuring {pkg}… ({self.setup_count}{total_str})")
            if self.total_packages > 0:
                frac = min(1.0, self.setup_count / self.total_packages)
                progress_changed |= self._set_progress(max(self.progress_value, int(88 + frac * 10)))
            elif self.progress_value < 97:
                progress_changed |= self._set_progress(self.progress_value + 1)

        if "processing triggers" in lo:
            pkg_m = re.search(r"processing triggers for (\S+)", lo)
            trigger_pkg = pkg_m.group(1) if pkg_m else ""
            msg = (
                f"Running post-install triggers ({trigger_pkg})…"
                if trigger_pkg
                else "Running post-install triggers…"
            )
            msg_changed |= self._set_status(msg)
            progress_changed |= self._set_progress(max(self.progress_value, 98))

        return self._result(msg_changed, progress_changed)

    _PHASE_PARSERS = {
        2: "_parse_bootstrap_phase",
        3: "_parse_package_list_phase",
        4: "_parse_download_phase",
        5: "_parse_unpack_phase",
        6: "_parse_configure_phase",
    }

    def parse_line(self, ln: str) -> tuple[str | None, int | None]:
        lo = ln.lower()

        if self.phase <= 1:
            result = self._parse_pull_phase(ln, lo)
            return result if result is not None else (None, None)

        parser_name = self._PHASE_PARSERS.get(self.phase)
        if parser_name is None:
            return (None, None)
        return getattr(self, parser_name)(ln, lo)
