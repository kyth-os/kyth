import importlib
import pathlib
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

    class _DummySignal(_Dummy):
        pass

    class _DummyLibraryInfo:
        class LibraryPath:
            PluginsPath = 0

        @staticmethod
        def path(_which):
            return ""

    qt = types.ModuleType("kyth_welcome.qt")
    for name in (
        "QComboBox",
        "QDialog",
        "QFrame",
        "QHBoxLayout",
        "QLabel",
        "QLineEdit",
        "QPushButton",
        "QSizePolicy",
        "QTextEdit",
        "QThread",
        "QTimer",
        "QUrl",
        "single_shot",
        "QVBoxLayout",
        "QWebEnginePage",
        "QWebEngineProfile",
        "QWebEngineUrlRequestJob",
        "QWebEngineUrlSchemeHandler",
        "QWebEngineView",
        "QWidget",
    ):
        setattr(qt, name, _Dummy)
    qt.Signal = _DummySignal
    qt.QLibraryInfo = _DummyLibraryInfo
    qt._WEBENGINE_AVAILABLE = False
    sys.modules["kyth_welcome.qt"] = qt

    widgets = types.ModuleType("kyth_welcome.widgets")
    widgets.Page = _Dummy
    widgets._make_card = lambda *args, **kwargs: (_Dummy(), _Dummy())
    widgets._set_log_panel = lambda *args, **kwargs: None
    sys.modules["kyth_welcome.widgets"] = widgets


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
_install_qt_stubs()

from kyth_welcome import core_base, page_vpn  # noqa: E402
from kyth_welcome.services import appstream, first_run, gaming, hardware, network, repair, software, updates, welcome  # noqa: E402


class CoreParserTests(unittest.TestCase):
    def test_parse_size_bytes(self):
        self.assertEqual(core_base._parse_size_bytes("1 KB"), 1024)
        self.assertEqual(core_base._parse_size_bytes("1.5 GB"), int(1.5 * 1024**3))
        self.assertEqual(core_base._parse_size_bytes("not a size"), 0)


class UpdateOperationControllerTests(unittest.TestCase):
    def test_operation_controller_tracks_phase_and_irreversible_cancel_boundary(self):
        controller = updates.UpdateOperationController()
        controller.start("update", now=100.0)

        phase = controller.receive_line("Deploying image", now=105.0)

        self.assertTrue(phase)
        self.assertEqual(controller.last_output_at, 105.0)
        self.assertTrue(controller.cancellation_blocked)
        self.assertTrue(controller.cancel_block_reason)

    def test_operation_controller_finishes_quiet_download(self):
        controller = updates.UpdateOperationController()
        controller.start("update", now=100.0)
        for _ in range(9):
            self.assertEqual(
                controller.update_download(500, 1000, 0, 0, proxy_running=False),
                "active",
            )

        self.assertEqual(
            controller.update_download(500, 1000, 0, 0, proxy_running=False),
            "complete",
        )
        self.assertEqual(controller.final_download_bytes, 500)

    def test_operation_controller_advances_silent_download_phase(self):
        controller = updates.UpdateOperationController()
        controller.start("update", now=100.0)
        controller.set_phase("Downloading image layers…")
        controller.last_output_at = 100.0

        self.assertEqual(controller.heartbeat_phase(now=111.0), "Processing image layers…")

    def test_parse_steam_acf_text(self):
        acf = gaming._parse_steam_acf_text(
            '"appid" "620"\n"name" "Portal 2"\n"installdir" "Portal 2"\n'
        )
        self.assertEqual(acf["appid"], "620")
        self.assertEqual(acf["name"], "Portal 2")
        self.assertEqual(acf["installdir"], "Portal 2")

    def test_format_display_mode(self):
        self.assertEqual(hardware._format_display_mode("1920x1080@143.98"), "1920\u00d71080 @ 144Hz")
        self.assertEqual(hardware._format_display_mode("bad-mode"), "bad-mode")

    def test_parse_kscreen_output(self):
        display = hardware._parse_kscreen_output(
            "Output: 1 HDMI-A-1\n"
            "connected\n"
            "enabled\n"
            "Modes: 0:1920x1080@144*! 1:1280x720@60\n"
            "Vrr: Never\n"
            "Hdr: disabled\n"
        )
        self.assertEqual(display.title, "Display")
        self.assertEqual(display.status, "warn")
        self.assertIn("HDMI-A-1", display.summary)
        self.assertIn("VRR/FreeSync", display.details)


