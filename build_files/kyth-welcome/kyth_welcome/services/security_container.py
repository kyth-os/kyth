"""Kali container inspection and capability policy."""
from __future__ import annotations

from dataclasses import dataclass

from .process import _run_command

DEFAULT_KALI_BOX = "kali"
DEFAULT_KALI_IMAGE = "docker.io/kalilinux/kali-rolling"


@dataclass(frozen=True)
class KaliContainerInfo:
    image: str = ""
    privileged: bool = False
    security_options: tuple[str, ...] = ()

    @property
    def socket_capable(self) -> bool:
        return (
            "kali" in self.image
            and self.privileged
            and "label=disable" in self.security_options
        )


def parse_kali_inspect_output(output: str) -> KaliContainerInfo:
    """Parse the deliberately line-oriented Podman inspect format."""
    lines = output.splitlines()
    return KaliContainerInfo(
        image=lines[0].strip() if lines else "",
        privileged=len(lines) > 1 and lines[1].strip() == "true",
        security_options=tuple(lines[2].split()) if len(lines) > 2 else (),
    )


def inspect_kali_box(name: str = DEFAULT_KALI_BOX) -> KaliContainerInfo | None:
    result = _run_command(
        [
            "sudo", "-n", "podman", "inspect", name,
            "--format",
            "{{.ImageName}}\n{{.HostConfig.Privileged}}\n"
            "{{range .HostConfig.SecurityOpt}}{{.}} {{end}}",
        ],
        timeout=10,
    )
    if result is None or result.returncode != 0:
        return None
    return parse_kali_inspect_output(result.stdout)


def is_socket_capable_kali_box(name: str = DEFAULT_KALI_BOX) -> bool:
    info = inspect_kali_box(name)
    return info is not None and info.socket_capable
