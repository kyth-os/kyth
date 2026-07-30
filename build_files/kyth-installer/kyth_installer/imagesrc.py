"""Install-source image reference handling: transport detection, registry
reachability preflight, and kernel-flavor image derivation.
"""

import logging
import socket

from .config import SOURCE_IMAGE, TARGET_IMAGE
from .runner import run_command

_logger = logging.getLogger(__name__)


def _source_imgref(image: str) -> str:
    image = (image or "").strip()
    if not image:
        return SOURCE_IMAGE
    if image.startswith(("docker://", "containers-storage:", "oci:", "ostree:")):
        return image
    return f"docker://{image}"


def _imgref_needs_network(imgref: str) -> bool:
    return imgref.startswith("docker://")


def _registry_host(imgref: str) -> str:
    image = imgref.removeprefix("docker://")
    return image.split("/", 1)[0].split("@", 1)[0].rsplit(":", 1)[0]


def _friendly_network_error(extra: str = "") -> str:
    detail = f"\n\nDetails: {extra}" if extra else ""
    return (
        "KythOS needs an internet connection before it can install.\n\n"
        "Connect to Wi-Fi or plug in Ethernet from the live desktop, then return "
        "to this installer and click Start Install again. Your disk, account, "
        "timezone, and kernel choices will stay here while you connect.\n\n"
        "Tip: use the network icon in the bottom-right panel to join Wi-Fi."
        f"{detail}"
    )


def _network_preflight(imgref: str) -> str | None:
    """Return a friendly error message if the selected install source needs
    the network and the live session cannot reach its registry yet."""
    if not _imgref_needs_network(imgref):
        return None

    host = _registry_host(imgref)
    if not host:
        return _friendly_network_error("The selected image registry could not be determined.")

    try:
        route = run_command(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=3,
        )
        if route.returncode != 0 or not route.stdout.strip():
            return _friendly_network_error("No active default network route was found.")
    except Exception:
        # Keep going: DNS/connect checks below are a better user-facing signal.
        _logger.debug("_network_preflight: default-route check failed", exc_info=True)

    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return _friendly_network_error(
            f"The live session is not resolving {host}. Wi-Fi may not be connected yet."
        )
    except Exception as exc:
        return _friendly_network_error(f"DNS check for {host} failed: {exc}")

    try:
        with socket.create_connection((host, 443), timeout=5):
            return None
    except OSError:
        return _friendly_network_error(
            f"The live session cannot reach {host}:443 yet."
        )


def _install_images(kernel: str) -> tuple[str, str]:
    """Return (source_imgref, target_imgref) for bootc install based on kernel choice.

    Fedora uses the configured SOURCE_IMAGE/TARGET_IMAGE as-is (may be a local
    OCI transport for embedded ISOs).  CachyOS always pulls from the
    registry, deriving the tag by appending the kernel suffix to the base tag.
    """
    if kernel == "fedora":
        return _source_imgref(SOURCE_IMAGE), TARGET_IMAGE
    # Derive registry and base tag from TARGET_IMAGE, stripping any existing suffix.
    if ":" in TARGET_IMAGE:
        registry, tag = TARGET_IMAGE.rsplit(":", 1)
    else:
        registry, tag = TARGET_IMAGE, "latest"
    if tag.endswith("-cachy"):
        tag = tag[: -len("-cachy")]
    suffix = "-cachy"
    img = f"{registry}:{tag}{suffix}"
    return f"docker://{img}", img
