#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


IMPORTANT_PACKAGES = [
    "kernel-cachyos",
    "kernel-cachyos-core",
    "mesa-dri-drivers",
    "mesa-vulkan-drivers",
    "libdrm",
    "gamescope",
    "mangohud",
    "vkBasalt",
    "pipewire",
    "wireplumber",
    "steam-devices",
    "asusctl",
    "supergfxctl",
]


def run(cmd: list[str], *, check: bool = True, cwd: str | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}"
        )
    return proc.stdout


def image_labels(image: str, digest: str) -> dict[str, str]:
    if not digest:
        return {}
    try:
        raw = run(
            [
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                f"{image}@{digest}",
                "--format",
                "{{ json .Image.Config.Labels }}",
            ]
        ).strip()
        if not raw:
            return {}
        return json.loads(raw)
    except Exception as exc:
        print(f"warning: could not inspect labels for {image}@{digest}: {exc}", file=sys.stderr)
        return {}


def find_sbom_digest(image: str, digest: str) -> str | None:
    if not digest:
        return None
    try:
        discovered = json.loads(
            run(["oras", "discover", "--format", "json", f"{image}@{digest}"])
        )
    except Exception as exc:
        print(f"warning: could not discover SBOM for {image}@{digest}: {exc}", file=sys.stderr)
        return None

    for referrer in discovered.get("referrers", []):
        artifact_type = referrer.get("artifactType", "")
        if "syft+json" in artifact_type or "spdx+json" in artifact_type:
            return referrer.get("digest")
    return None


def load_sbom(image: str, image_digest: str) -> dict | None:
    sbom_digest = find_sbom_digest(image, image_digest)
    if not sbom_digest:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        try:
            run(["oras", "pull", f"{image}@{sbom_digest}"], cwd=tmp)
        except Exception as exc:
            print(f"warning: could not pull SBOM {sbom_digest}: {exc}", file=sys.stderr)
            return None

        for entry in Path(tmp).iterdir():
            if entry.suffix == ".json":
                return json.loads(entry.read_text(encoding="utf-8"))
    return None


def rpm_packages(sbom: dict | None) -> dict[str, str]:
    if not sbom:
        return {}

    packages: dict[str, str] = {}
    for artifact in sbom.get("artifacts", []):
        if artifact.get("type") != "rpm":
            continue
        name = artifact.get("name")
        version = artifact.get("version")
        if not name or not version:
            continue
        packages[name] = normalize_version(version)
    return packages


def normalize_version(version: str) -> str:
    version = re.sub(r"^\d+:", "", version)
    version = re.sub(r"\.fc\d+(?=\.|$)", "", version)
    return version


