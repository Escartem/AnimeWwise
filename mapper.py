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
		if map_version != b"\x32\x31":
			print(f"Warning: you are using an unknown / unsupported version of the mapping that is no longer supported, please use a newer one or download an older version of this tool.")
			raise Exception("incompatible mapping")

		self.reader = reader
		self.process_map()

	def process_map(self):
		reader = self.reader

		# utils
		val = lambda length: vl2(reader.ReadBytes(length))
		vl2 = lambda data: int.from_bytes(data, "little")
		raw = lambda length: rw2(reader.ReadBytes(length))
		rw2 = lambda data: data.rstrip(b"\x00").decode("utf-8")

		# get map meta
		reader.ReadBytes(2)

		games = {
			"hk4e": "Genshin",
			"hkrpg": "Star Rail",
			"nap": "Zenless Zone Zero"
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

		# read sectors
		sectors_signature = reader.ReadBytes(9)
		if sectors_signature != b"\xFF\x53\x45\x43\x54\x4F\x52\x53\xFF": # ff sectors ff
			raise Exception("invalid mapping sectors signature")

		n_sectors = val(1)
		sectors = {}

		for i in range(n_sectors):
			name_length = val(1)
			name = raw(name_length)
			offset = val(4)
			size = val(4)

			sectors[name] = {
				"offset": offset,
				"size": size
			}

		# read config
		reader.SetBufferPos(sectors["HEADER"]["offset"])

		header_sig = reader.ReadBytes(8) # hardcoded but lazy, this value is for this sector only

		n_configs = val(1)
		config = {}
		for i in range(n_configs):
			name = raw(4)
			value = raw(5)
			config[name] = value

		infos = {
			"game": games[config["game"]],
			"version": config["verS"],
			# "coverage": config["covR"],
			"useBanksSector": config["bnkS"],
			# "bankSectorCoverage": config["bCov"]
		}

		print(f"> Loading mapping for {infos['game']} v{infos['version']}, this may take a few seconds...")

		# read prefixes
		prefixes = {}
		n_prefixes = reader.ReadUInt8()
		l_prefixes = reader.ReadUInt8()

		for i in range(n_prefixes):
			prefix = raw(l_prefixes)
			marker = reader.ReadBytes(1)
			prefixes[marker] = prefix

		# sector jump here
		reader.SetBufferPos(sectors["ITEMS"]["offset"])

		items_sec_sig = reader.ReadBytes(7) # hardcoded too

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
		# GI 3649050 (outdated value, use items sector size instead)
		keys_data = {}
		n_keys = val(3)

		left = reader.GetRemainingLength()
		if infos["useBanksSector"] == "TRUE":
			left -= sectors["BANKS"]["size"]

		data = bytearray(reader.ReadBytes(left))
		keys_data = {rw2(data[i:i+16]): bytes(data[i+16:i+21]) for i in range(0, len(data), 21)}

		self.keys_data = keys_data

		# read banks sector
		if infos["useBanksSector"] == "TRUE":
			reader.SetBufferPos(sectors["BANKS"]["offset"])

			banks_sec_sig = reader.ReadBytes(7) # hardcoded

			global_path_size = val(1)
			global_path = raw(global_path_size)

			n_bank_keys = val(2)
			bank_keys = {}

			for i in range(n_bank_keys):
				key_length = val(1)
				key = raw(key_length)
				value_length = val(1)
				value = raw(value_length)

				bank_keys[key] = f"{global_path}\\{value}"

			self.bank_keys = bank_keys

		# done
		print(f"> Finished loading mapping")
		print(f"=-=-= Voicelines sector =-=-=")
		print(f": {n_langs} languages")
		print(f": {n_files} mapped files")
		print(f": {n_keys} keys")
		if infos["useBanksSector"] == "TRUE":
			print(f"=-=-= Music sector =-=-=")
			print(f": {n_bank_keys} keys")

	def get_key(self, key, lang=False):
		keys_data = self.keys_data
		banks_data = self.bank_keys

		if key in keys_data.keys():
			key_data = keys_data[key]
			data = [self.files_offsets[int.from_bytes(key_data[2:], "little")]]

			if lang:
				data.append(self.langs_offsets[int.from_bytes(key_data[:1], "little")])

			return data

		if key in banks_data.keys():
			return [banks_data[str(key)], ""]

		return None

	def reset(self):
		self.reader = None
		self.langs_offsets.clear()
		self.files_offsets.clear()
		self.keys_data.clear()
