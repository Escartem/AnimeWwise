import os
import io
import sys
import time
import shutil
import filecmp
import tempfile
import wavescan
import subprocess
from mapper import Mapper
from allocator import Allocator
from filereader import FileReader

cwd = os.getcwd()
path = lambda path: os.path.join(cwd, path)
call = lambda args: subprocess.call(args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

# TODO: handle hdiff, helper :
# hpathz.exe -f original.pck patch.hdiff output.pck
# diff = filecmp.dircmp(original, patched)
# new_files, changed_files = diff.right_only, diff.diff_files

class WwiseExtract:
	def __init__(self):
		self.allocator = Allocator()

	### loading files ###

	def load_folder(self, _map, path):
		self.mapper = None
		if _map is not None:
			self.mapper = Mapper(os.path.join(os.getcwd(), f"maps/{_map}"))
		self.file_structure = {"folders": {}, "files": []}

		files = [f for f in os.listdir(path) if f.endswith(".pck")]

		if len(files) == 0:
			return None

		for file in files:
			self.load_file(os.path.join(path, file))

		return self.file_structure

	def load_file(self, _input):
		with open(_input, "rb") as f:
			data = f.read()
			f.close()
		self.get_wems(data, os.path.basename(_input))

	def get_wems(self, data, filename):
		reader = FileReader(io.BytesIO(data), "little")
		files = wavescan.get_data(reader)
		self.map_names(files, filename)
	
	def map_names(self, files, filename):
		mapper = self.mapper
		base = self.file_structure

		for file in files:
			if mapper is not None:
				key = mapper.get_key(file[0].split(".")[0])
			else:
				key = None
			if key is not None:
				self.add_to_structure(f"{filename}\\{key[0]}.wem".split("\\"), [file[1], file[2]])
			else:
				temp = base["folders"]
				if filename not in temp:
					temp[filename] = {"folders": {}, "files": []}
				temp = temp[filename]["folders"]
				if "unmapped" not in temp:
					temp["unmapped"] = {"folders": {}, "files": []}
				temp["unmapped"]["files"].append(file)

		self.file_structure = base

	def add_to_structure(self, parts, meta):
		current_level = self.file_structure
		for part in parts[:-1]:
			if "folders" not in current_level:
				current_level["folders"] = {}
			if part not in current_level["folders"]:
				current_level["folders"][part] = {"folders": {}, "files": []}
			current_level = current_level["folders"][part]
		if "files" not in current_level:
			current_level["files"] = []
		current_level["files"].append([parts[-1], meta[0], meta[1]])

	### extracting files ###

	def extract_files(self, _input, files, output, _format, progress):
		temp_dir = tempfile.TemporaryDirectory()
		self.progress = progress
		self.steps = {
			"wem": 1,
			"wav": 2,
			"mp3": 3,
			"ogg": 3
		}[_format]

		# wem
		if _format == "wem":
			output_folder = output
		else:
			output_folder = os.path.join(temp_dir.name, "wem")

		self.extract_wem(_input, files, output_folder)

		if _format == "wem":
			temp_dir.cleanup()
			return

		# wav
		new_input = output_folder
		files = [os.path.join("/".join(file["path"]), file["name"]) for file in files]

		if _format == "wav":
			output_folder = output
		else:
			output_folder = os.path.join(temp_dir.name, "wav")

		self.extract_wav(new_input, files, output_folder)

		if _format == "wav":
			temp_dir.cleanup()
			return

		# mp3 & ogg
		files = [os.path.join(os.path.dirname(file), f'{os.path.basename(file).split(".")[0]}.wav') for file in files]
		new_input = output_folder
		output_folder = output

		self.extract_ffmpeg(new_input, files, output_folder, _format)

		temp_dir.cleanup()
		return

	def extract_wem(self, _input, files, output):
		print(": Extracting audio as wem")
		all_sources = list(set([e["source"] for e in files]))

		for source in all_sources:
			self.allocator.load_file(os.path.join(_input, source))

		pos = 0
		for file in files:
			pos += 1
			self.update_progress(pos, len(files), 1)

			data = self.allocator.read_at(file["source"], file["offset"], file["size"])
			
			filepath = os.path.join("/".join(file["path"]), file["name"])
			fullpath = os.path.join(output, filepath)
			os.makedirs(os.path.dirname(fullpath), exist_ok=True)
			
			with open(fullpath, "wb") as f:
				f.write(data)
				f.close()

		self.allocator.free_mem()

	def extract_wav(self, _input, files, output):
		print(": Converting audio to wav")
		pos = 0
		for file in files:
			pos += 1
			self.update_progress(pos, len(files), 2)

			filename = f'{os.path.basename(file).split(".")[0]}.wav'
			filepath = os.path.join(output, os.path.dirname(file), filename)
			os.makedirs(os.path.dirname(filepath), exist_ok=True)

			args = [
				path("tools/vgmstream/vgmstream-cli.exe"),
				"-o",
				filepath,
				os.path.join(_input, file)
			]

			call(args)

	def extract_ffmpeg(self, _input, files, output, _format):
		print(f": Converting audio to {_format}")

		encoders = {
			"mp3": "libmp3lame",
			"ogg": "libvorbis"
		}
		
		encoder = encoders[_format]

		pos = 0
		for file in files:
			pos += 1
			self.update_progress(pos, len(files), 3)

			filename = f'{os.path.basename(file).split(".")[0]}.{_format}'
			filepath = os.path.join(output, os.path.dirname(file), filename)
			os.makedirs(os.path.dirname(filepath), exist_ok=True)

			args = [
				path("tools/ffmpeg/ffmpeg.exe"),
				"-i",
				os.path.join(_input, file),
				"-acodec",
				encoder,
				"-b:a",
				"192k", # 192|4
				filepath
			]

			call(args)
		
	### other ###

	def update_progress(self, current, total, step):
		base = 100 / self.steps
		self.progress(["total", current * base // total + base * (step - 1)])
		self.progress(["file", current * 100 // total])

	def reset(self):
		if self.mapper is not None:
			self.mapper.reset()
		self.allocator.free_mem()
