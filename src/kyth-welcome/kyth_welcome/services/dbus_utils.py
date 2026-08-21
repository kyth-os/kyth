import logging

from ..qt import QDBusConnection, QDBusInterface, QDBusMessage

_logger = logging.getLogger(__name__)


def is_systemd_unit_enabled(unit_name: str) -> bool:
    """Instantly checks if a systemd unit is enabled via DBus."""
    try:
        system_bus = QDBusConnection.systemBus()
        interface = QDBusInterface(
            "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1",
            "org.freedesktop.systemd1.Manager",
            system_bus
        )
        if not interface.isValid():
            return True
        reply = interface.call("GetUnitFileState", unit_name)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            return True
        state = reply.arguments()[0]
        return state in ("enabled", "static")
    except (OSError, RuntimeError, AttributeError) as exc:
        _logger.debug("is_systemd_unit_enabled(%s) failed: %s", unit_name, exc, exc_info=True)
        return True

def is_systemd_unit_active(unit_name: str) -> bool:
    """Instantly checks if a systemd unit is active via DBus."""
    try:
        system_bus = QDBusConnection.systemBus()
        interface = QDBusInterface(
            "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1",
            "org.freedesktop.systemd1.Manager",
            system_bus
        )
        if not interface.isValid():
            return False
        reply = interface.call("GetUnit", unit_name)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            return False
        unit_path = reply.arguments()[0]
        
        # Now query the unit's ActiveState property
        unit_interface = QDBusInterface(
            "org.freedesktop.systemd1",
            unit_path,
            "org.freedesktop.systemd1.Unit",
            system_bus
        )
        if not unit_interface.isValid():
            return False
        state = unit_interface.property("ActiveState")
        return state == "active"
    except (OSError, RuntimeError, AttributeError) as exc:
        _logger.debug("is_systemd_unit_active(%s) failed: %s", unit_name, exc, exc_info=True)
        return False
