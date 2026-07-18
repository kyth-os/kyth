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

from kyth_welcome import core, page_vpn  # noqa: E402


class CoreParserTests(unittest.TestCase):
    def test_parse_size_bytes(self):
        self.assertEqual(core._parse_size_bytes("1 KB"), 1024)
        self.assertEqual(core._parse_size_bytes("1.5 GB"), int(1.5 * 1024**3))
        self.assertEqual(core._parse_size_bytes("not a size"), 0)

    def test_parse_steam_acf_text(self):
        acf = core._parse_steam_acf_text(
            '"appid" "620"\n"name" "Portal 2"\n"installdir" "Portal 2"\n'
        )
        self.assertEqual(acf["appid"], "620")
        self.assertEqual(acf["name"], "Portal 2")
        self.assertEqual(acf["installdir"], "Portal 2")

    def test_format_display_mode(self):
        self.assertEqual(core._format_display_mode("1920x1080@143.98"), "1920\u00d71080 @ 144Hz")
        self.assertEqual(core._format_display_mode("bad-mode"), "bad-mode")

    def test_parse_kscreen_output(self):
        display = core._parse_kscreen_output(
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
            core._DEFAULT_FIRST_RUN_APPS,
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


if __name__ == "__main__":
    unittest.main()