class AppDefaultsTests(unittest.TestCase):
    def test_brave_is_in_default_first_run_apps(self):
        self.assertIn(
            ("com.brave.Browser", "Brave"),
            first_run.DEFAULT_FIRST_RUN_APPS,
        )


class LazyPageTests(unittest.TestCase):
    def test_lazy_page_uses_page_new_for_qt_style_objects(self):
        widgets_module = types.ModuleType("kyth_welcome.widgets")

        class DummyPage:
            new_calls = 0

            def __new__(cls, *args, **kwargs):
                cls.new_calls += 1
                return super().__new__(cls)

        widgets_module.Page = DummyPage
        sys.modules["kyth_welcome.widgets"] = widgets_module
        sys.modules.pop("kyth_welcome.lazy_page", None)

        lazy_page = importlib.import_module("kyth_welcome.lazy_page")

        @lazy_page.compose_on_first_init(lambda: ())
        class Shell(DummyPage):
            pass

        instance = Shell()
        self.assertIsInstance(instance, DummyPage)


class VpnParserTests(unittest.TestCase):
    def test_parse_gp_saml_cookie(self):
        field, value, username = page_vpn._parse_gp_saml_cookie(
            "prelogin-cookie=secret&saml-username=alice"
        )
        self.assertEqual(field, "prelogin-cookie")
        self.assertEqual(value, "secret")
        self.assertEqual(username, "alice")

    def test_redact_vpn_log_line(self):
        redacted = page_vpn._redact_vpn_log_line(
            "GlobalProtect login returned prelogin-cookie=secret"
        )
        self.assertNotIn("secret", redacted)
        self.assertIn("<redacted>", redacted)

    def test_vpn_line_is_connected(self):
        self.assertTrue(page_vpn._vpn_line_is_connected("Established DTLS connection"))
        self.assertFalse(page_vpn._vpn_line_is_connected("Authentication failed"))


class HomeHeroViewTests(unittest.TestCase):
    def test_home_categories_and_profile_filtering(self):
        categories = welcome.home_categories(has_nvidia=True)
        self.assertEqual(categories[0][2], "Games")
        self.assertIn(("Manage NVIDIA drivers", "NVIDIA"), categories[-1][3])
        self.assertEqual(welcome.visible_category_indexes("everyday", [True, False, False]), [1, 2])
        self.assertEqual(welcome.visible_category_indexes("gaming", [True, False]), [0, 1])

    def test_staged_update_takes_priority(self):
        view = welcome.home_hero_view(staged=True, rollback=True, windows_found=True)
        self.assertEqual(view.pill_text, "RESTART REQUIRED")
        self.assertEqual(view.pill_object_name, "glowing-pill-warn")
        self.assertEqual(view.rec_target, "reboot")
        self.assertEqual(view.rec_btn_label, "Restart Now")

    def test_rollback_beats_windows_when_not_staged(self):
        view = welcome.home_hero_view(staged=False, rollback=True, windows_found=True)
        self.assertEqual(view.pill_text, "SYSTEM UP-TO-DATE")
        self.assertEqual(view.pill_object_name, "glowing-pill-ok")
        self.assertEqual(view.rec_target, "Update")
        self.assertEqual(view.rec_btn_label, "Manage Rollbacks")

    def test_windows_found_without_staged_or_rollback(self):
        view = welcome.home_hero_view(staged=False, rollback=False, windows_found=True)
        self.assertEqual(view.rec_target, "Move Files")
        self.assertEqual(view.rec_btn_label, "Transfer Files")

    def test_default_recommends_gaming_setup(self):
        view = welcome.home_hero_view(staged=False, rollback=False, windows_found=False)
        self.assertEqual(view.rec_target, "Gaming")
        self.assertEqual(view.rec_btn_label, "Configure Games")
        self.assertEqual(view.pill_text, "SYSTEM UP-TO-DATE")


class PageServiceModelTests(unittest.TestCase):
    def test_update_operations_are_provider_independent(self):
        full = updates.full_update_operation()
        image = updates.image_update_operation(lambda: ["pkexec", "bootc", "upgrade"])
        self.assertEqual(full.mode, "full-update")
        self.assertEqual(image.command, ("pkexec", "bootc", "upgrade"))
        self.assertEqual(updates.failed_operation_label("rollback"), "bootc rollback")

    def test_repair_quick_fixes_are_declarative(self):
        fixes = repair.quick_fixes()
        self.assertEqual(fixes[0].label, "Refresh App Menu")
        self.assertTrue(all(fix.command for fix in fixes))