def package_changes(previous: dict[str, str], current: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    added = []
    changed = []
    removed = []

    for name in sorted(set(previous) | set(current)):
        if name not in previous:
            added.append(name)
        elif name not in current:
            removed.append(name)
        elif previous[name] != current[name]:
            changed.append(name)

    return added, changed, removed


def table_for(names: list[str], previous: dict[str, str], current: dict[str, str], marker: str) -> str:
    rows = []
    for name in names:
        rows.append(
            f"| {marker} | `{name}` | {previous.get(name, '')} | {current.get(name, '')} |"
        )
    return "\n".join(rows)


def grype_cve_set(path: str | None) -> set[tuple[str, str]]:
    """Return (cve_id, package_name) pairs from a Grype JSON report."""
    if not path:
        return set()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        result: set[tuple[str, str]] = set()
        for match in data.get("matches", []):
            cve_id = match.get("vulnerability", {}).get("id", "")
            pkg = match.get("artifact", {}).get("name", "")
            if cve_id and pkg:
                result.add((cve_id, pkg))
        return result
    except Exception as exc:
        print(f"warning: could not parse grype output {path!r}: {exc}", file=sys.stderr)
        return set()


def security_section(grype_current: str | None, grype_previous: str | None) -> str:
    current = grype_cve_set(grype_current)
    previous = grype_cve_set(grype_previous)
    if not current and not previous:
        return ""

    lines: list[str] = ["### Security fixes", ""]
    if previous:
        fixed = sorted(previous - current)
        if fixed:
            lines += ["| CVE | Package |", "| --- | --- |"]
            for cve_id, pkg in fixed:
                lines.append(
                    f"| [{cve_id}](https://nvd.nist.gov/vuln/detail/{cve_id}) | `{pkg}` |"
                )
        else:
            lines.append("No CVEs resolved compared to the previous build.")
    else:
        lines.append(
            f"No previous scan to compare against — {len(current)} finding(s) currently "
            "tracked. Future releases will show a fixed-CVE diff."
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def commit_section(previous_labels: dict[str, str], current_sha: str) -> str:
    previous_sha = previous_labels.get("org.opencontainers.image.revision", "")
    if not previous_sha or not current_sha or previous_sha == current_sha:
        return ""

    try:
        output = run(
            [
                "git",
                "log",
                "--pretty=format:| `%h` | %s | %an |",
                f"{previous_sha}..{current_sha}",
            ]
        ).strip()
    except Exception as exc:
        print(f"warning: could not generate commit range: {exc}", file=sys.stderr)
        return ""

    if not output:
        return ""
    return "### Commits\n| Hash | Subject | Author |\n| --- | --- | --- |\n" + output + "\n\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--current-tag", required=True)
    parser.add_argument("--current-digest", required=True)
    parser.add_argument("--previous-digest", default="")
    parser.add_argument("--current-sha", required=True)
    parser.add_argument("--current-sbom-file", default="")
    parser.add_argument("--grype-current", default="")
    parser.add_argument("--grype-previous", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.current_sbom_file:
        try:
            current_sbom = json.loads(Path(args.current_sbom_file).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"warning: could not read --current-sbom-file: {exc}", file=sys.stderr)
            current_sbom = None
    else:
        current_sbom = load_sbom(args.image, args.current_digest)
    previous_sbom = load_sbom(args.image, args.previous_digest)
    current_packages = rpm_packages(current_sbom)
    previous_packages = rpm_packages(previous_sbom)
    previous_labels = image_labels(args.image, args.previous_digest)

    title = f"Kyth image `{args.current_tag}`"
    lines = [
        f"# {title}",
        "",
        f"Built from branch `{args.branch}` at commit `{args.current_sha[:12]}`.",
        "",
        f"Image: `{args.image}@{args.current_digest}`",
        "",
    ]

    if not current_packages:
        lines += [
            "No current SBOM package data was available for this build.",
            "",
        ]
    elif not previous_packages:
        lines += [
            "No previous SBOM was available to compare against. Future releases will include package-level diffs.",
            "",
            "### Major Packages",
            "| Name | Version |",
            "| --- | --- |",
        ]
        for name in IMPORTANT_PACKAGES:
            if name in current_packages:
                lines.append(f"| `{name}` | {current_packages[name]} |")
        lines.append("")
    else:
        added, changed, removed = package_changes(previous_packages, current_packages)
        important = [name for name in IMPORTANT_PACKAGES if name in set(added + changed + removed)]
        if important:
            lines += [
                "### Major Package Changes",
                "| | Name | Previous | New |",
                "| --- | --- | --- | --- |",
            ]
            for name in important:
                marker = "+" if name in added else "-" if name in removed else "~"
                lines.append(
                    f"| {marker} | `{name}` | {previous_packages.get(name, '')} | {current_packages.get(name, '')} |"
                )
            lines.append("")

        lines.append(commit_section(previous_labels, args.current_sha).rstrip())
        if lines[-1]:
            lines.append("")

        lines += [
            "### All RPM Changes",
            "| | Name | Previous | New |",
            "| --- | --- | --- | --- |",
        ]
        rendered = []
        rendered += table_for(added, previous_packages, current_packages, "+").splitlines()
        rendered += table_for(changed, previous_packages, current_packages, "~").splitlines()
        rendered += table_for(removed, previous_packages, current_packages, "-").splitlines()
        lines += rendered or ["| | No RPM package changes detected | | |"]
        lines.append("")

    sec = security_section(args.grype_current or None, args.grype_previous or None)
    if sec:
        lines.append(sec.rstrip())
        lines.append("")

    Path(args.output).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
