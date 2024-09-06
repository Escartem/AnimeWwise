import os
import sys
import json
import math
import extract
from PyQt5 import uic
from requests import get
from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, QMetaType, Qt
from PyQt5.QtWidgets import QMessageBox, QMainWindow, QApplication, QFileDialog, QHeaderView, QAbstractItemView, QTreeWidgetItem

QMetaType.type("QTextCursor")

class TextEditStream(QObject):
	append_text = pyqtSignal(str)

	def __init__(self, text_edit):
		super().__init__()
		self.text_edit = text_edit
		self.append_text.connect(self._append_text)

	def write(self, text):
		self.append_text.emit(text)

	def flush(self):
		pass

	def _append_text(self, text):
		self.text_edit.moveCursor(QTextCursor.End)
		self.text_edit.insertPlainText(text)
		self.text_edit.moveCursor(QTextCursor.End)

class BackgroundWorker(QObject):
	finished = pyqtSignal(dict)
	progress = pyqtSignal(list)

	def __init__(self, action, extract, data):
		super().__init__()
		self.action = action
		self.extract = extract

		if action == "load":
			self.input = data["input"]
			self.map = data["map"]
			self.diff = data["diff"]
		if action == "extract":
			self.input = data["input"]
			self.files = data["files"]
			self.format = data["format"]
			self.output = data["output"]

	def run(self):
		if self.action == "load":
			print("Loading files and mapping if necessary...")
			fileStructure = self.extract.load_folder(self.map, self.input, self.diff, progress=self.progress.emit)
			if fileStructure is None:
				self.finished.emit({"action": "error", "content": {"msg": "Nothing found !", "state": 1}})
				print("Nothing found !")
				return
			print("Building file structure...")
			self.finished.emit({"action": "load", "content": fileStructure})
		if self.action == "extract":
			if len(self.files) == 0:
				self.finished.emit({"action": "error", "content": {"msg": "Nothing selected !", "state": 2}})
				return
			print(f"Extracting {len(self.files)} files...")
			self.extract.extract_files(self.input, self.files, self.output, self.format, progress=self.progress.emit)
			self.finished.emit({"action": "extract"})

