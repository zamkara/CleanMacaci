import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons

import "controls" as SoundUi

Item {
  id: root
  function toolPath(name) { return decodeURIComponent(Qt.resolvedUrl("scripts/"+name).toString().replace(/^file:\/\//,"")) }
  readonly property string statePath: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME")+"/.local/state")+"/CleanMacaci"
  Component.onCompleted: menuIntegration.running=true
  Process { id:menuIntegration; command:["python3",root.toolPath("menu.py"),"--install"]; stderr:StdioCollector { onStreamFinished:if(text.trim())console.warn("CleanMacaci menu:",text) } }
  property bool opened: false
  property var categories: []
  property string errorText: ""
  property string resultText: ""
  property string inventoryText: ""
  property string systemSummary: ""
  property bool confirming: false
  property string operation: ""
  property bool cancelling: false
  property string logText: ""
  property string coverageText: ""
  property int detailIndex: -1
  property int excludedCount: 0
  property bool toolsOpen: false
  property string toolGroup: "main"
  property var restoreSelectionIDs: []
  readonly property var closeRows: visibleRows.filter(function(r){return r.closeSelected && r.blocked && r.windows && r.windows.length>0})
  readonly property var visibleRows: categories.filter(function(r){return r.confidence!=="preserve"})
  readonly property bool allSelected: visibleRows.some(function(r){return !r.blocked}) && visibleRows.filter(function(r){return !r.blocked}).every(function(r){return r.selected})
  function selectVisible() {
    if(busy) return
    var ids=visibleRows.filter(function(r){return !r.blocked}).map(function(r){return r.id})
    var selected=!allSelected
    categories=categories.map(function(r){return ids.indexOf(r.id)>=0 ? Object.assign({},r,{selected:selected}) : r})
    confirming=false
  }
  function rowIndex(row) { return categories.findIndex(function(r){return r.id===row.id}) }
  function cancelScan() { if(busy && operation === "scan" && !cancelling){cancelling=true;worker.signal(15)} }
  function copyReport() { if(root.busy || root.errorText){Quickshell.execDetached(["bash","-c",'printf "%s" "$1" | wl-copy',"copy-cleaner-log",root.errorText+"\n"+root.logText]);return} Quickshell.execDetached(["bash","-c",'wl-copy < "$1"',"copy-cleaner-report",root.statePath+"/latest-scan.json"]) }
  function displayRows(rows) {
    var available = rows.filter(function(r) { return r.bytes > 0 })
    excludedCount = available.filter(function(r) { return r.blocked }).length
    detailIndex = -1
    categories = available.map(function(r){return restoreSelectionIDs.indexOf(r.id)>=0 && !r.blocked ? Object.assign({},r,{selected:true}) : r})
  }
  readonly property var detailRow: detailIndex >= 0 && detailIndex < categories.length ? categories[detailIndex] : null
  readonly property bool busy: worker.running
  readonly property double selectedBytes: {
    var n = 0
    for (var i = 0; i < categories.length; i++) if (categories[i].selected && !categories[i].blocked) n += categories[i].bytes
    return n
  }
  QtObject { id: sounds; function play(name) {} function interaction(name) {} function surface(opened) {} }
  onOpenedChanged: sounds.surface(opened)
  function formatSize(bytes) {
    if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(2) + " GiB"
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MiB"
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + " KiB"
    return bytes + " B"
  }
  function open(payload) { opened = true; root.start(["--scan"]) }
  function close() { if(toolsOpen){toolsOpen=false;return} if (busy) return; opened = false; confirming = false }
  function start(args) {
    if (busy) return
    confirming = false
    toolsOpen = false
    cancelling = false
    operation = args[0] === "--close-apps" ? "close" : args[0] === "--clean" ? "clean" : "scan"
    logText = ""
    resultText = ""
    errorText = ""
    worker.command = ["python3", root.toolPath("cleaner.py")].concat(args)
    worker.running = true
  }
  function toggleCategory(index) {
    if (busy || categories[index].blocked) return
    var rows = categories.slice()
    rows[index] = Object.assign({}, rows[index], {selected: !rows[index].selected})
    categories = rows
    confirming = false
  }
  function toggleAll() {
    if(busy) return
    var eligible=categories.filter(function(r){return !r.blocked})
    var select=eligible.some(function(r){return !r.selected})
    categories=categories.map(function(r){return Object.assign({},r,{selected:!r.blocked && select})})
    confirming=false
  }
  function toggleLock(row) {
    if(busy || !row.blocked || !row.windows || !row.windows.length)return
    categories=categories.map(function(r){return r.id===row.id ? Object.assign({},r,{closeSelected:!r.closeSelected}) : r})
    detailIndex=rowIndex(row); confirming=false
  }
  function cleanSelected() {
    if (busy) return
    if (!confirming) { confirming = true; sounds.play("warning"); return }
    if(closeRows.length) {
      restoreSelectionIDs=categories.filter(function(r){return r.selected || r.closeSelected}).map(function(r){return r.id})
      start(["--close-apps",closeRows.map(function(r){return r.id}).join(",")]);return
    }
    var ids = categories.filter(function(row) { return row.selected && !row.blocked }).map(function(row) { return row.id })
    start(["--clean", ids.join(",")])
  }
  IpcHandler {
    target: "cleanmacaci"
    function status(): string { return JSON.stringify({busy: root.busy, categories: root.categories, selectedBytes: root.selectedBytes, confirming: root.confirming, error: root.errorText, result: root.resultText}) }
    function scan(): string { root.start(["--scan"]); return "ok" }
    function state(): string { return JSON.stringify({busy:root.busy,operation:root.operation,visible:root.visibleRows.length,error:root.errorText}) }
  }
  Process {
    id: worker
    stderr: SplitParser { onRead: function(line) { root.logText=(root.logText+line+"\n").slice(-16000) } }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          if (root.cancelling || !text.trim()) return
          var data = JSON.parse(text)
          if(data.close_requested){root.resultText=data.note;root.confirming=false;rescanTimer.restart();return}
          if (data.error) { root.errorText = data.error; sounds.play("error"); return }
          if (data.scan) {
            root.resultText = "Cache removed: " + root.formatSize(data.removed_bytes) + ". " + data.errors.length + " error."
            if (data.errors.length) root.errorText = data.errors.map(function(e) { return e.error }).join("; ")
            sounds.play(data.errors.length ? "warning" : "success")
            root.displayRows(data.scan.categories)
          } else {
            if (data.categories) root.displayRows(data.categories)
            if (data.last_cleanup && !root.resultText) root.resultText = "Last cleanup: " + root.formatSize(data.last_cleanup.removed_bytes) + " cache · " + data.last_cleanup.timestamp
          }
          var coverage=(data.scan || data).coverage
          if(coverage) root.coverageText=coverage.length+" data roots scanned · "+coverage.reduce(function(n,r){return n+r.entries_checked},0)+" entries checked" + (coverage.some(function(r){return r.limited || r.errors.length}) ? " · Some locations could not be fully scanned; see Reports." : "")
          root.logText += "\n" + ((data.scan || data).categories ? "Scan complete: " + (data.scan || data).categories.length + " entries.\n" : "")
          var system = (data.scan || data).system_sources
          if (system) root.systemSummary = system.map(function(r) { return r.label + (r.path ? " · " + r.path : "") + ": " + (r.candidate_count !== undefined ? r.candidate_count + " old packages (" + root.formatSize(r.candidate_bytes) + ")" : (r.rules ? r.rules.join("; ") : r.detail)) }).join("\n")
          if (data.inventory) root.inventoryText = data.inventory.slice(0, 8).map(function(row) { return row.path.split("/").pop() + ": " + root.formatSize(row.bytes) }).join(" · ")
        } catch (e) { root.errorText = "Scan failed: " + e }
      }
    }
    onExited: function(code, status) { if(root.cancelling) { root.resultText="Scan cancelled. No files were deleted."; root.cancelling=false; return } if (code !== 0 && !root.errorText) root.errorText = "Cleaner exited with code " + code }
  }

  Timer { id:rescanTimer; interval:1500; onTriggered:root.start(["--scan"]) }
  PanelWindow {
    id: window
    visible:root.opened
    anchors { top:true; bottom:true; left:true; right:true }
    color:"transparent"; exclusionMode:ExclusionMode.Ignore
    WlrLayershell.namespace:"omarchy-menu"; WlrLayershell.layer:WlrLayer.Overlay; WlrLayershell.keyboardFocus:WlrKeyboardFocus.Exclusive
    MouseArea { anchors.fill:parent; onClicked:root.close() }
    Rectangle {
      id: card
      width:Math.min(820,parent.width-60); height:Math.min(content.implicitHeight+44,parent.height-60)
      anchors.centerIn:parent; color:Color.menu.background; border.color:Color.menu.border; radius:Style.cornerRadius
      MouseArea { anchors.fill:parent }
      ColumnLayout {
        id:content
        anchors { left:parent.left; right:parent.right; top:parent.top; margins:22 }
        spacing:12
        Keys.onEscapePressed:root.close()
        RowLayout {
          id:headerRow
          Layout.fillWidth:true
          Text { text:"CleanMacaci"; color:Color.menu.text; font.family:Style.font.menuFamily; font.pixelSize:Style.font.display; Layout.fillWidth:true }
          SoundUi.Button { soundBus:sounds; iconText:"󰅖"; tooltipText:"Close"; enabled:!root.busy; opacity:enabled?1:0.45; onClicked:root.close() }
        }
        Text { text:"Verified regenerable caches are selected automatically. Project dependencies and uncertain data require review."; color:Color.menu.text; font.family:Style.font.menuFamily; font.pixelSize:Style.font.heading; Layout.fillWidth:true; wrapMode:Text.WordWrap }
        Text { text:root.busy ? (root.cancelling ? "Cancelling scan…" : root.operation === "close" ? "Requesting application close…" : root.operation === "clean" ? "Cleaning selected files…" : "Scanning application data…") : "Selected: "+root.formatSize(root.selectedBytes)+(root.closeRows.length?" · "+root.closeRows.length+" close requests":""); color:Color.menu.text; font.family:Style.font.menuFamily; font.pixelSize:Style.font.heading }
        Rectangle { Layout.fillWidth:true; implicitHeight:1; color:Color.menu.border }
        RowLayout {
          Layout.fillWidth:true; spacing:8
          Text { text:"Items"; color:Color.menu.text; font.family:Style.font.menuFamily; font.pixelSize:Style.font.heading }
          Item { Layout.fillWidth:true }
          SoundUi.Button { soundBus:sounds; iconText:root.allSelected?"󰄲":"󰄱"; text:root.allSelected?"Deselect All":"Select All"; fontFamily:Style.font.menuFamily; fontSize:Style.font.heading; iconSize:24; enabled:!root.busy && root.visibleRows.some(function(r){return !r.blocked}); opacity:enabled?1:0.45; onClicked:root.selectVisible() }
        }
        RowLayout {
          Layout.fillWidth:true; spacing:20
          GridView {
            id:list
            Layout.fillWidth:true; Layout.preferredHeight:Math.min(300,Math.max(60,Math.ceil(root.visibleRows.length/(list.width<600?1:2))*62))
            clip:true; reuseItems:true; cacheBuffer:0; model:root.visibleRows
            cellWidth:width/(list.width<600?1:2); cellHeight:62
            delegate:Rectangle {
              required property var modelData
              required property int index
              width:list.cellWidth-8; height:58; radius:6
              activeFocusOnTab:!root.busy && (!modelData.blocked || (!!modelData.windows && modelData.windows.length>0))
              Keys.onSpacePressed:{if(modelData.blocked)root.toggleLock(modelData);else root.toggleCategory(root.rowIndex(modelData));sounds.interaction("click")}
              opacity:root.busy?0.45:1
              color:hover.containsMouse || activeFocus ? Color.menu.border : "transparent"
              MouseArea { id:hover; anchors.fill:parent; hoverEnabled:true; enabled:!root.busy; onEntered:{root.detailIndex=root.rowIndex(modelData)} onClicked:{root.detailIndex=root.rowIndex(modelData);if(!modelData.blocked){root.toggleCategory(root.detailIndex);sounds.interaction("click")}} }
              Item {
                anchors { fill:parent; leftMargin:12; rightMargin:12 }
                Item { id:check; anchors.verticalCenter:parent.verticalCenter; width:24; height:32
                  Text { anchors.centerIn:parent; text:modelData.blocked?(modelData.closeSelected?"󰌿":"󰌾"):modelData.selected?"󰄲":"󰄱"; color:Color.menu.text; opacity:modelData.blocked && !modelData.closeSelected?0.45:1; font.family:Style.font.family; font.pixelSize:24 }
                  MouseArea { anchors.fill:parent; enabled:!root.busy && (!modelData.blocked || (!!modelData.windows && modelData.windows.length>0)); cursorShape:Qt.PointingHandCursor; onClicked:{if(modelData.blocked)root.toggleLock(modelData);else root.toggleCategory(root.rowIndex(modelData))} }
                }
                Column {
                  anchors { left:check.right; leftMargin:10; right:amount.left; rightMargin:8; verticalCenter:parent.verticalCenter }
                  spacing:3
                  Text { width:parent.width; text:modelData.label; elide:Text.ElideRight; color:Color.menu.text; opacity:modelData.blocked?0.6:1; font.family:Style.font.menuFamily; font.pixelSize:Style.font.heading }
                  Text { text:modelData.blocked?(modelData.closeSelected?"WILL CLOSE":modelData.confidence==="preserve"?"PROTECTED":"CLOSE APP FIRST"):modelData.default?"SAFE · AUTO": "REVIEW"; color:Color.menu.text; opacity:0.65; font.family:Style.font.menuFamily; font.pixelSize:Style.font.bodySmall }
                }
                Text { id:amount; anchors { right:parent.right; verticalCenter:parent.verticalCenter } text:root.formatSize(modelData.bytes); color:Color.menu.text; font.family:Style.font.menuFamily; font.pixelSize:Style.font.body }
              }
            }
            Text { anchors.centerIn:parent; visible:root.visibleRows.length===0; text:root.busy?"Scanning…":"No entries in this view."; color:Color.menu.text; font.family:Style.font.menuFamily; font.pixelSize:Style.font.heading }
          }
        }
        Rectangle { Layout.fillWidth:true; implicitHeight:1; color:Color.menu.border }
        RowLayout {
          Layout.fillWidth:true
          Flickable {
            id:logScroll; Layout.fillWidth:true; Layout.preferredHeight:90
            clip:true; contentWidth:width; contentHeight:logLabel.implicitHeight
            TextEdit {
              id:logLabel; width:logScroll.width; readOnly:true; selectByMouse:true; color:Color.menu.text; font.family:Style.font.family; font.pixelSize:Style.font.body+2; wrapMode:TextEdit.WrapAnywhere
              text:root.busy || root.errorText ? (root.errorText || root.logText) : root.detailRow ? root.detailRow.reason+"\n"+root.detailRow.paths.join("\n") : (root.inventoryText ? root.inventoryText+"\n" : "")+(root.resultText ? root.resultText+"\n" : "")+root.coverageText+"\n"+root.systemSummary
              onTextChanged:if(root.busy)Qt.callLater(function(){logScroll.contentY=Math.max(0,logScroll.contentHeight-logScroll.height)})
            }
          }
          SoundUi.Button { soundBus:sounds; iconText:"󰆏"; iconSize:22; tooltipText:root.busy?"Copy log":"Copy scan report"; enabled:!!root.logText || root.categories.length>0; opacity:enabled?1:0.45; onClicked:root.copyReport() }
        }
        Text { visible:root.confirming; text:"Permanently remove "+root.formatSize(root.selectedBytes)+" of selected files?"; color:Color.menu.text; font.family:Style.font.menuFamily; font.pixelSize:Style.font.heading; Layout.fillWidth:true; wrapMode:Text.WordWrap }
        Rectangle { Layout.fillWidth:true; implicitHeight:1; color:Color.menu.border }
        RowLayout {
          id:footerActions
          Layout.fillWidth:true; spacing:12
          SoundUi.Button { soundBus:sounds; Layout.fillWidth:true; Layout.preferredWidth:1; text:root.closeRows.length?(root.confirming?"Confirm Close Apps":"Close Apps & Rescan"):(root.confirming?"Confirm Clean":"Clean Selected"); iconText:"󰃢"; fontFamily:Style.font.menuFamily; fontSize:Style.font.heading+1; bordered:true; focusable:true; enabled:!root.busy && (root.selectedBytes>0 || root.closeRows.length>0); opacity:enabled?1:0.45; onClicked:root.cleanSelected() }
          SoundUi.Button { soundBus:sounds; Layout.fillWidth:true; Layout.preferredWidth:1; text:root.busy && root.operation==="scan"?(root.cancelling?"Cancelling…":"Cancel Scan"):"Scan Again"; iconText:root.busy?"󰅖":"󰑐"; fontFamily:Style.font.menuFamily; fontSize:Style.font.heading+1; bordered:true; focusable:true; enabled:!root.busy || (root.operation==="scan" && !root.cancelling); opacity:enabled?1:0.45; background:root.busy && root.operation==="scan"?"#59383c":"transparent"; onClicked:{if(root.busy)root.cancelScan();else root.start(["--scan"])} }
          SoundUi.Button { soundBus:sounds; iconText:"󰅀"; Layout.fillHeight:true; tooltipText:"More actions"; fontSize:Style.font.heading+1; bordered:true; focusable:true; enabled:!root.busy; opacity:enabled?1:0.45; onClicked:{root.toolGroup="main";root.toolsOpen=!root.toolsOpen} }
        }

      }
      MouseArea { visible:root.toolsOpen; anchors.fill:parent; z:3; onClicked:root.toolsOpen=false }
      Rectangle {
        visible:root.toolsOpen; z:4
        x:parent.width-width-22; y:Math.max(22,content.y+footerActions.y-height-8)
        width:240; height:toolItems.implicitHeight+24
        color:Color.menu.background; border.color:Color.menu.border; radius:Style.cornerRadius
        MouseArea { anchors.fill:parent }
        ColumnLayout {
          id:toolItems; anchors { left:parent.left; right:parent.right; top:parent.top; margins:12 } spacing:4
          Text { text:root.toolGroup==="system"?"System Cleanup":"More Actions"; color:Color.menu.text; font.family:Style.font.menuFamily; font.pixelSize:Style.font.heading; Layout.fillWidth:true }
          Rectangle { Layout.fillWidth:true; implicitHeight:1; color:Color.menu.border }
          SoundUi.Button { focusable:true; soundBus:sounds; visible:root.toolGroup==="main"; text:"Space Usage"; iconText:"󰋊"; leftAlign:true; Layout.fillWidth:true; fontFamily:Style.font.menuFamily; fontSize:Style.font.heading; enabled:!root.busy; onClicked:root.start(["--inventory"]) }
          SoundUi.Button { focusable:true; soundBus:sounds; visible:root.toolGroup==="main"; text:"System Cleanup  ›"; iconText:"󰒓"; leftAlign:true; Layout.fillWidth:true; fontFamily:Style.font.menuFamily; fontSize:Style.font.heading; enabled:!root.busy; onClicked:root.toolGroup="system" }
          SoundUi.Button { focusable:true; soundBus:sounds; visible:root.toolGroup==="main"; text:"Reports"; iconText:"󰈙"; leftAlign:true; Layout.fillWidth:true; fontFamily:Style.font.menuFamily; fontSize:Style.font.heading; enabled:!root.busy; onClicked:{root.toolsOpen=false;Quickshell.execDetached(["xdg-open",root.statePath])} }
          Repeater {
            model:root.toolGroup==="system"?[{label:"Package Cache",scope:"packages",icon:"󰏗"},{label:"Archived Logs",scope:"journal",icon:"󰈙"},{label:"Temporary Files",scope:"temporary",icon:"󰉋"},{label:"All System Cleanup",scope:"all",icon:"󰒓"}]:[]
            delegate:SoundUi.Button { focusable:true; required property var modelData; soundBus:sounds; text:modelData.label; iconText:modelData.icon; leftAlign:true; Layout.fillWidth:true; fontFamily:Style.font.menuFamily; fontSize:Style.font.heading; enabled:!root.busy; onClicked:{root.toolsOpen=false;Quickshell.execDetached(["xdg-terminal-exec","--app-id=org.omarchy.terminal","--title=System Cleanup","-e","bash",root.toolPath("system-cleaner.sh"),modelData.scope])} }
          }
          Rectangle { visible:root.toolGroup==="system"; Layout.fillWidth:true; implicitHeight:1; color:Color.menu.border }
          SoundUi.Button { focusable:true; visible:root.toolGroup==="system"; soundBus:sounds; text:"Back"; iconText:"󰁍"; leftAlign:true; Layout.fillWidth:true; fontFamily:Style.font.menuFamily; fontSize:Style.font.heading; onClicked:root.toolGroup="main" }
        }
      }
    }
  }
}
