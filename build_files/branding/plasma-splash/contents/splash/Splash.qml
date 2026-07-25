// SPDX-License-Identifier: Apache-2.0

import QtQuick

Rectangle {
    id: root
    color: "#090b12"

    property int stage

    Item {
        id: content
        anchors.fill: parent
        opacity: root.stage >= 2 && root.stage < 5 ? 1 : 0

        Behavior on opacity {
            NumberAnimation {
                duration: 300
                easing.type: Easing.InOutQuad
            }
        }

        Image {
            id: logo
            anchors.centerIn: parent
            asynchronous: true
            fillMode: Image.PreserveAspectFit
            source: "images/kyth-logo.svg"
            sourceSize.width: Math.min(root.width * 0.34, 320)
            sourceSize.height: Math.min(root.height * 0.34, 240)
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: logo.bottom
            anchors.topMargin: 18
            color: "#d8dee9"
            font.pixelSize: 18
            font.weight: Font.Medium
            text: "Starting KythOS"
        }

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: logo.bottom
            anchors.topMargin: 58
            spacing: 9

            Repeater {
                model: 3

                Rectangle {
                    required property int index
                    width: 8
                    height: 8
                    radius: 4
                    color: "#73daca"
                    opacity: 0.3

                    SequentialAnimation on opacity {
                        loops: Animation.Infinite
                        PauseAnimation { duration: index * 160 }
                        NumberAnimation { to: 1; duration: 280 }
                        NumberAnimation { to: 0.3; duration: 500 }
                        PauseAnimation { duration: (2 - index) * 160 }
                    }
                }
            }
        }
    }
}
