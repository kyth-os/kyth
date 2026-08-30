"""Hub deep links — every --page key that ships must resolve.

kyth-welcome-launch forwards `--page KEY` unchanged to whichever Hub is
installed. The native Slint shell and the compatibility Tauri shell both
consume the same argument. Nothing in
that chain validates the key: an unknown one falls back to "/" and silently
opens Home instead of the requested page. That is how `--page "App Store"`
(shipped in 23-kyth-helper-ctx-installs.sh) and 19 krunner entries regressed
when deepLink.ts's route table only listed the rail destinations.

deepLink.ts derives its table from data/destinations.ts, which in turn
lists the section arrays from hubSections.ts, so checking the data source
covers every emitted key is enough — and it stays stable across refactors
of the mapping code itself, which parsing the TS logic would not.
"""
from __future__ import annotations

import pathlib
import re
import sys
import types
import unittest


def _install_qt_stubs() -> None:
    class _Dummy:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return self

        def __getattr__(self, _name):
            return self

    qt = types.ModuleType("kyth_welcome.qt")
    for name in ("QLabel", "QPushButton", "QTextEdit", "QThread", "QWidget"):
        setattr(qt, name, _Dummy)
    qt.Signal = _Dummy
    sys.modules["kyth_welcome.qt"] = qt


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
_install_qt_stubs()

from kyth_welcome.krunner_desktop import build_entries  # noqa: E402

