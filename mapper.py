# reader for the .map format i've made to improve reading speed and mapping size
from filereader import FileReader
import os
import json


class Mapper:
	def __init__(self, mapping_file):
		file = open(mapping_file, "rb")
		reader = FileReader(file, "little") # encoded as little

		# check file
		if reader.ReadBytes(4) != b"ESFM":
			file.close()
			raise Exception("mapping was invalid")

		reader.ReadBytes(2)

		map_version = reader.ReadBytes(2)
		if map_version == b"\x56\x31":
			print(f"Warning: you are using an old version of the mapping that is no longer supported, please use a newer one or download an older version of this tool.")
			raise Exception("outdated mapping")
		elif map_version  == b"\x56\x32":
			self.reader = reader
			self.process_map()
		else:
			file.close()
			raise Exception("invalid mapping version")

	def process_map(self):
		reader = self.reader

		# utils
		val = lambda length: int.from_bytes(reader.ReadBytes(length), "little")
		raw = lambda length: reader.ReadBytes(length).rstrip(b"\x00").decode("utf-8")
		n2p = lambda val: [e[0] for e in enumerate(list(bin(val)[2:][::-1])) if e[1] == "1"]

		# get map meta
		reader.ReadBytes(2)

		games = {
			"ys": "Genshin",
			"sr": "Star Rail",
			"zzz": "Zenless Zone Zero"
			# more later
		}

		coverages = [
			"english voicelines",
			"chinese voicelines",
			"japanese voicelines",
			"korean voicelines",
			"music",
			"sfx"
		]

		reader.ReadBytes(1) # header size
		infos = {
			"game": games[raw(4)],
			"version": list(raw(4)),
			"coverage": int(raw(4))
			# more later
		}

		print(f"> Loading mapping for {infos['game']} v{infos['version'][0]}.{infos['version'][1]}, this may take a few seconds...")

		# read prefixes
		prefixes = {}
		n_prefixes = reader.ReadUInt8()
		l_prefixes = reader.ReadUInt8()

		for i in range(n_prefixes):
			prefix = raw(l_prefixes)
			marker = reader.ReadBytes(1)
			prefixes[marker] = prefix

		# read languages
		langs_offsets = {}
		n_langs = reader.ReadUInt8()
		l_langs = reader.ReadUInt8()
		
		for i in range(n_langs):
			offset = reader.GetBufferPos()
			langs_offsets[offset] = raw(l_langs)

		# read folders
		folder_offsets = {}
		n_folders = reader.ReadUInt8()

		for i in range(n_folders):
			offset = reader.GetBufferPos()
			length = reader.ReadUInt8()
			prefix = reader.ReadBytes(1)
			folder = raw(length)
			folder = f"{prefixes[prefix]}{folder}"
			folder_offsets[offset] = folder

		# read files
		files_offsets = {}
		n_files = val(3)

		for i in range(n_files):
			offset = reader.GetBufferPos()
			path_length = reader.ReadUInt8()
			path = []
			for i in range(path_length):
				path.append(folder_offsets[reader.ReadUInt16()])
			
			name_length = reader.ReadUInt8()
			prefix = reader.ReadBytes(1)
			prefix = prefixes[prefix]
			name = raw(name_length)
			
			name = f"{prefix}{name}"
			path.append(name)
			path = "\\".join(path)

			files_offsets[offset] = path

		# read keys
		keys_data = {}
		n_keys = val(3)

		for i in range(n_keys):
			key = raw(16)
			
			lang_offset = val(2)
			file_offset = val(3)

			keys_data[key] = [files_offsets[file_offset], langs_offsets[lang_offset]]

		self.keys_data = keys_data

		# done
		print(f"> Finished loading mapping")
		print(f": {n_langs} supported languages")
		print(f": {n_files} mapped files")
		print(f": {n_keys} available keys")
		print(f"")
		print(f"> Mapping coverage")
		coverage = n2p(infos["coverage"])
		for val in coverage:
			if val%2 == 0:
				print(f": partial {coverages[val//2-1]}")
			else:
				print(f": {coverages[(val-1)//2]}")

	def get_key(self, key, lang=False):
		keys_data = self.keys_data
		if key not in keys_data.keys():
			return None

		key_data = keys_data[key]
		data = [key_data[0]]

		if lang:
			data.append(key_data[1])

		return data
