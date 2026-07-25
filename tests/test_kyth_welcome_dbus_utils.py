import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

# dbus_utils imports QDBusConnection/QDBusInterface from ..qt, which pulls in
# PySide6/PyQt6. Neither is installed in this test environment. Other test
# modules (test_kyth_page_registry, test_kyth_welcome_parsers) also stub
# kyth_welcome.qt in sys.modules with their own narrower dummies and leave
# them installed process-wide, so under `unittest discover` this module may
# see an existing stub that lacks QDBus* — patch just what's missing rather
# than overwriting whatever is already there.
_qt_stub = sys.modules.setdefault("kyth_welcome.qt", MagicMock())
if not hasattr(_qt_stub, "QDBusConnection"):
    _qt_stub.QDBusConnection = MagicMock()
if not hasattr(_qt_stub, "QDBusInterface"):
    _qt_stub.QDBusInterface = MagicMock()

from kyth_welcome.services import dbus_utils  # noqa: E402


def _error_reply():
    reply = MagicMock()
    reply.type.return_value = reply.Type.ErrorMessage
    return reply


def _ok_reply(*arguments):
    reply = MagicMock()
    reply.type.return_value = MagicMock(name="NotErrorMessage")
    reply.arguments.return_value = list(arguments)
    return reply


class IsSystemdUnitEnabledTests(unittest.TestCase):
    def test_returns_true_for_enabled_unit(self):
        interface = MagicMock()
        interface.isValid.return_value = True
        interface.call.return_value = _ok_reply("enabled")
        with patch.object(dbus_utils, "QDBusInterface", return_value=interface):
            self.assertTrue(dbus_utils.is_systemd_unit_enabled("kyth-update-watcher.timer"))

    def test_returns_true_for_static_unit(self):
        interface = MagicMock()
        interface.isValid.return_value = True
        interface.call.return_value = _ok_reply("static")
        with patch.object(dbus_utils, "QDBusInterface", return_value=interface):
            self.assertTrue(dbus_utils.is_systemd_unit_enabled("some.service"))

    def test_returns_false_for_disabled_unit(self):
        interface = MagicMock()
        interface.isValid.return_value = True
        interface.call.return_value = _ok_reply("disabled")
        with patch.object(dbus_utils, "QDBusInterface", return_value=interface):
            self.assertFalse(dbus_utils.is_systemd_unit_enabled("some.service"))

    def test_fails_open_when_interface_is_invalid(self):
        interface = MagicMock()
        interface.isValid.return_value = False
        with patch.object(dbus_utils, "QDBusInterface", return_value=interface):
            self.assertTrue(dbus_utils.is_systemd_unit_enabled("some.service"))

    def test_fails_open_on_dbus_error_reply(self):
        interface = MagicMock()
        interface.isValid.return_value = True
        interface.call.return_value = _error_reply()
        with patch.object(dbus_utils, "QDBusInterface", return_value=interface):
            self.assertTrue(dbus_utils.is_systemd_unit_enabled("some.service"))

    def test_fails_open_on_unexpected_exception(self):
        with patch.object(dbus_utils, "QDBusConnection") as connection:
            connection.systemBus.side_effect = RuntimeError("no bus")
            self.assertTrue(dbus_utils.is_systemd_unit_enabled("some.service"))


class IsSystemdUnitActiveTests(unittest.TestCase):
    def test_returns_true_for_active_unit(self):
        manager = MagicMock()
        manager.isValid.return_value = True
        manager.call.return_value = _ok_reply("/org/freedesktop/systemd1/unit/some_2eservice")

        unit = MagicMock()
        unit.isValid.return_value = True
        unit.property.return_value = "active"

        with patch.object(dbus_utils, "QDBusInterface", side_effect=[manager, unit]):
            self.assertTrue(dbus_utils.is_systemd_unit_active("some.service"))

    def test_returns_false_for_inactive_unit(self):
        manager = MagicMock()
        manager.isValid.return_value = True
        manager.call.return_value = _ok_reply("/org/freedesktop/systemd1/unit/some_2eservice")

        unit = MagicMock()
        unit.isValid.return_value = True
        unit.property.return_value = "inactive"

        with patch.object(dbus_utils, "QDBusInterface", side_effect=[manager, unit]):
            self.assertFalse(dbus_utils.is_systemd_unit_active("some.service"))

    def test_fails_closed_when_manager_interface_is_invalid(self):
        manager = MagicMock()
        manager.isValid.return_value = False
        with patch.object(dbus_utils, "QDBusInterface", return_value=manager):
            self.assertFalse(dbus_utils.is_systemd_unit_active("some.service"))

    def test_fails_closed_on_dbus_error_reply(self):
        manager = MagicMock()
        manager.isValid.return_value = True
        manager.call.return_value = _error_reply()
        with patch.object(dbus_utils, "QDBusInterface", return_value=manager):
            self.assertFalse(dbus_utils.is_systemd_unit_active("some.service"))

    def test_fails_closed_when_unit_interface_is_invalid(self):
        manager = MagicMock()
        manager.isValid.return_value = True
        manager.call.return_value = _ok_reply("/org/freedesktop/systemd1/unit/some_2eservice")

        unit = MagicMock()
        unit.isValid.return_value = False

        with patch.object(dbus_utils, "QDBusInterface", side_effect=[manager, unit]):
            self.assertFalse(dbus_utils.is_systemd_unit_active("some.service"))

    def test_fails_closed_on_unexpected_exception(self):
        with patch.object(dbus_utils, "QDBusConnection") as connection:
            connection.systemBus.side_effect = RuntimeError("no bus")
            self.assertFalse(dbus_utils.is_systemd_unit_active("some.service"))


if __name__ == "__main__":
    unittest.main()
