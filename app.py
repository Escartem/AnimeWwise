import os
import sys
import json
import math
import time
import extract
import platform
import urllib
import webbrowser
from PyQt5 import uic
from requests import get
from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, QMetaType, Qt
from PyQt5.QtWidgets import QDesktopWidget, QDialog, QMessageBox, QMainWindow, QApplication, QFileDialog, QHeaderView, QAbstractItemView, QTreeWidgetItem, QAction, QActionGroup

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
			self.base = data["base"]
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
			fileStructure = self.extract.load_folder(self.map, self.input, self.diff, self.base, progress=self.progress.emit)
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

class UpdaterWorker(QObject):
	finished = pyqtSignal(bool)
	progress = pyqtSignal(list)

	def __init__(self):
		super().__init__()

	def run(self):
		try:
			# know current and latest maps
			self.progress.emit([0, "Fetching index..."])
			ver = lambda s: int(s.replace(".", ""))

			index = open("version.json", "r")
			currentMaps = json.loads(index.read())["maps"]
			index.close()

			latestMaps = get("https://raw.githubusercontent.com/Escartem/AnimeWwise/master/maps/index.json")

			if latestMaps.status_code == 200:
				latestMaps = json.loads(latestMaps.text)

			# do each game
			n_games = len(latestMaps["maps"])
			game_size = 95 // n_games
			for i in range(n_games):
				current = currentMaps["maps"][i]
				latest = latestMaps["maps"][i]
				name = f"maps/{latest['name']}"

				if (ver(current["version"]) < ver(latest["version"])) or not os.path.isfile(name):
					self.progress.emit([5 + game_size * i, f'Updating {latest["game"]} to {latest["version"]}'])

					url = f"https://raw.githubusercontent.com/Escartem/AnimeWwise/master/{name}"
					urllib.request.urlretrieve(url, "maps/temp.map")

					if os.path.isfile(name):
						os.remove(name)
					os.rename("maps/temp.map", name)

					# update index
					currentMaps["maps"][i]["version"] = latest["version"]

			# save new index
			index_sum = sum([ver(e["version"]) for e in currentMaps["maps"]])

			with open("version.json", "r+") as f:
				data = json.loads(f.read())
				data["mapsVersion"] = index_sum
				data["maps"] = currentMaps
				f.seek(0)
				f.write(json.dumps(data, indent=4))
				f.truncate()
				f.close()

			# done
			self.progress.emit([100, "Update finished ! The program will start shortly..."])
		except Exception as e:
			# failure :(
			self.progress.emit([100, f"Update failed ! The program will start shortly... | {e}"])

		time.sleep(3)
		self.finished.emit(True)


class Updater(QDialog):
	def __init__(self):
		super(Updater, self).__init__()
		uic.loadUi("updater.ui", self)
		self.setWindowFlag(Qt.WindowCloseButtonHint, False)
		self.center()
		self.update()

	def center(self):
		qr = self.frameGeometry()
		cp = QDesktopWidget().availableGeometry().center()
		qr.moveCenter(cp)
		self.move(qr.topLeft())

	def update(self):
		self.backgroundThread = QThread()
		self.backgroundWorker = UpdaterWorker()
		self.backgroundWorker.moveToThread(self.backgroundThread)
		self.backgroundThread.started.connect(self.backgroundWorker.run)
		self.backgroundWorker.finished.connect(self.updateFinished)
		self.backgroundWorker.finished.connect(self.backgroundThread.quit)
		self.backgroundWorker.finished.connect(self.backgroundWorker.deleteLater)
		self.backgroundThread.finished.connect(self.backgroundThread.deleteLater)

		self.backgroundWorker.progress.connect(self.updateProgress)
		self.backgroundThread.start()

	@pyqtSlot(bool)
	def updateFinished(self):
		self.close()

	@pyqtSlot(list)
	def updateProgress(self, data):
		self.progressBar.setValue(data[0])
		if len(data) == 2:
			self.status.setText(data[1])

