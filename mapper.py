# reader for the .map format i've made to improve reading speed and mapping size
from filereader import FileReader


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
		val = lambda length: vl2(reader.ReadBytes(length))
		vl2 = lambda data: int.from_bytes(data, "little")
		raw = lambda length: rw2(reader.ReadBytes(length))
		rw2 = lambda data: data.rstrip(b"\x00").decode("utf-8")
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

		header_size = val(1) # header size
		block_size = 4
		header_blocks = [reader.ReadBytes(block_size) for _ in range(header_size // block_size)]

		infos = {
			"game": games[rw2(header_blocks[0])],
			"version": list(rw2(header_blocks[1])),
			"coverage": int(rw2(header_blocks[2])),
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

		self.langs_offsets = langs_offsets

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
			if prefix != b"\x00":
				prefix = prefixes[prefix]
			else:
				prefix = ""
			name = raw(name_length)
			
			name = f"{prefix}{name}"
			path.append(name)
			path = "\\".join(path)

			files_offsets[offset] = path

		self.files_offsets = files_offsets

		# read keys
		# GI 3649050
		keys_data = {}
		n_keys = val(3)

		left = reader.GetRemainingLength()
		data = bytearray(reader.ReadBytes(left))
		keys_data = {rw2(data[i:i+16]): bytes(data[i+16:i+21]) for i in range(0, len(data), 21)}

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
		data = [self.files_offsets[int.from_bytes(key_data[2:], "little")]]

		if lang:
			data.append(self.langs_offsets[int.from_bytes(key_data[:1], "little")])

		return data

	def reset(self):
		self.reader = None
		self.langs_offsets.clear()
		self.files_offsets.clear()
		self.keys_data.clear()
