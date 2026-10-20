import QtQuick
import Quickshell.Io

Item {
  id: root
  property var servers: []
  property bool ready: false
  property string error: ""
  property string feedback: ""
  readonly property bool busy: stopper.running
  readonly property string script: Qt.resolvedUrl("collect.py").toString().replace(/^file:\/\//, "")
  function stop(server) {
    if (busy || !ready) return
    feedback = "Stopping PID " + server.pid + "…"
    stopper.command = ["/usr/bin/python3", "-B", script, "--stop", String(server.pid), String(server.startTime), String(server.port), String(server.inode)]
    stopper.running = true
  }
  Process {
    id: backend
    command: ["/usr/bin/python3", "-B", root.script]
    running: true
    stdout: SplitParser {
      onRead: function(line) {
        try {
          var data = JSON.parse(line)
          root.servers = data.servers || []
          root.error = data.error || ""
          root.ready = root.error === ""
          stale.restart()
        } catch (e) { console.warn("Konoports:", e) }
      }
    }
    stderr: StdioCollector { onStreamFinished: if (text.trim()) console.warn("Konoports:", text.trim()) }
    onExited: { root.ready = false; root.error = "Collector stopped. Retrying…"; retry.restart() }
  }
  Process {
    id: stopper
    stdout: StdioCollector {
      onStreamFinished: {
        try { root.feedback = JSON.parse(text).message }
        catch (e) { root.feedback = "Could not stop process. Please try again." }
      }
    }
    stderr: StdioCollector { onStreamFinished: if (text.trim()) console.warn("Konoports stop:", text.trim()) }
  }
  Timer { id: retry; interval: 5000; onTriggered: backend.running = true }
  Timer { id: stale; interval: 10000; onTriggered: { root.ready = false; root.error = "Data update timed out" } }
  IpcHandler {
    target: "konochi.konoports"
    function status(): string { return JSON.stringify({ready: root.ready, error: root.error, servers: root.servers, busy: root.busy, feedback: root.feedback}) }
  }
}
