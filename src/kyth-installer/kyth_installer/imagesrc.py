"""Install-source image reference handling: transport detection, registry
reachability preflight, and kernel-flavor image derivation.
"""

import hashlib
import json
import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path

from .config import SOURCE_DIGEST, SOURCE_IMAGE, SOURCE_METADATA_FILE, TARGET_IMAGE
from .runner import run_command

_logger = logging.getLogger(__name__)

#: Override for the embedded cosign bundle (tests point this at a fixture).
def _signature_bundle_path() -> Path:
    return Path(os.environ.get("KYTH_SOURCE_SIGNATURE", "/usr/share/kyth/image.sig.bundle.json"))


def _registry_signed_source(source_image: str) -> bool:
    """True when the ISO build-time source needed a registry cosign signature.

    Loopback registries and non-registry transports are unsigned dev inputs;
    everything else must carry a verified signature bundle.
    """
    image = source_image.removeprefix("docker://")
    if image.startswith(("oci:", "containers-storage:", "dir:", "ostree:")):
        return False
    return not (
        image.startswith(("localhost:", "localhost/"))
        or image.startswith("127.0.0.1")
        or image.startswith("[::1]")
    )


def _valid_base64_signature(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 128 * 1024
        and all(char.isascii() and (char.isalnum() or char in "+/=") for char in value)
    )


def _verify_signature_bundle(
    digest: str,
    release_digest: str,
    metadata: dict,
    *,
    bundle_path: Path | None = None,
) -> None:
    """Verify the cosign signature bundle embedded at ISO build time.

    ``metadata["signature"]`` is ``"verified"`` for registry builds — the
    bundle file's sha256 must equal ``metadata["signature_digest"]`` and the
    bundle's subject digest must equal the release digest — or ``"local"``
    for unsigned loopback / non-registry dev sources. ``"local"`` is only
    accepted when the build-time source image itself is loopback/local; a
    registry image claiming to be local fails closed.
    """
    state = str(metadata.get("signature") or "")
    if state == "local":
        if _registry_signed_source(str(metadata.get("source_image") or "")):
            raise RuntimeError(
                "embedded image claims an unsigned local source but was built from a registry image"
            )
        return
    if state != "verified":
        raise RuntimeError("embedded-image metadata has an unknown signature state")
    path = bundle_path if bundle_path is not None else _signature_bundle_path()
    try:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"embedded signature bundle is missing or unsafe: {path}")
        raw = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"could not read embedded signature bundle: {exc}") from exc
    if len(raw) > 4 * 1024 * 1024:
        raise RuntimeError("embedded signature bundle is too large")
    calculated = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    expected = str(metadata.get("signature_digest") or "")
    if not expected or expected != calculated:
        raise RuntimeError(
            "embedded signature bundle does not match the digest pinned by this ISO release"
        )
    try:
        bundle = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"embedded signature bundle is invalid: {exc}") from exc
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
        raise RuntimeError("embedded signature bundle has an unsupported schema")
    if bundle.get("digest") != digest or bundle.get("release_digest") != release_digest:
        raise RuntimeError(
            "embedded signature bundle does not cover this ISO release digest"
        )
    signatures = bundle.get("signatures")
    if not signatures or not all(_valid_base64_signature(entry) for entry in signatures):
        raise RuntimeError(
            "embedded signature bundle carries no verifiable signature"
        )


@dataclass(frozen=True)
class ImageSource:
    """A source resolved and verified before any destructive disk operation."""

    source_ref: str
    target_ref: str
    kind: str
    digest: str = ""
    verified: bool = False

    @property
    def requires_network(self) -> bool:
        return _imgref_needs_network(self.source_ref)


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
        "This selected KythOS image needs an internet connection before it can install.\n\n"
        "Connect to Wi-Fi or plug in Ethernet from the live desktop, then return "
        "to this installer and click Start Install again. Your disk, account, "
        "timezone, and kernel choices will stay here while you connect.\n\n"
        "Tip: use the network icon in the bottom-right panel to join Wi-Fi."
        f"{detail}"
    )


def _oci_layout_ref(imgref: str) -> tuple[Path, str]:
    value = imgref.removeprefix("oci:")
    slash = value.rfind("/")
    colon = value.rfind(":")
    if colon > slash:
        return Path(value[:colon]), value[colon + 1 :] or "latest"
    return Path(value), "latest"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _read_source_metadata(path: Path = SOURCE_METADATA_FILE) -> dict:
    try:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"source metadata is missing or unsafe: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read embedded-image metadata: {exc}") from exc
    if payload.get("schema_version") != 1:
        raise RuntimeError("embedded-image metadata has an unsupported schema")
    return payload