HUB_WEB = ROOT / "src" / "kyth-hub-web" / "src"
SECTIONS_TS = (HUB_WEB / "data" / "hubSections.ts").read_text(encoding="utf-8")
DEEP_LINK_TS = (HUB_WEB / "deepLink.ts").read_text(encoding="utf-8")
DESTINATIONS_TS = (HUB_WEB / "data" / "destinations.ts").read_text(encoding="utf-8")
SIDEBAR_TSX = (HUB_WEB / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
HUB_PAGE_TSX = (HUB_WEB / "pages" / "HubPage.tsx").read_text(encoding="utf-8")
LAUNCHER_SH = (ROOT / "src" / "kyth-welcome" / "kyth-welcome-launch").read_text(encoding="utf-8")
NATIVE_RS = (ROOT / "src" / "kyth-hub-web" / "src-tauri" / "src" / "native_main.rs").read_text(encoding="utf-8")
CTX_INSTALLS_SH = (
    ROOT / "build_files" / "scripts" / "branding" / "23-kyth-helper-ctx-installs.sh"
).read_text(encoding="utf-8")

_PAGE_ARG_RE = re.compile(r'--page "([^"]+)"')


def _code_only(source: str) -> str:
    """Drop comments so assertions match real code, not prose about it —
    these files document the contract in comments that quote the very
    identifiers and keys being asserted on."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(("//", "*"))
    )


DEEP_LINK_CODE = _code_only(DEEP_LINK_TS)
DESTINATIONS_CODE = _code_only(DESTINATIONS_TS)
HUB_PAGE_CODE = _code_only(HUB_PAGE_TSX)


def _section_keys() -> set[str]:
    return set(re.findall(r'key:\s*"([^"]+)"', SECTIONS_TS))


def _destination_keys() -> set[str]:
    """Rail destinations from the shared DESTINATIONS table literal.

    The table moved to data/destinations.ts when the search box needed the
    same "what pages exist and where" list deep links use; Welcome is still
    seeded by deepLink.ts's own route table, since it is a route with no
    sections rather than a destination.
    """
    keys = set(re.findall(r'key:\s*"([^"]+)",\s*route:\s*"/[a-z-]*"', DESTINATIONS_CODE))
    if re.search(r'\{\s*Welcome:\s*"/"', DEEP_LINK_CODE):
        keys.add("Welcome")
    return keys


def _resolvable_keys() -> set[str]:
    return _section_keys() | _destination_keys()


class HubWebDeepLinkTests(unittest.TestCase):
    def test_native_hub_is_the_default_with_explicit_react_rollback(self):
        self.assertIn('target_bin="/usr/bin/kyth-hub-native"', LAUNCHER_SH)
        self.assertIn('KYTH_USE_REACT_UI:-0', LAUNCHER_SH)
        self.assertIn('target_bin="/usr/bin/kyth-hub-shell"', LAUNCHER_SH)

    def test_every_krunner_page_key_resolves(self):
        emitted = {
            _PAGE_ARG_RE.search(content).group(1) for content in build_entries().values()
        }
        self.assertGreaterEqual(len(emitted), 20)
        missing = sorted(emitted - _resolvable_keys())
        self.assertEqual(
            missing,
            [],
            f"krunner ships --page keys the React Hub cannot route (they open Home): {missing}",
        )

    def test_shipped_desktop_files_page_keys_resolve(self):
        emitted = set(_PAGE_ARG_RE.findall(CTX_INSTALLS_SH))
        self.assertIn("App Store", emitted, "context-menu installer entry lost its --page key")
        self.assertEqual(sorted(emitted - _resolvable_keys()), [])

    def test_destinations_cover_the_full_pulse_rail(self):
        self.assertEqual(
            _destination_keys(),
            {"Welcome", "Play", "Apps", "This PC", "Move In", "Updates"},
        )

    def test_updates_is_the_last_left_rail_destination(self):
        entries = re.findall(r'\{ to: "([^"]+)", label: "([^"]+)",', SIDEBAR_TSX)
        self.assertTrue(entries)
        self.assertEqual(entries[-1], ("/updates", "Updates"))

    def test_sections_are_derived_not_hardcoded_in_the_route_table(self):
        # Guards the regression's actual cause: if someone re-lists sections
        # by hand, adding a section to hubSections.ts stops being enough and
        # the next key silently falls back to Home.
        for array in ("PLAY_SECTIONS", "APPS_SECTIONS", "THIS_PC_SECTIONS", "MOVE_IN_SECTIONS", "UPDATES_SECTIONS"):
            self.assertIn(array, DESTINATIONS_CODE)
        self.assertIn("DESTINATIONS", DEEP_LINK_CODE)
        for key in sorted(_section_keys()):
            for name, code in (("deepLink.ts", DEEP_LINK_CODE), ("destinations.ts", DESTINATIONS_CODE)):
                self.assertNotIn(
                    f'"{key}"', code, f"{key} hardcoded in {name} rather than derived"
                )

    def test_section_deep_links_and_hub_page_agree_on_the_query_param(self):
        # Two halves of one contract: deepLink.ts writes ?section=, HubPage
        # reads it. If either side renames it, deep links go to the
        # destination's first tab instead of the requested one.
        self.assertIn("?section=${encodeURIComponent(section.key)}", DEEP_LINK_CODE)
        self.assertIn('searchParams.get("section")', HUB_PAGE_CODE)
        self.assertIn("useSearchParams", HUB_PAGE_CODE)
        # A mount-time effect syncing state->URL would clobber the incoming
        # deep link; the tab state must live only in the URL.
        self.assertNotIn("useState", HUB_PAGE_CODE)

    def test_native_hub_selects_requested_section_deep_links(self):
        # The native shell receives the same registry key through --page, but
        # has no URL query string to carry the React shell's ?section value.
        # It must select the matching native tab after resolving the landing
        # destination, including the historical Just -> Recipes alias.
        self.assertIn("fn initial_requested_page()", NATIVE_RS)
        self.assertIn("fn initial_section(page: &str)", NATIVE_RS)
        self.assertIn('Some("Just") if page == "This PC" => "Recipes"', NATIVE_RS)
        self.assertIn('Some("Update") if page == "Updates" => "Updates"', NATIVE_RS)
        self.assertIn('"Update" | "Updates" => "Updates"', NATIVE_RS)
        self.assertIn("let section = initial_section(&page);", NATIVE_RS)
        self.assertIn("window.set_selected_section(SharedString::from(section.as_str()));", NATIVE_RS)

    def test_native_installed_acceptance_contract_keeps_migrated_surfaces(self):
        slint = (ROOT / "src" / "kyth-hub-web" / "src-tauri" / "ui" / "hub.slint").read_text(encoding="utf-8")
        self.assertIn('target_bin="/usr/bin/kyth-hub-native"', LAUNCHER_SH)
        self.assertIn('KYTH_USE_REACT_UI:-0', LAUNCHER_SH)
        for page, section in (("This PC", "Hardware"), ("Play", "Gaming"), ("Apps", "App Store"), ("This PC", "Guardian")):
            self.assertIn(f'selected-page == "{page}" && selected-section == "{section}"', slint)
        for action in ('page-action("upgrade")', 'page-action("rollback")'):
            self.assertIn(action, slint)


if __name__ == "__main__":
    unittest.main()
