import os
import sys
import json
import time
import mapper
import extract
from PyQt5 import uic
from PyQt5.QtGui import QTextCursor, QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QMessageBox, QMainWindow, QApplication, QFileDialog, QHeaderView, QAbstractItemView, QTreeWidgetItem
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, QMetaType, Qt

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
		if action == "extract":
			self.input = data["input"]

	def run(self):
		if self.action == "load":
			print("Loading files and mapping if necessary...")
			fileStructure = self.extract.load_folder(self.map, self.input)
			print("Done !")
			self.finished.emit({"action": "load", "content": fileStructure})
		if self.action == "extract":
			self.extract.extract_files(self.input)

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

		# utils
		self.selectFolder = lambda: QFileDialog.getExistingDirectory(self, "Select Folder")

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

		self.actionExtractSelected.triggered.connect(lambda: self.extractItems(False))
		self.actionExtractAll.triggered.connect(lambda: self.extractItems(True))

	# workers
	@pyqtSlot(list)
	def progressBarSlot(self, progress):
		if progress[0] == "total":
			self.progress.setValue(progress[1])
		elif progress[0] == "task":
			self.taskProgress.setValue(progress[1])

	@pyqtSlot(dict)
	def handleFinished(self, data):
		if data["action"] == "load":
			self.fileStructure = data["content"]
			self.updateTreeWidget()
			self.tabs.setTabEnabled(0, False)
			self.tabs.setTabEnabled(1, True)
			self.tabs.setTabEnabled(2, True)
			self.tabs.setCurrentIndex(1)

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
		self.backgroundWorker = BackgroundWorker("load", self.extract, {"input": self.folders["input"], "map": _map})
		self.backgroundWorker.moveToThread(self.backgroundThread)
		self.backgroundThread.started.connect(self.backgroundWorker.run)
		self.backgroundWorker.finished.connect(self.handleFinished)
		self.backgroundWorker.finished.connect(self.backgroundThread.quit)
		self.backgroundWorker.finished.connect(self.backgroundWorker.deleteLater)
		self.backgroundThread.finished.connect(self.backgroundThread.deleteLater)

		self.backgroundWorker.progress.connect(self.progressBarSlot)
		self.backgroundThread.start()

	# page 2 - browsing
	def resetTreeWidget(self):
		self.treeWidget.clear()
		self.tabs.setTabEnabled(1, False)

	def updateTreeWidget(self):
		self.treeWidget.clear()
		self.treeWidget.setColumnCount(3)
		self.treeWidget.setHeaderLabels(["Name", "Offset", "Size"])
		
		self.addItems(None, self.fileStructure)

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
			folder_item = QTreeWidgetItem([folder_name, "", ""])
			folder_item.setFlags(folder_item.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
			folder_item.setCheckState(0, Qt.Unchecked)
			if parent is None:
				self.treeWidget.addTopLevelItem(folder_item)
			else:
				parent.addChild(folder_item)
			self.addItems(folder_item, folder_content)

		for file in sorted(element.get("files", [])):
			file_item = QTreeWidgetItem([str(file[0]), str(hex(file[1])), str(file[2])])
			file_item.setFlags(file_item.flags() | Qt.ItemIsUserCheckable)
			file_item.setCheckState(0, Qt.Unchecked)
			if parent is None:
				self.treeWidget.addTopLevelItem(file_item)
			else:
				parent.addChild(file_item)

	# page 3 - extraction
	def extractItems(self, _all):
		checked_items = []
	
		def check_items(item, _all):
			if item.checkState(0) == Qt.Checked or _all:
				checked_items.append([item.text(column) for column in range(item.columnCount())])
			for i in range(item.childCount()):
				check_items(item.child(i), _all)
		
		for i in range(self.treeWidget.topLevelItemCount()):
			check_items(self.treeWidget.topLevelItem(i), _all)
		
		print(checked_items)

		# yet another block of threading bs
		self.backgroundThread = QThread()
		self.backgroundWorker = BackgroundWorker("extract", self.extract, {"input": self.folders["input"], "files": checked_items})
		self.backgroundWorker.moveToThread(self.backgroundThread)
		self.backgroundThread.started.connect(self.backgroundWorker.run)
		self.backgroundWorker.finished.connect(self.handleFinished)
		self.backgroundWorker.finished.connect(self.backgroundThread.quit)
		self.backgroundWorker.finished.connect(self.backgroundWorker.deleteLater)
		self.backgroundThread.finished.connect(self.backgroundThread.deleteLater)

		self.backgroundWorker.progress.connect(self.progressBarSlot)
		self.backgroundThread.start()

	# misc
	def resetApp(self):
		self.resetTreeWidget()
		self.extract.reset()
		self.tabs.setTabEnabled(0, True)
		self.tabs.setTabEnabled(1, False)
		self.tabs.setTabEnabled(2, False)

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
