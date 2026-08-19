# reader for the .map format i've made to improve reading speed and mapping size
import io
import json
from filereader import FileReader


class Mapper:
	def __init__(self, mapping_file):
		self.mode = None
		self.keys = {}
		self.languages = []
		self.strings = bytearray()
		self.words = bytearray()
		self.files = bytearray()
		self.music_keys = {}

		### NORMAL MAP LOADING ###

		self.load_data(mapping_file)
		self.load_map("MAP")

		# you can use the following to load your own mapping instead of the official one
		# for both cases, comment the 2 lines in the normal mode and uncomment the 2 in your mode
		# and for both make sure of the following
		#
		# key -> the hashed path
		# value -> without the .wem extension, by default the language is also removed and 
		# obtained back via addLang param but you can keep it in the path
		#
		# example : 3fe302b037275600 -> voice\\chapter4\\76\\player\\chapter4_76_player_118_f

		### JSON MAP LOADING ###

		# make sure the json is in the format {hash: path}
		# format the path to use *double backward slashes*
		#
		# example
		# {"3fe302b037275600": "voice\\chapter4\\76\\player\\chapter4_76_player_118_f"}

		# self.load_data("maps/yourmap.json")
		# self.load_map("JSON")

		### TSV MAP LOADING ###

		# make sure it is in the format "hash \t path"
		# format the path to use *single backward slashes*
		#
		# example
		# 3fe302b037275600	voice\chapter4\76\player\chapter4_76_player_118_f

		# self.load_data("maps/yourmap.tsv")
		# self.load_map("TSV")

	def load_map(self, mode):
		self.mode = mode
		
		if self.mode == "MAP":
			self.process_map()
		elif self.mode == "JSON":
			self.keys = json.loads(self.data)
		elif self.mode == "TSV":
			self.keys = {
				parts[0]:parts[1]
				for e in self.data.decode("utf-8").splitlines()
				if (parts := e.split("\t")) and len(parts) >= 2}

	def load_data(self, file):
		file = open(file, "rb")
		self.data = file.read()
		file.close()

	def process_map(self):
		reader = FileReader(io.BytesIO(self.data), "little")

		# check file
		if reader.ReadBytes(4) != b"ESFM":
			raise Exception("mapping was invalid")

		reader.ReadBytes(2)

		self.map_version = reader.ReadBytes(2)
		if self.map_version not in [b"\x33\x31", b"\x33\x32"]:
			print(f"Error: you are using an unknown / unsupported version of the mapping that is no longer supported, please use a newer one or download an older version of this tool.")
			raise Exception("incompatible mapping")

		reader.ReadBytes(2)

		games = {
			"hk4e": "Genshin",
			"hkrpg": "Star Rail",
			"nap": "Zenless Zone Zero",
			"beyond": "Arknights Endfield"
			# more later
		}

		# read config
		game_size = reader.ReadInt8()
		game = reader.ReadBytes(game_size).decode("utf-8")

		infos = {
			"game": games[game],
			"version": ".".join(list(str(reader.ReadInt8())))
		}

		print(f"> Loading mapping for {infos['game']} v{infos['version']}, this may take a few seconds...")

		# sectors
		def int24():
			val = reader.ReadBytes(3)
			if val == b"\xFF" * 3:
				val = reader.ReadBytes(4)
			return int.from_bytes(val, "big")

		names = ["languages", "strings", "words", "files", "keys", "music"]
		sectors = {n: [int24(), int24()] for n in names}
		if list(sectors.values())[0][0] == 0:
			offset = reader.GetBufferPos()
			for v in sectors.values():
				v[0] += offset

		# languages
		reader.SetBufferPos(sectors["languages"][0])
		self.languages = []

		n_langs = reader.ReadInt8()
		for i in range(n_langs):
			size = reader.ReadInt8()
			name = bytes([b ^ (0x97 + size) for b in reader.ReadBytes(size)]).decode("utf-8")
			self.languages.append(name)

		# alloc sectors
		reader.SetBufferPos(sectors["strings"][0])
		self.strings = bytearray(reader.ReadBytes(sectors["strings"][1]))
		reader.SetBufferPos(sectors["words"][0])
		self.words = bytearray(reader.ReadBytes(sectors["words"][1]))
		reader.SetBufferPos(sectors["files"][0])
		self.files = bytearray(reader.ReadBytes(sectors["files"][1]))

		# read keys
		reader.SetBufferPos(sectors["keys"][0])
		key_size = reader.ReadInt8()
		n_keys = (sectors["keys"][1]-1) // key_size
		n_files = n_keys // n_langs

		keys_data = bytearray(reader.ReadBytes(sectors["keys"][1]-1))
		if self.map_version == b"\x33\x31":
			self.keys = {keys_data[i+3:i+key_size].hex(): int.from_bytes(keys_data[i:i+3], "big") for i in range(0, len(keys_data), key_size)}
		else:
			self.keys = {keys_data[i+4:i+key_size].hex(): (int.from_bytes(keys_data[i:i+3], "big"), keys_data[i+3]) for i in range(0, len(keys_data), key_size)}

		# music
		self.music_keys = {}
		hasMusic = sectors["music"][1] > 0

		if hasMusic:
			reader.SetBufferPos(sectors["music"][0])
			root_size = reader.ReadInt8()
			root = reader.ReadBytes(root_size).decode("utf-8")
			n_music = int.from_bytes(reader.ReadBytes(2), "big")

			for i in range(n_music):
				key = int.from_bytes(reader.ReadBytes(4), "big")
				name_size = reader.ReadInt8()
				name = bytes([b ^ (0x97 + name_size) for b in reader.ReadBytes(name_size)]).decode("utf-8")
				self.music_keys[str(key)] = f"{root}\\{name}"

		# done
		print(f"> Finished loading mapping")
		print(f"=-=-= Voicelines sector =-=-=")
		print(f": {n_langs} languages")
		print(f": {n_files} mapped files")
		print(f": {n_keys} keys")
		if hasMusic:
			print(f": {n_music} musics")

	def get_key(self, key, addLang=False):
		if self.mode == "MAP":
			if (not key in self.keys) and (not key in self.music_keys):
				return None

			if key in self.music_keys:
				return [self.music_keys[key], ""]

			if self.map_version == b"\x33\x31":
				lang, offset = (self.keys[key] >> 22) & 0x03, self.keys[key] & 0x3FFFFF
			else:
				offset, lang = self.keys[key]

			parts = int.from_bytes(self.files[offset:offset+1], "big")
			name = []

			for i in range(parts):
				word_offset = int.from_bytes(self.files[offset+1+(3*i):offset+4+(3*i)], "big")
				word_parts = int.from_bytes(self.words[word_offset:word_offset+1], "big")
				word = []

				for j in range(word_parts):
					string_offset = int.from_bytes(self.words[word_offset+1+(2*j):word_offset+3+(2*j)], "big")
					string_size = int.from_bytes(self.strings[string_offset:string_offset+1], "big")
					if string_size > 128:
						string = str(int.from_bytes(self.strings[string_offset+1:string_offset+1+(string_size-128)], "big"))
					else:
						string = bytes([b ^ (0x97 + string_size) for b in self.strings[string_offset+1:string_offset+1+string_size]]).decode("utf-8")
					word.append(string)

				word = "_".join(word)
				name.append(word)

			name = ["\\".join(name)]
			
			if addLang:
				name.append(self.languages[lang])

			return name
		elif self.mode in ["JSON", "TSV"]:
			if not key in self.keys:
				return None
			return [self.keys[key]]

	def reset(self):
		self.mode = None
		self.keys = {}
		self.languages = []
		self.strings = bytearray()
		self.words = bytearray()
		self.files = bytearray()
		self.music_keys = {}