class FamiliarAppMatchTests(unittest.TestCase):
    _APPS = [
        ("Microsoft Office", "Use LibreOffice.", "org.libreoffice.LibreOffice"),
        ("Word / Excel / PowerPoint", "LibreOffice Writer, Calc, Impress.", "org.libreoffice.LibreOffice"),
        ("Notepad", "Kate is already installed.", ""),
    ]

    def test_exact_name_matches(self):
        match = software.find_familiar_app_match("Notepad", self._APPS)
        self.assertEqual(match, ("Notepad", "Kate is already installed.", ""))

    def test_case_insensitive_substring_match(self):
        match = software.find_familiar_app_match("office", self._APPS)
        self.assertEqual(match[0], "Microsoft Office")

    def test_earlier_entry_wins_ties(self):
        apps = [("Notepad", "d1", "a"), ("Notepad++", "d2", "b")]
        match = software.find_familiar_app_match("Notepad", apps)
        self.assertEqual(match[0], "Notepad")

    def test_no_match_returns_none(self):
        self.assertIsNone(software.find_familiar_app_match("Blender", self._APPS))

    def test_empty_query_returns_none(self):
        self.assertIsNone(software.find_familiar_app_match("   ", self._APPS))


class ShareFormValidationTests(unittest.TestCase):
    _VALID = dict(
        name="NAS-Media", server="192.168.1.100", share_path="Media",
        mount_pt="", username="alice", password="hunter2", domain="",
        auto_mount=True, existing_names=set(), reconnect_name=None,
    )

    def test_missing_required_fields_are_rejected(self):
        for field, message in (
            ("name", "Please enter a Share Name."),
            ("server", "Please enter a Server address."),
            ("share_path", "Please enter the Share Path."),
            ("username", "Please enter a Username."),
        ):
            kwargs = {**self._VALID, field: ""}
            result = network.validate_share_form(**kwargs)
            self.assertIsNone(result.share)
            self.assertEqual(result.error_title, "Missing Field")
            self.assertEqual(result.error_message, message)

    def test_valid_form_defaults_mount_point_from_name(self):
        result = network.validate_share_form(**self._VALID)
        self.assertIsNotNone(result.share)
        self.assertEqual(result.share["mount_point"], "/mnt/kyth/NAS-Media")
        self.assertEqual(result.share["name"], "NAS-Media")

    def test_name_is_sanitized_to_safe_characters(self):
        result = network.validate_share_form(**{**self._VALID, "name": "NAS Media!"})
        self.assertEqual(result.share["name"], "NAS_Media_")

    def test_mount_point_outside_approved_prefix_is_rejected(self):
        result = network.validate_share_form(**{**self._VALID, "mount_pt": "/etc/passwd"})
        self.assertIsNone(result.share)
        self.assertEqual(result.error_title, "Invalid Mount Point")

    def test_duplicate_name_is_rejected(self):
        result = network.validate_share_form(
            **{**self._VALID, "existing_names": {"NAS-Media"}}
        )
        self.assertIsNone(result.share)
        self.assertEqual(result.error_title, "Duplicate Name")

    def test_duplicate_name_allowed_when_reconnecting_same_share(self):
        result = network.validate_share_form(**{
            **self._VALID,
            "existing_names": {"NAS-Media"},
            "reconnect_name": "NAS-Media",
        })
        self.assertIsNotNone(result.share)

    def test_share_path_leading_slash_is_stripped(self):
        result = network.validate_share_form(**{**self._VALID, "share_path": "/Media/Movies"})
        self.assertEqual(result.share["share_path"], "Media/Movies")


class AppStreamCatalogTests(unittest.TestCase):
    def test_as_localized(self):
        import xml.etree.ElementTree as ET
        xml_str = """
        <component>
            <name xml:lang="en">English App</name>
            <name xml:lang="de">Deutsches App</name>
            <name>Default App</name>
        </component>
        """
        elem = ET.fromstring(xml_str)  # noqa: S314 — literal fixture above, not untrusted input
        self.assertEqual(appstream._as_localized(elem, "name", "de"), "Deutsches App")
        self.assertEqual(appstream._as_localized(elem, "name", "en"), "English App")

    def test_as_localized_desc(self):
        import xml.etree.ElementTree as ET
        xml_str = """
        <component>
            <description xml:lang="en">
                <p>Hello world</p>
            </description>
        </component>
        """
        elem = ET.fromstring(xml_str)  # noqa: S314 — literal fixture above, not untrusted input
        self.assertEqual(appstream._as_localized_desc(elem, "en"), "Hello world")


if __name__ == "__main__":
    unittest.main()
