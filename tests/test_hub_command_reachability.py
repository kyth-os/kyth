"""Reachability audit for every /usr/bin/kyth-* binary the Hub can invoke.

The Hub (src/kyth-hub-web's Tauri backend) and the kyth-shared library it
links against are the whole "hub app" control surface described in
MIGRATION.md: every button ultimately resolves to a literal
"/usr/bin/kyth-<name>" (or "/usr/libexec/kyth-<name>") path string somewhere
in that source. If a button references a path nothing in the build ever
installs, it is broken on every real image regardless of what the Rust code
around it does — and that class of bug (kyth-windows-verify was a live
instance of it, see tests/test_python_packaging.py's
test_tunable_dispatcher_is_native_and_runs_once_after_all_binaries_are_copied)
is invisible to unit tests that only exercise the Rust logic in isolation.

This test builds the two sides of that check from source, the same way a
real build assembles them, and asserts nothing is invoked that isn't
installed by at least one of:
  * a Cargo `[[bin]]` target copied out by the Dockerfile's
    `COPY --from=hub-web-builder` lines,
  * one of the tunable dispatcher's 94 symlinks (build_files/config/
    tunables.toml, installed by build_files/scripts/tunable-dispatcher.sh),
  * a direct `install ... /usr/bin/kyth-<name>` line anywhere under
    build_files/scripts (the legacy-fixture / branding-fragment path).

Binaries invoked without a leading "/usr/bin/" prefix (relying on $PATH,
e.g. kyth-scx from the upstream scx-scheds package) are deliberately out of
scope: they are not built or installed by this repo at all, so there is no
in-repo "installed set" entry to check them against.
"""

from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HUB_TAURI_SRC = ROOT / "src/kyth-hub-web/src-tauri/src"
SHARED_SRC = ROOT / "src/kyth-shared-rs/src"
SHARED_CARGO = ROOT / "src/kyth-shared-rs/Cargo.toml"
TUNABLES_TOML = ROOT / "build_files/config/tunables.toml"
DOCKERFILE = ROOT / "Dockerfile"
SCRIPTS_ROOT = ROOT / "build_files/scripts"

BIN_PATH_RE = re.compile(r"/usr/(?:bin|libexec)/(kyth-[a-z0-9][a-z0-9-]*)")


def _rust_sources(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.rs") if path.is_file()]


class HubCommandReachabilityTest(unittest.TestCase):
    def test_every_invoked_kyth_binary_is_installed_somewhere(self):
        invoked: set[str] = set()
        for path in _rust_sources(HUB_TAURI_SRC) + _rust_sources(SHARED_SRC):
            text = path.read_text(errors="ignore")
            invoked.update(BIN_PATH_RE.findall(text))

        # A reachability audit over an empty invoked-set proves nothing;
        # guard against the extraction regex silently matching zero files
        # (e.g. a future source-tree rename breaking HUB_TAURI_SRC/SHARED_SRC).
        self.assertGreater(
            len(invoked), 20, "extraction found suspiciously few /usr/bin/kyth-* references"
        )

        installed: set[str] = set()

        cargo_text = SHARED_CARGO.read_text()
        installed.update(re.findall(r'(?m)^name = "(kyth-[a-z0-9-]+)"', cargo_text))

        with TUNABLES_TOML.open("rb") as stream:
            tunables = tomllib.load(stream)["tunables"]
        installed.update(f"kyth-{name}" for name in tunables)

        for script in SCRIPTS_ROOT.rglob("*.sh"):
            # install lines routinely wrap the destination onto a
            # continuation line ("install -m 0755 /ctx/foo \\\n\t/usr/libexec/foo");
            # join backslash-newlines before matching so those aren't missed.
            text = script.read_text(errors="ignore").replace("\\\n", " ")
            installed.update(
                re.findall(r"install\s+[^\n]*?" + BIN_PATH_RE.pattern, text)
            )

        dockerfile_text = DOCKERFILE.read_text()
        for line in dockerfile_text.splitlines():
            if line.startswith("COPY --from=hub-web-builder"):
                installed.update(BIN_PATH_RE.findall(line))

        missing = sorted(invoked - installed)
        self.assertEqual(
            missing,
            [],
            "Hub or kyth-shared references a /usr/bin(/libexec)/kyth-* path "
            "that no Cargo bin target, tunable-dispatcher entry, branding "
            "install line, or Dockerfile COPY installs: " + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