def _verify_oci_source(
    imgref: str,
    *,
    expected_digest: str = SOURCE_DIGEST,
    metadata_path: Path = SOURCE_METADATA_FILE,
    bundle_path: Path | None = None,
) -> str:
    """Verify the selected OCI manifest blob and its release-pinned digest."""
    root, tag = _oci_layout_ref(imgref)
    try:
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError(f"embedded OCI layout is missing or unsafe: {root}")
        layout = json.loads((root / "oci-layout").read_text(encoding="utf-8"))
        index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read embedded OCI image: {exc}") from exc
    if layout.get("imageLayoutVersion") != "1.0.0":
        raise RuntimeError("embedded OCI image has an unsupported layout version")

    manifests = index.get("manifests") or []
    descriptor = next(
        (
            item for item in manifests
            if (item.get("annotations") or {}).get("org.opencontainers.image.ref.name") == tag
        ),
        manifests[0] if len(manifests) == 1 else None,
    )
    digest = str((descriptor or {}).get("digest") or "")
    if not digest.startswith("sha256:") or len(digest) != 71:
        raise RuntimeError("embedded OCI image has no valid manifest digest")
    manifest_blob = root / "blobs" / "sha256" / digest.removeprefix("sha256:")
    if manifest_blob.is_symlink() or not manifest_blob.is_file():
        raise RuntimeError("embedded OCI manifest blob is missing or unsafe")
    if _sha256_file(manifest_blob) != digest:
        raise RuntimeError("embedded OCI manifest failed its SHA-256 integrity check")

    metadata = _read_source_metadata(metadata_path)
    metadata_digest = str(metadata.get("digest") or "")
    configured_digest = expected_digest or metadata_digest
    if not configured_digest or configured_digest != digest or metadata_digest != digest:
        raise RuntimeError(
            "embedded OCI image does not match the digest pinned by this ISO release"
        )
    # The release digest is the ISO build's pinned expectation: manifest,
    # metadata, release, and configured digests must all agree, and the
    # build-time cosign bundle must still cover that digest.
    release_digest = str(metadata.get("release_digest") or "")
    if release_digest != digest:
        raise RuntimeError(
            "embedded OCI image does not match the release digest pinned by this ISO release"
        )
    _verify_signature_bundle(digest, release_digest, metadata, bundle_path=bundle_path)
    metadata_target = str(metadata.get("target_image") or "")
    if metadata_target and metadata_target != TARGET_IMAGE:
        raise RuntimeError("embedded-image metadata does not match the configured update target")
    return digest


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
    except (OSError, ValueError, RuntimeError) as exc:  # noqa: BLE001 -- narrow: ip route probe failures
        # Keep going: DNS/connect checks below are a better user-facing signal.
        _logger.debug("_network_preflight: default-route check failed: %s", exc, exc_info=True)

    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return _friendly_network_error(
            f"The live session is not resolving {host}. Wi-Fi may not be connected yet."
        )
    except OSError as exc:  # noqa: BLE001 -- narrow: DNS check failures are OSError subclasses
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


def resolve_install_source(kernel: str) -> ImageSource:
    """Resolve and validate the source before storage preparation begins."""
    source_ref, target_ref = _install_images(kernel)
    return resolve_source_refs(source_ref, target_ref)


_SOURCE_STATUS_CACHE: dict[str, dict] = {}


def source_status(kernel: str = "fedora") -> dict:
    """Return a support-safe source description for the installer UI."""
    if kernel in _SOURCE_STATUS_CACHE:
        return _SOURCE_STATUS_CACHE[kernel]
    try:
        source = resolve_install_source(kernel)
    except RuntimeError as exc:
        return {
            "available": False,
            "kind": "invalid",
            "verified": False,
            "requires_network": False,
            "digest": "",
            "message": str(exc),
        }
    result = {
        "available": True,
        "kind": source.kind,
        "verified": source.verified,
        "requires_network": source.requires_network,
        "digest": source.digest,
        "target_ref": source.target_ref,
        "message": (
            "Verified image embedded in this ISO"
            if source.kind == "embedded"
            else "Network image selected"
            if source.requires_network
            else "Local image selected"
        ),
    }
    _SOURCE_STATUS_CACHE[kernel] = result
    return result


def resolve_source_refs(source_ref: str, target_ref: str) -> ImageSource:
    """Validate already-selected refs; split out for orchestration tests."""
    if source_ref.startswith("oci:"):
        digest = _verify_oci_source(source_ref)
        return ImageSource(source_ref, target_ref, "embedded", digest, True)
    if source_ref.startswith(("containers-storage:", "ostree:")):
        return ImageSource(source_ref, target_ref, "local", SOURCE_DIGEST, bool(SOURCE_DIGEST))
    return ImageSource(source_ref, target_ref, "network", SOURCE_DIGEST, bool(SOURCE_DIGEST))
