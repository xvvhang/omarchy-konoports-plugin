import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "konochi.konoports"
  manageIpc: false
  property var hostWidget: null
  property var anchorItem: null
  readonly property var service: hostWidget?.service
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color dim: Qt.darker(barForeground, 1.55)
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  property var pending: null
  onOpenedChanged: { pending = null }
  Timer { id: confirmationTimeout; interval: 6000; onTriggered: root.pending = null }
  function requestStop(server) {
    if (pending?.key === server.key) {
      root.service.stop(server)
      pending = null
      confirmationTimeout.stop()
    } else {
      pending = server
      confirmationTimeout.restart()
    }
  }
  component ActionButton: Button {
    foreground: root.barForeground
    accent: foreground
    bordered: true
    focusable: true
    fontFamily: root.fontFamily
    fontSize: Style.font.caption
    opacity: enabled ? 1 : 0.4
  }
  component Label: Text {
    width: parent.width
    color: root.barForeground
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    textFormat: Text.PlainText
    wrapMode: Text.Wrap
  }
  KeyboardPanel {
    anchorItem: root.anchorItem
    bar: root.bar
    owner: root.hostWidget
    open: root.opened
    focusTarget: content
    contentWidth: fittedContentWidth(Style.space(380))
    contentHeight: fittedContentHeight(column.implicitHeight)
    Flickable {
      id: content
      anchors.fill: parent
      clip: true
      contentWidth: width
      contentHeight: column.implicitHeight
      boundsBehavior: Flickable.StopAtBounds
      flickableDirection: Flickable.VerticalFlick
      interactive: contentHeight > height
      Keys.onEscapePressed: { if (root.pending) root.pending = null; else root.close() }
      Column {
        id: column
        width: content.width
        spacing: Style.space(12)
        PanelHero {
          width: parent.width
          title: "Konoports"
          meta: "Local dev servers"
          foreground: root.barForeground
          fontFamily: root.fontFamily
          iconComponent: Component {
            Item {
              width: Style.font.display
              height: width
              OpticalGlyph { anchors.fill: parent; text: "\u{f048d}"; color: root.barForeground; fontFamily: root.fontFamily; fontSize: Style.font.display }
            }
          }
        }
        Label {
          text: root.service?.ready ? root.service.servers.length + " listening endpoint" + (root.service.servers.length === 1 ? "" : "s") : (root.service?.error || "Scanning local dev servers…")
          color: root.dim
        }
        Label {
          visible: (root.service?.ready ?? false) && root.service.servers.length === 0
          text: "No dev servers running.\nStart a project and it will appear here automatically."
          color: root.dim
          font.pixelSize: Style.font.body
        }
        Repeater {
          model: root.service?.servers || []
          Column {
            id: server
            required property var modelData
            width: column.width
            spacing: Style.space(8)
            PanelSeparator { foreground: root.barForeground }
            Row {
              width: parent.width
              spacing: Style.space(8)
              Label {
                width: Math.max(0, parent.width - portLabel.width - parent.spacing)
                text: server.modelData.project
                font.pixelSize: Style.font.body
                font.bold: true
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
              }
              Label {
                id: portLabel
                width: implicitWidth
                text: ":" + server.modelData.port
                font.pixelSize: Style.font.body
                font.bold: true
              }
            }
            Column {
              width: parent.width
              spacing: Style.space(4)
              Label { text: server.modelData.kind + " · PID " + server.modelData.pid; color: root.dim }
              Label { text: server.modelData.cwd; visible: text !== ""; color: root.dim; wrapMode: Text.NoWrap; elide: Text.ElideMiddle }
            }
            Label { text: "$ " + (server.modelData.displayCommand || server.modelData.command); font.pixelSize: Style.font.bodySmall }
            Label { text: server.modelData.url; color: root.dim }
            Flow {
              width: parent.width
              spacing: Style.space(6)
              ActionButton {
                text: "Open in browser"
                enabled: root.service?.ready ?? false
                onClicked: Qt.openUrlExternally(server.modelData.url)
              }
              ActionButton {
                text: root.pending?.key === server.modelData.key ? "Confirm stop" : "Stop process"
                foreground: root.pending?.key === server.modelData.key ? root.urgent : root.barForeground
                selected: root.pending?.key === server.modelData.key
                enabled: (root.service?.ready ?? false) && !root.service.busy
                onClicked: root.requestStop(server.modelData)
              }
              ActionButton { visible: root.pending?.key === server.modelData.key; text: "Cancel"; onClicked: root.pending = null }
            }
          }
        }
        Label {
          visible: root.pending !== null
          text: "Stop PID " + (root.pending?.pid ?? "") + " and all its ports? Forces exit after 2.5s if needed."
          color: root.urgent
        }
        Label { visible: text !== ""; text: root.service?.feedback || "" }
        PanelSeparator { foreground: root.barForeground }
        Label { text: "Refreshes every 2s · Current-user TCP listeners"; color: root.dim }
      }
    }
  }
}
