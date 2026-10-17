import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
    id: root
    property string mode: "idle"

    Socket {
        path: Quickshell.env("LINUXWHISPER_OVERLAY_SOCKET")
        connected: true
        parser: SplitParser {
            onRead: data => root.mode = data
        }
        onConnectedChanged: if (!connected) Quickshell.quit()
    }

    PanelWindow {
        visible: root.mode !== "idle"
        anchors.bottom: true
        margins.bottom: 32
        implicitWidth: 278
        implicitHeight: 70
        color: "transparent"
        WlrLayershell.namespace: "linuxwhisper-recording"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        exclusionMode: ExclusionMode.Ignore
        mask: Region {}

        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: 23
            border.width: 1
            border.color: "#393d43"
            gradient: Gradient {
                GradientStop { position: 0; color: "#202329" }
                GradientStop { position: 1; color: "#13161b" }
            }

            Row {
                x: 22
                anchors.verticalCenter: parent.verticalCenter
                height: 25
                spacing: 3
                Repeater {
                    model: [8, 17, 25, 14, 7]
                    Rectangle {
                        required property int modelData
                        width: 2
                        height: modelData
                        anchors.verticalCenter: parent.verticalCenter
                        radius: 1
                        color: "#eee6d6"
                    }
                }
            }

            Text {
                x: 61; y: 15
                text: root.mode === "f4" ? "Voice edit" : "Listening"
                color: "#f0e9dc"
                font.family: "Inter"
                font.pixelSize: 14
                font.weight: Font.Medium
                renderType: Text.NativeRendering
            }
            Text {
                x: 61; y: 36
                text: root.mode === "f4" ? "Release to apply" : "Release to paste"
                color: "#999da6"
                font.family: "Inter"
                font.pixelSize: 10
                renderType: Text.NativeRendering
            }
            Rectangle {
                x: 190; y: 21
                width: 5; height: 5; radius: 2.5
                color: "#ef9878"
            }
            Rectangle {
                x: 215; y: 23
                width: 43; height: 23; radius: 7
                color: "#25292f"
                border.color: "#3a3e44"
                Text {
                    anchors.centerIn: parent
                    text: root.mode === "f4" ? "F4" : "AltGr"
                    color: "#bfc2c8"
                    font.family: "Inter"
                    font.pixelSize: 10
                    renderType: Text.NativeRendering
                }
            }
        }
    }
}
