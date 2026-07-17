"""Security toolbox helpers (Kali distrobox probe + command builders).

Pure — no Qt. UI lives in page_software_security.
"""
from __future__ import annotations

from .process import _run_command

DEFAULT_KALI_BOX = "kali"
DEFAULT_KALI_IMAGE = "docker.io/kalilinux/kali-rolling"

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


def is_socket_capable_kali_box(name: str = DEFAULT_KALI_BOX) -> bool:
    """True when Kali is rootful, privileged, and outside SELinux container_t."""
    result = _run_command(
        [
            "sudo", "-n", "podman", "inspect", name,
            "--format",
            "{{.ImageName}}\n{{.HostConfig.Privileged}}\n{{range .HostConfig.SecurityOpt}}{{.}} {{end}}",
        ],
        timeout=10,
    )
    if result is None or result.returncode != 0:
        return False
    lines = result.stdout.splitlines()
    image = lines[0] if len(lines) > 0 else ""
    privileged = lines[1] if len(lines) > 1 else ""
    security_opts = lines[2] if len(lines) > 2 else ""
    return "kali" in image and privileged == "true" and "label=disable" in security_opts


_is_socket_capable_kali_box = is_socket_capable_kali_box


def distrobox_create_command(
    name: str = DEFAULT_KALI_BOX,
    image: str = DEFAULT_KALI_IMAGE,
) -> list[str]:
    return [
        "distrobox", "create", "--root", "--image", image, "--name", name,
        "--additional-flags", "--privileged --security-opt label=disable",
    ]


def distrobox_enter_command(name: str = DEFAULT_KALI_BOX, *inner: str) -> list[str]:
    cmd = ["distrobox", "enter", "--root", name]
    if inner:
        cmd.append("--")
        cmd.extend(inner)
    return cmd


def distrobox_remove_commands(name: str = DEFAULT_KALI_BOX) -> list[list[str]]:
    """Stop/rm rootless and rootful attempts."""
    return [
        ["distrobox", "stop", name],
        ["distrobox", "rm", "-f", name],
        ["distrobox", "stop", "--root", name],
        ["distrobox", "rm", "-f", "--root", name],
    ]
