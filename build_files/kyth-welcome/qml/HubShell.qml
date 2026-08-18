// HubShell.qml — Phase 3 pilot stub (no runtime switch yet)
// Keeps Python services as source of truth. When enabled, window.py will
// load this via QQuickWidget with a QmlBridge context property.
// This stub mirrors the Windows 11 Settings nav (left rail + content).
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    color: "#0a0c13"
    RowLayout { anchors.fill: parent; spacing: 0
        Rectangle { Layout.preferredWidth: 240; Layout.fillHeight: true; color: "#0a0c13"; border.color: "#262b3d"; border.width: 1
            ColumnLayout { anchors.fill: parent; anchors.margins: 12; spacing: 4
                Text { text: "KythOS"; color: "#f2f4fb"; font.pixelSize: 20; font.weight: 800 }
                Text { text: "System Hub — QML pilot"; color: "#5b6580"; font.pixelSize: 11 }
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.fillHeight: true; color: "transparent"
            // Guard for stale snapshot on page re-entry: reload model if probe cache invalidated
            property bool staleGuard: false
            Connections {
                target: typeof QmlBridge !== "undefined" ? QmlBridge : null
                function onProbeCacheInvalidated() { staleGuard = true }
            }
            onVisibleChanged: if (visible && staleGuard) { staleGuard = false; if (typeof QmlBridge !== "undefined" && QmlBridge.reloadHardwareSnapshot) QmlBridge.reloadHardwareSnapshot() }
            Text { anchors.centerIn: parent; text: "QML shell stub — Python services stay in control"; color: "#93a1bd"; font.pixelSize: 13 }
        }
    }
}
