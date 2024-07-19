import os
import sys
import json
import time
import mapper
import extract
from PyQt5 import uic
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QMessageBox, QMainWindow, QApplication, QFileDialog
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, QMetaType

QMetaType.type('QTextCursor')

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

class ExtractionWorker(QObject):
	finished = pyqtSignal()
	progress = pyqtSignal(list)

	def __init__(self, folders, _map, _format):
		super().__init__()
		self.folders = folders
		self.map = _map
		self.format = _format

	def run(self):
		_map = None
		if self.map:
			_map = mapper.Mapper(os.path.join(os.getcwd(), f"maps/{self.map}"))
			print("\n==========\n")
		self.progress.emit(["total", 5])
		extracter = extract.WwiseExtract(_map, self.format, *self.folders.values(), progress=self.progress.emit)
		extracter.extract()
		self.finished.emit()

class AnimeWwise(QMainWindow):
	def __init__(self):
		super(AnimeWwise, self).__init__()
		uic.loadUi("gui.ui", self)
		# self.setupUi(self)
		self.maps = self.getMaps()
		self.folders = {
			"input": "",
			"output": "",
			"diff": ""
		}
		self.setupActions()
		sys.stdout = TextEditStream(self.console)

		# utils
		self.selectFolder = lambda: QFileDialog.getExistingDirectory(self, "Select Folder")

	def setFolder(self, elem, folder):
		path = self.selectFolder()
		self.folders[folder] = path
		elem.setText(path)

	def setupActions(self):
		self.changeInput.clicked.connect(lambda: self.setFolder(self.inputPath, "input"))
		self.changeAltInput.clicked.connect(lambda: self.setFolder(self.altInputPath, "diff"))
		self.changeOutput.clicked.connect(lambda: self.setFolder(self.outputPath, "output"))

		self.outputFormat.addItems(["mp3", "ogg"])
		self.assetMap.addItems(["No map", *[f'{e["game"]} - v{e["version"]}' for e in self.maps["maps"]]])

		self.startButton.clicked.connect(lambda: self.start())

	def getMaps(self):
		with open("maps/index.json", "r") as f:
			maps = json.loads(f.read())
			f.close()

		return maps

	@pyqtSlot(list)
	def progressBarSlot(self, progress):
		if progress[0] == "total":
			self.progress.setValue(progress[1])
		elif progress[0] == "task":
			self.taskProgress.setValue(progress[1])

	def start(self):
		if "" in [self.folders["input"], self.folders["output"]]:
			QMessageBox.warning(None, "Warning", "Missing input/output folder !", QMessageBox.Ok)
			return

		_map = self.assetMap.currentIndex()
		if _map != 0:
			_map = self.maps["maps"][_map-1]["name"]
		else:
			_map = None

		self.extractThread = QThread()
		self.extractWorker = ExtractionWorker(self.folders, _map, self.outputFormat.currentText())
		self.extractWorker.moveToThread(self.extractThread)
		self.extractThread.started.connect(self.extractWorker.run)
		self.extractWorker.finished.connect(self.extractThread.quit)
		self.extractWorker.finished.connect(self.extractWorker.deleteLater)
		self.extractThread.finished.connect(self.extractThread.deleteLater)

		self.extractWorker.progress.connect(self.progressBarSlot)
		self.extractThread.start()

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