class AnimeWwise(QMainWindow):
	def __init__(self):
		super(AnimeWwise, self).__init__()
		uic.loadUi("gui.ui", self)
		self.versions = self.getJson("version")
		self.version = self.versions["version"]
		self.maps = self.version["maps"]
		self.setWindowTitle(f'AnimeWwise | v{".".join(list(str(self.version)))}')
		self.folders = {
			"input": "",
			"output": "",
			"diff": ""
		}
		self.format = "wav"
		self.fileStructure = {"folders": {}, "files": []}
		self.setupActions()
		sys.stdout = TextEditStream(self.console)
		self.extract = extract.WwiseExtract()
		self.checkUpdates()
		self.totalProgress.setMaximum(10000)
		self.fileProgress.setMaximum(10000)

		# utils
		self.selectFolder = lambda: QFileDialog.getExistingDirectory(self, "Select Folder")

	def checkUpdates(self):
		print("Checking for updates...")
		try:
			currentVersion = self.versions
			latestVersionReq = get("https://raw.githubusercontent.com/Escartem/AnimeWwise/master/version.json")
			
			if latestVersionReq.status_code == 200:
				latestVersion = json.loads(latestVersionReq.text)

			if currentVersion["version"] < latestVersion["version"]:
				print("Update found !")
				QMessageBox.information(None, "Info", "Newer version of the program is availble, please update it.", QMessageBox.Ok)
			elif currentVersion["mapsVersion"] < latestVersion["mapsVersion"]:
				print("Update found !")
				QMessageBox.information(None, "Info", "Newer version of the mappings are availble, the program will update them now.", QMessageBox.Ok)
				self.updaterWindow = Updater()
				self.updaterWindow.exec_()
				self.maps = latestVersion["maps"]
			else:
				print("No updates")
		except:
			print("Failed to check updates :(")

	def getJson(self, path):
		with open(f"{path}.json", "r") as f:
			data = json.loads(f.read())
			f.close()

		return data

	def setFolder(self, elem=None, folder=None):
		path = self.selectFolder()
		self.folders[folder] = path
		if elem:
			elem.setText(path)

	def setupActions(self):
		self.changeAltInput.clicked.connect(lambda: self.setFolder(self.altInputPath, "diff"))

		self.pckLoadTypeCombo.addItems(["Folder", "File"])
		self.pckLoadTypeCombo.currentIndexChanged.connect(self.loadTypeChange)
		self.loadType = "folder"

		self.assetMap.addItems(["No map", *[f'{e["game"]} - v{e["version"]}' for e in self.maps["maps"]]])

		self.setExtractionState(False)

		self.updateTreeWidget(self.fileStructure)

		self.loadFilesButton.clicked.connect(lambda: self.loadFiles())

		self.actionReset.triggered.connect(lambda: self.resetApp())
		self.actionExit.triggered.connect(lambda: self.close())

		self.actionExpand_all.triggered.connect(lambda: self.treeWidget.expandAll())
		self.actionCollapse_all.triggered.connect(lambda: self.treeWidget.collapseAll())

		self.actionExtract_Selected.triggered.connect(lambda: self.extractItems(False))
		self.actionExtract_All.triggered.connect(lambda: self.extractItems(True))

		self.actionReport_a_bug.triggered.connect(lambda: self.openLink(0))
		self.actionSource_code.triggered.connect(lambda: self.openLink(1))
		self.actionDiscord.triggered.connect(lambda: self.openLink(2))

		self.searchAsset.textChanged.connect(lambda: self.filterAsset())

		# output format
		formats = ["wem (fastest)", "wav (fast)", "mp3 (slow)", "ogg (slow)"]
		action_group = QActionGroup(self)
		action_group.setExclusive(True)

		for index, item_name in enumerate(formats):
			action = QAction(item_name, self)
			action.setCheckable(True)
			if index == 1:
				action.setChecked(True)
			self.menuOutput_format.addAction(action)
			action_group.addAction(action)

		action_group.triggered.connect(self.updateFormat)

	# utils
	def loadTypeChange(self, event):
		if event == 0:
			self.pckSubFold.setEnabled(True)
			self.loadType = "folder"
		elif event == 1:
			self.pckSubFold.setEnabled(False)
			self.loadType = "file"

	def updateFormat(self, event):
		text = event.text()
		self.format = text.split(" ")[0]

	def openLink(self, id):
		urls = [
			"https://github.com/Escartem/AnimeWwise/issues/new",
			"https://github.com/Escartem/AnimeWwise",
			"https://discord.gg/fzRdtVh"
		]

		webbrowser.open(urls[id])

	def setExtractionState(self, state):
		self.actionExtract_Selected.setEnabled(state)
		self.actionExtract_All.setEnabled(state)
		self.actionExpand_all.setEnabled(state)
		self.actionCollapse_all.setEnabled(state)

	def displaySize(self, size):
		if size < 1024:
			return f"{size} b"
		elif size > 1024 and size < 1048576:
			return f"{size//1024} KiB"
		elif size > 1048576 and size < 1073741824:
			return f"{size//1048576} MiB"
		elif size > 1073741824:
			return f"{size//1073741824} GiB"

	# workers
	@pyqtSlot(list)
	def progressBarSlot(self, progress):
		progress_value = math.ceil(progress[1]*100)
		if progress[0] == "total":
			self.totalProgress.setValue(progress_value)
			self.totalProgress.setFormat("%.02f %%" % (progress_value / 100))
		elif progress[0] == "file":
			self.fileProgress.setValue(progress_value)
			self.fileProgress.setFormat("%.02f %%" % (progress_value / 100)) 

	@pyqtSlot(dict)
	def handleFinished(self, data):
		if data["action"] == "load":
			self.fileStructure = data["content"]
			self.updateTreeWidget(self.fileStructure)
			self.loadFilesButton.setEnabled(True)
			self.setExtractionState(True)
			self.tabs.setCurrentIndex(1)
			print("Done !")
		if data["action"] == "error":
			QMessageBox.warning(None, "Warning", data["content"]["msg"], QMessageBox.Ok)
			state = data["content"]["state"]
			if state == 1:
				self.loadFilesButton.setEnabled(True)
			if state == 2:
				self.setExtractionState(True)
		if data["action"] == "extract":
			self.setExtractionState(True)
			print("Finished extracting everything !")

			if platform.system() == "Windows":
				os.startfile(self.folders["output"])

	# page 1 - config
	def loadFiles(self):
		if self.loadType == "folder":
			self.setFolder(folder="input")
			files = []
			if self.folders["input"]:
				if self.pckSubFold.isChecked():
					files = [os.path.join(root, f) for root, dirs, files_in_dir in os.walk(self.folders["input"]) for f in files_in_dir if f.endswith(".pck")]
				else:
					files = [os.path.join(self.folders["input"], f) for f in os.listdir(self.folders["input"]) if f.endswith(".pck")]
		elif self.loadType == "file":
			path = QFileDialog.getOpenFileName(self, "Select .pck File", "", "PCK Files (*.pck)", options=QFileDialog.Options())
			self.folders["input"] = os.path.dirname(path[0])
			files = [path[0]]

		if len(files) == 0 or files[0] == "":
			QMessageBox.warning(None, "Warning", "Nothing to load !", QMessageBox.Ok)
			return

		self.currentInput = self.folders["input"]
		if not self.folders["input"]:
			self.currentInput = os.path.dirname(path[0])

		_map = self.assetMap.currentIndex()
		if _map != 0:
			_map = self.maps["maps"][_map-1]["name"]
		else:
			_map = None

		self.resetTreeWidget()
		self.loadFilesButton.setEnabled(False)

		# why is all this required for threading damnit
		self.backgroundThread = QThread()
		self.backgroundWorker = BackgroundWorker("load", self.extract, {"base": self.folders["input"], "input": files, "map": _map, "diff": self.folders["diff"]})
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

	def searchFiles(self, data, substring, current_path="", flatten=False):
		result = {"folders": {}, "files": []}

		result["files"] = [file for file in data.get("files", []) if substring in file[0]]

		for folder_name, folder_data in data.get("folders", {}).items():
			subfolder_result = self.searchFiles(folder_data, substring)
			if subfolder_result["files"] or subfolder_result["folders"]:
				result["folders"][folder_name] = subfolder_result

		if flatten:
			while result["files"] == []:
				if len(result["folders"]) == 0:
					break
				result = list(result["folders"].values())[0]

		return result

	def resetTreeWidget(self):
		self.treeWidget.clear()
		self.fileStructure = {"folders": {}, "files": []}
		self.audioInfoLabel.setText("Click on an audio file to get more infos !")
		self.setExtractionState(False)

	def updateTreeWidget(self, structure):
		self.treeWidget.clear()
		self.treeWidget.setColumnCount(4)
		self.treeWidget.setHeaderLabels(["Name", "Duration", "Compressed Size", "Source", "Offset"])
		
		self.addItems(None, structure)

		self.treeWidget.expandAll()

		self.treeWidget.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
		self.treeWidget.header().setSectionResizeMode(1, QHeaderView.Stretch)
		self.treeWidget.header().setSectionResizeMode(2, QHeaderView.Stretch)
		self.treeWidget.header().setSectionResizeMode(3, QHeaderView.Stretch)

		self.treeWidget.setHeaderHidden(False)

		self.treeWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
		self.treeWidget.setDragDropMode(QAbstractItemView.NoDragDrop)
		self.treeWidget.itemClicked.connect(self.updateAudioPreview)

	def computeFolderSize(self, folder):
		total_size = 0
		
		for file in folder.get("files", []):
			total_size += file[1]["size"]

		for subfolder_name, subfolder in folder.get("folders", {}).items():
			subfolder_size = self.computeFolderSize(subfolder)
			total_size += subfolder_size

		return total_size

	def updateAudioPreview(self, item, column):
		file_data = self.searchFiles(self.fileStructure, item.text(0), flatten=True)

		if file_data == {"folders": {}, "files": []}:
			self.audioInfoLabel.setText("Click on an audio file to get more infos !")
			return

		meta = file_data["files"][0][1]["metadata"]

		# show meta
		text = f'Infos for {item.text(0)} => Channels : {meta["channels"]} | Sample rate : {meta["sampleRate"]} Hz | Bitrate : {meta["avgBitrate"]} kbps | Codec : {meta["codecDisplay"]} | Layout type : {meta["layoutType"]}'
		self.audioInfoLabel.setText(text)

	def addItems(self, parent, element):
		for folder_name in sorted(element.get("folders", {}).keys()):
			folder_content = element["folders"][folder_name]
			folder_item = QTreeWidgetItem([folder_name, "", self.displaySize(self.computeFolderSize(folder_content)), "", ""])
			folder_item.setFlags(folder_item.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
			folder_item.setCheckState(0, Qt.Unchecked)
			if parent is None:
				self.treeWidget.addTopLevelItem(folder_item)
			else:
				parent.addChild(folder_item)
			self.addItems(folder_item, folder_content)

		for file in sorted(element.get("files", []), key=lambda x: x[0]):
			file_meta = file[1]
			file_item = QTreeWidgetItem([file[0], f'{round(file_meta["metadata"]["duration"], 1)} seconds', self.displaySize(file_meta["size"]), file_meta["source"], str(hex(file_meta["offset"]))])
			file_item.setFlags(file_item.flags() | Qt.ItemIsUserCheckable)
			file_item.setCheckState(0, Qt.Unchecked)
			if parent is None:
				self.treeWidget.addTopLevelItem(file_item)
			else:
				parent.addChild(file_item)

	# page 3 - extraction
	def extractItems(self, _all):
		self.setFolder(folder="output")

		checked_items = []
	
		def check_items(item, _all):
			if item.checkState(0) == Qt.Checked or _all:
				if item.text(1) != "":
					checked_items.append(self.getFileMeta(item))
			for i in range(item.childCount()):
				check_items(item.child(i), _all)
		
		for i in range(self.treeWidget.topLevelItemCount()):
			check_items(self.treeWidget.topLevelItem(i), _all)

		self.setExtractionState(False)

		# yet another block of threading bs
		self.backgroundThread = QThread()
		self.backgroundWorker = BackgroundWorker("extract", self.extract, {"input": self.currentInput, "files": checked_items, "format": self.format, "output": self.folders["output"]})
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

		meta = self.searchFiles(self.fileStructure, item.text(0), flatten=True)["files"][0]
		name = meta[0]
		meta = meta[1] # move inside

		return {
			"name": item.text(0),
			"path": path[:-1],
			"source": meta["source"],
			"offset": meta["offset"],
			"size": meta["size"]
		}

	# misc
	def resetApp(self):
		self.resetTreeWidget()
		self.extract.reset()
		self.currentInput = None
		self.setExtractionState(False)
		self.tabs.setCurrentIndex(0)
		self.totalProgress.setValue(0)
		self.fileProgress.setValue(0)
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
