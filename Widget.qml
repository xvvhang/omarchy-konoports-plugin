import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "konochi.konoports"
  readonly property var service: bar?.shell?.serviceFor(moduleName)
  readonly property bool active: (service?.ready ?? false) && (service?.servers.length ?? 0) > 0
  readonly property bool opened: panel.opened
  readonly property bool popoutSwitchClosing: panel.popoutSwitchClosing
  readonly property real openPanelIndicatorWidth: Style.bar.iconCanvas
  readonly property real openPanelIndicatorHeight: Style.bar.iconCanvas
  function open() { panel.open() }
  function close() { panel.close() }
  function closeForPopoutSwitch() { panel.closeForPopoutSwitch() }
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    useActiveColor: false
    labelVisible: false
    hasVisualContent: true
    fixedWidth: root.vertical ? -1 : Style.bar.iconSlot
    fixedHeight: root.vertical ? Style.bar.iconSlot : -1
    tooltipText: "Konoports · " + (!root.service?.ready ? (root.service?.error || "Scanning…") : root.service.servers.length + " listening endpoint" + (root.service.servers.length === 1 ? "" : "s"))
    onPressed: function(b) { if (b === Qt.LeftButton) panel.toggle() }
    Item {
      anchors.centerIn: parent
      width: Style.bar.iconCanvas
      height: width
      opacity: root.active ? 1 : 0.35
      Behavior on opacity { NumberAnimation { duration: 150 } }
      OpticalGlyph { anchors.fill: parent; text: "\u{f048d}"; color: button.foreground; fontFamily: button.fontFamily; fontSize: Style.bar.iconFont }
    }
  }
  PortsPanel { id: panel; bar: root.bar; hostWidget: root; anchorItem: button }
}
