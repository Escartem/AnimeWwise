import os
import io
import sys
import time
from mapper import Mapper
import shutil
import filecmp
import tempfile
import wavescan
import subprocess
from filereader import FileReader
from allocator import Allocator

cwd = os.getcwd()
path = lambda path: os.path.join(cwd, path)
call = lambda args: subprocess.call(args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

skips = "000000000" # used for debugging

# 1 - original extract
# 2 - patch
# 3 - patch extract
# 4 - filter files
# 5 - wem to wav
# 6 - wav to mp3
# 7 - map names
# 8 - clean up
# 9 - temp clean up

class WwiseExtract:
	def __init__(self):

		self.paths = {
			"input": "",
			"output": "",
			"diff": "",
			"temp": tempfile.TemporaryDirectory()
		}

		self.allocator = Allocator()

	def path(self, base, path):
		base_path = self.paths[base]
		if base == "temp":
			base_path = base_path.name
		return os.path.join(base_path, path)

	def extract2(self):
		audio_format = self.format
		mapper = self.map
		_p = self.path # lazy

		print(f'Format: {audio_format}')

		# TODO: ui popup
		# if os.path.exists("output") and len(os.listdir("output")) > 0:
		# 	print("The output folder needs to be cleared, continue ? [Y/N]")
		# 	select = input(">")
		# 	if select.lower() == "y":
		# 		shutil.rmtree("output")
		# 	else:
		# 		print("Aborting")
		# 		exit()

		# Get all files to process
		hdiff_files = [f for f in os.listdir(self.paths["input"]) if f.endswith(".pck") and os.path.exists(_p("diff", f"{f}.hdiff"))]
		alone_files = [f for f in os.listdir(self.paths["input"]) if f.endswith(".pck") and not os.path.exists(_p("diff", f"{f}.hdiff"))]
		files = [*hdiff_files, *alone_files]

		if len(files) == 0:
			print("No files found !")
			# self.progress(100)
			return

		print(self.paths["temp"].name)

		print(f"{len(files)} file{'s' if len(files) != 1 else ''} to extract")
		iteration = 0

		for file in files:
			try:
				iteration += 1
				filename = file
				if file in hdiff_files:
					filename = f"{file.split('.')[0]}.hdiff.pck"
				print(f"--- {filename} ({iteration}/{len(files)}) ---")

				alone = False #8 steps
				if file in alone_files:
					alone = True # 5 steps

				######################################
				### 1 - Extract original .pck file ###
				######################################

				if skips[0] != "1":
					shutil.copy(_p("input", file), _p("temp", file))

					output_path = "original_decoded"
					if alone:
						output_path = "wem"

					print(f"Extracting")
					wavescan.extract(_p("temp", file), _p("temp", output_path))
					self.progress(["total", 15])

					if alone:
						all_files = os.listdir(_p("temp", "wem"))

				######################################
				### 2 - Patch the .pck with .hdiff ###
				######################################

				if skips[1] != "1":
					if not alone:
						print(f"Patching")

						# update files
						shutil.copy(_p("diff", f"{file}.hdiff"), _p("temp", f"{file}.hdiff"))
						shutil.move(_p("temp", file), _p("temp", f"{file.split('.')[0]}.original.pck"))

						# prepare args
						args = [
							path("tools/hpatchz/hpatchz.exe"),
							"-f",
							_p("temp", f"{file.split('.')[0]}.original.pck"),
							_p("temp", f"{file}.hdiff"),
							_p("temp", file)
						]

						call(args)
						self.progress(["total", 20])

				#####################################
				### 3 - Extract patched .pck file ###
				#####################################

				if skips[2] != "1":
					if not alone:
						print(f"Extracting patch")
						wavescan.extract(path(f"temp/{file}"), path(f"temp/patched_decoded"))
						self.progress(["total", 30])

						# cleanup useless files to save storage
						os.remove(_p("temp", file))
						os.remove(_p("temp", f"{file}.hdiff"))
						os.remove(_p("temp", f"{file.split('.')[0]}.original.pck"))

				####################################
				### 4 - Search new/changed files ###
				####################################

				if skips[3] != "1":
					if not alone:
						print(f"Filtering files")
						# compare folders
						diff = filecmp.dircmp(_p("temp", "original_decoded"), _p("temp", "patched_decoded"))
						new_files, changed_files = diff.right_only, diff.diff_files
						all_files = [*new_files, *changed_files]

						# merge files
						os.makedirs(_p("temp", "wem"), exist_ok=True)

						for file in all_files:
							shutil.move(_p("temp", f"patched_decoded/{file}"), _p("temp", f"wem/{file}"))

						# cleanup useless folders to save storage
						shutil.rmtree(_p("temp", "original_decoded"))
						shutil.rmtree(_p("temp", "patched_decoded"))
						self.progress(["total", 35])

				######################################
				### 5 - Convert .wem files to .wav ###
				######################################

				if skips[4] != "1":

					# updates folders
					os.makedirs(_p("temp", "wav"), exist_ok=True)
					print(f"Converting to wav")
					pos = 0
					# convert each file one by one
					for file in all_files:
						pos += 1
						args = [
							path("tools/vgmstream/vgmstream-cli.exe"),
							"-o",
							_p("temp", f"wav/{file.split('.')[0]}.wav"),
							_p("temp", f"wem/{file}")
						]

						call(args)
						self.progress(["total", round(35 + (pos * 30) / len(all_files))])
						self.progress(["task", round((pos * 100) / len(all_files))])

					# cleanup
					shutil.rmtree(_p("temp", "wem"))
					wem_length = len(all_files)
					all_files = [f for f in os.listdir(_p("temp", "wav"))]
					diff_length = wem_length - len(all_files)

					if diff_length > 0:
						print(f": Failed to extract {diff_length} files out of {wem_length} (probably no extractable content)")

				#############################################
				### 6 - Convert .wav files to .mp3 or ogg ###
				#############################################

				if skips[5] != "1":
					# updates folders and progress bar
					os.makedirs(_p("temp", audio_format), exist_ok=True)
					print(f"Converting to {audio_format}")

					# update file list
					all_files = [f"{f.split('.')[0]}.wav" for f in all_files]
					pos = 0
					# convert each file one by one
					for file in all_files:
						pos += 1
						args = [
							path("tools/ffmpeg/ffmpeg.exe"),
							"-i",
							_p("temp", f"wav/{file}"),
							"-acodec",
							"libvorbis" if audio_format == "ogg" else "libmp3lame",
							"-b:a",
							"192k", # 192k | 4k
							_p("temp", f"{audio_format}/{file.split('.')[0]}.{audio_format}"),
						]

						call(args)
						self.progress(["total", (round(65 + (pos * 30) / len(all_files)))])
						self.progress(["task", round((pos * 100) / len(all_files))])

					# cleanup
					shutil.rmtree(_p("temp", "wav"))

					# update files list
					all_files = [f"{f.split('.')[0]}.{audio_format}" for f in all_files]

					if not alone:
						new_files = [f"{f.split('.')[0]}.{audio_format}" for f in new_files]
						changed_files = [f"{f.split('.')[0]}.{audio_format}" for f in changed_files]

				#########################
				### 7 - Map filenames ###
				#########################

				if skips[6] != "1" or mapper != None:
					print(f"Mapping names")

					# TODO: remove unmapped folder if empty
					os.makedirs(_p("temp", "map/unmapped"), exist_ok=True)
					if not alone:
						os.makedirs(_p("temp", f"map/new_files/unmapped"), exist_ok=True)
						os.makedirs(_p("temp", f"map/changed_files/unmapped"), exist_ok=True)

					lang = None

					for file in all_files:
						file_name = file.split(".")[0]
						base_path = "map"
						if not alone:
							if file in new_files:
								base_path = "map/new_files"
							elif file in changed_files:
								base_path = "map/changed_files"

						key_data = mapper.get_key(file_name, lang is None)

						if key_data is not None:
							if lang is None:
								lang = key_data[1]
								# TODO: use language for output path
								print(f"\n: {lang} detected")

							dir_path = _p("temp", f"{base_path}/{key_data[0]}.{audio_format}")
							os.makedirs(os.path.dirname(dir_path), exist_ok=True)
							shutil.copy(_p("temp", f"{audio_format}/{file}"), dir_path)
						else:
							shutil.copy(_p("temp", f"{audio_format}/{file}"), _p("temp", f"{base_path}/unmapped/{file}"))

				######################################################
				### 8 - Clean everything and move result to output ###
				######################################################

				if skips[7] != "1":
					print(f"Cleaning up")

					filename = filename.split('.')[0]

					shutil.move(_p("temp", "map"), _p("output", filename))

					self.paths["temp"].cleanup()

					self.progress["total", 100]

			except Exception as e:
				print("")
				print("An error occured while processing this file ! Skipping... details of the error bellow :")
				print(f"Line {sys.exc_info()[-1].tb_lineno}, {e}")

		print("-"*30)
		print("Done extracting everything !")

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

		# wem
		if _format == "wem":
			output_folder = output
		else:
			output_folder = os.path.join(temp_dir.name, "wem")

		self.extract_wem(_input, files, output_folder, progress)

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

		self.extract_wav(new_input, files, output_folder, progress)

		if _format == "wav":
			temp_dir.cleanup()
			return

		new_input = output_folder
		# TODO: add mp3 and ogg

	def extract_wem(self, _input, files, output, progress):
		print(": Extracting audio as wem")
		all_sources = list(set([e["source"] for e in files]))

		for source in all_sources:
			self.allocator.load_file(os.path.join(_input, source))

		pos = 0
		for file in files:
			pos += 1
			progress(["file", pos * 100 // len(files)])

			data = self.allocator.read_at(file["source"], file["offset"], file["size"])
			
			filepath = os.path.join("/".join(file["path"]), file["name"])
			fullpath = os.path.join(output, filepath)
			os.makedirs(os.path.dirname(fullpath), exist_ok=True)
			
			with open(fullpath, "wb") as f:
				f.write(data)
				f.close()

		self.allocator.free_mem()

	def extract_wav(self, _input, files, output, progress):
		print(": Converting audio to wav")
		pos = 0
		for file in files:
			pos += 1
			progress(["file", pos * 100 // len(files)])

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
		
	### other ###

	def reset(self):
		if self.mapper is not None:
			self.mapper.reset()
		self.allocator.free_mem()