class AnimeWwise(QMainWindow):
	def __init__(self):
		super(AnimeWwise, self).__init__()
		uic.loadUi("gui.ui", self)
		self.maps = self.getMaps()
		self.folders = {
			"input": "",
			"output": "",
			"diff": ""
		}
		self.setupActions()
		sys.stdout = TextEditStream(self.console)
		self.extract = extract.WwiseExtract()
		self.checkMapsUpdates()

		# utils
		self.selectFolder = lambda: QFileDialog.getExistingDirectory(self, "Select Folder")

	def checkMapsUpdates(self):
		print("Checking updates")
		try:
			getVersion = lambda m: sum([int(e["version"].replace(".", "")) for e in m["maps"]])
			mapsVersion = getVersion(self.maps)
			latestMaps = get("https://raw.githubusercontent.com/Escartem/AnimeWwise/master/maps/index.json")
			
			if latestMaps.status_code == 200:
				latestVersion = getVersion(json.loads(latestMaps.text))

			if mapsVersion < latestVersion:
				print("Update found")
				QMessageBox.information(None, "Info", "Newer version of the mappings are availble, please update the program", QMessageBox.Ok)
			else:
				print("No updates")
		except:
			print("Failed to check updates")

	def getMaps(self):
		with open("maps/index.json", "r") as f:
			maps = json.loads(f.read())
			f.close()

		return maps

	def setFolder(self, elem, folder):
		path = self.selectFolder()
		self.folders[folder] = path
		elem.setText(path)

	def setupActions(self):
		self.changeInput.clicked.connect(lambda: self.setFolder(self.inputPath, "input"))
		self.changeAltInput.clicked.connect(lambda: self.setFolder(self.altInputPath, "diff"))
		self.changeOutput.clicked.connect(lambda: self.setFolder(self.outputPath, "output"))

		self.outputFormat.addItems(["wem (fastest)", "wav (fast)", "mp3 (slow)", "ogg (slow)"])
		self.assetMap.addItems(["No map", *[f'{e["game"]} - v{e["version"]}' for e in self.maps["maps"]]])

		self.tabs.setTabEnabled(1, False)
		self.tabs.setTabEnabled(2, False)

		self.loadFilesButton.clicked.connect(lambda: self.loadFiles())

		self.actionReset.triggered.connect(lambda: self.resetApp())
		self.actionExit.triggered.connect(lambda: self.close())

		self.extractSelected.clicked.connect(lambda: self.extractItems(False))
		self.extractAll.clicked.connect(lambda: self.extractItems(True))

		self.searchAsset.textChanged.connect(lambda: self.filterAsset())

	# workers
	@pyqtSlot(list)
	def progressBarSlot(self, progress):
		if progress[0] == "load":
			self.loadProgress.setValue(math.ceil(progress[1]))
		if progress[0] == "total":
			self.totalProgress.setValue(math.ceil(progress[1]))
		elif progress[0] == "file":
			self.fileProgress.setValue(math.ceil(progress[1]))

	@pyqtSlot(dict)
	def handleFinished(self, data):
		if data["action"] == "load":
			self.fileStructure = data["content"]
			self.updateTreeWidget(self.fileStructure)
			self.tabs.setTabEnabled(0, False)
			self.tabs.setTabEnabled(1, True)
			self.tabs.setTabEnabled(2, True)
			self.tabs.setCurrentIndex(1)
			print("Done !")
		if data["action"] == "error":
			QMessageBox.warning(None, "Warning", data["content"]["msg"], QMessageBox.Ok)
			state = data["content"]["state"]
			if state == 1:
				self.tabs.setTabEnabled(0, True)
			elif state == 2:
				self.tabs.setTabEnabled(1, True)
				self.tabs.setTabEnabled(2, True)
		if data["action"] == "extract":
			self.tabs.setTabEnabled(1, True)
			self.tabs.setTabEnabled(2, True)
			self.tabs.setCurrentIndex(2)
			print("Finished extracting everything !")
			os.startfile(self.folders["output"])

	# page 1 - config
	def loadFiles(self):
		if self.folders["input"] == "":
			QMessageBox.warning(None, "Warning", "Missing input folder !", QMessageBox.Ok)
			return

		_map = self.assetMap.currentIndex()
		if _map != 0:
			_map = self.maps["maps"][_map-1]["name"]
		else:
			_map = None

		self.tabs.setTabEnabled(0, False)
		self.resetTreeWidget()

		# why is all this required for threading damnit
		self.backgroundThread = QThread()
		self.backgroundWorker = BackgroundWorker("load", self.extract, {"input": self.folders["input"], "map": _map, "diff": self.folders["diff"]})
		self.backgroundWorker.moveToThread(self.backgroundThread)
		self.backgroundThread.started.connect(self.backgroundWorker.run)
		self.backgroundWorker.finished.connect(self.handleFinished)
		self.backgroundWorker.finished.connect(self.backgroundThread.quit)
		self.backgroundWorker.finished.connect(self.backgroundWorker.deleteLater)
		self.backgroundThread.finished.connect(self.backgroundThread.deleteLater)

		self.backgroundWorker.progress.connect(self.progressBarSlot)
		self.backgroundThread.start()

	# page 2 - browsing
	def filterAsset(self):
		search = self.searchAsset.text()
		if search == "":
			self.updateTreeWidget(self.fileStructure)
			return
		result = self.searchFiles(self.fileStructure, search)
		self.updateTreeWidget(result)

	def searchFiles(self, data, substring, current_path=""):
		result = {"folders": {}, "files": []}

		result["files"] = [file for file in data.get("files", []) if substring in file[0]]

		for folder_name, folder_data in data.get("folders", {}).items():
			subfolder_result = self.searchFiles(folder_data, substring)
			if subfolder_result["files"] or subfolder_result["folders"]:
				result["folders"][folder_name] = subfolder_result

		return result

	def resetTreeWidget(self):
		self.treeWidget.clear()
		self.tabs.setTabEnabled(1, False)

	def updateTreeWidget(self, structure):
		self.treeWidget.clear()
		self.treeWidget.setColumnCount(3)
		self.treeWidget.setHeaderLabels(["Name", "Offset", "Size", "Source"])
		
		self.addItems(None, structure)

		self.treeWidget.expandAll()
		self.treeWidget.header().setSectionResizeMode(0, QHeaderView.Stretch)
		self.treeWidget.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
		self.treeWidget.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
		self.treeWidget.setHeaderHidden(False)

		self.treeWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
		self.treeWidget.setDragDropMode(QAbstractItemView.NoDragDrop)

	def addItems(self, parent, element):
		for folder_name in sorted(element.get("folders", {}).keys()):
			folder_content = element["folders"][folder_name]
			folder_item = QTreeWidgetItem([folder_name, "", "", ""])
			folder_item.setFlags(folder_item.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
			folder_item.setCheckState(0, Qt.Unchecked)
			if parent is None:
				self.treeWidget.addTopLevelItem(folder_item)
			else:
				parent.addChild(folder_item)
			self.addItems(folder_item, folder_content)

		for file in sorted(element.get("files", [])):
			file_item = QTreeWidgetItem([str(file[0]), str(hex(file[1])), str(file[2]), str(file[3])])
			file_item.setFlags(file_item.flags() | Qt.ItemIsUserCheckable)
			file_item.setCheckState(0, Qt.Unchecked)
			if parent is None:
				self.treeWidget.addTopLevelItem(file_item)
			else:
				parent.addChild(file_item)

	# page 3 - extraction
	def extractItems(self, _all):
		if self.folders["output"] == "":
			QMessageBox.warning(None, "Warning", "Missing output folder !", QMessageBox.Ok)
			return

		checked_items = []
	
		def check_items(item, _all):
			if item.checkState(0) == Qt.Checked or _all:
				if item.text(1) != "":
					checked_items.append(self.getFileMeta(item))
			for i in range(item.childCount()):
				check_items(item.child(i), _all)
		
		for i in range(self.treeWidget.topLevelItemCount()):
			check_items(self.treeWidget.topLevelItem(i), _all)

		self.tabs.setTabEnabled(1, False)
		self.tabs.setTabEnabled(2, False)
		self.tabs.setCurrentIndex(2)

		# yet another block of threading bs
		self.backgroundThread = QThread()
		self.backgroundWorker = BackgroundWorker("extract", self.extract, {"input": self.folders["input"], "files": checked_items, "format": self.outputFormat.currentText()[:3], "output": self.folders["output"]})
		self.backgroundWorker.moveToThread(self.backgroundThread)
		self.backgroundThread.started.connect(self.backgroundWorker.run)
		self.backgroundWorker.finished.connect(self.handleFinished)
		self.backgroundWorker.finished.connect(self.backgroundThread.quit)
		self.backgroundWorker.finished.connect(self.backgroundWorker.deleteLater)
		self.backgroundThread.finished.connect(self.backgroundThread.deleteLater)

		self.backgroundWorker.progress.connect(self.progressBarSlot)
		self.backgroundThread.start()

	def getFileMeta(self, item):
		path = []
		current_item = item

		while current_item is not None:
			path.insert(0, current_item.text(0))
			current_item = current_item.parent()
		
		return {
			"name": item.text(0),
			"path": path[:-1] if path[0] in ["changed_files", "new_files"] else path[1:-1],
			"source": item.text(3),
			"offset": int(item.text(1), 16),
			"size": int(item.text(2))
		}

	# misc
	def resetApp(self):
		self.resetTreeWidget()
		self.extract.reset()
		self.tabs.setTabEnabled(0, True)
		self.tabs.setTabEnabled(1, False)
		self.tabs.setTabEnabled(2, False)
		print("Reset !")

	def _appendText(self, text):
		cursor = self.console.textCursor()
		cursor.movePosition(cursor.End)
		cursor.insertText(text)
		self.console.setTextCursor(cursor)
		self.console.ensureCursorVisible()

if __name__ == "__main__":
	app = QApplication(sys.argv)
	window = AnimeWwise()
	window.show()
	sys.exit(app.exec_())
