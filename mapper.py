# reader for the .map format i've made to improve reading speed and mapping size
import io
import json
from filereader import FileReader


class Mapper:
	def __init__(self, mapping_file):
		file = open(mapping_file, "rb")
		self.data = file.read()
		file.close()

		reader = FileReader(io.BytesIO(self.data), "little")

		# check file
		if reader.ReadBytes(4) != b"ESFM":
			raise Exception("mapping was invalid")

		reader.ReadBytes(2)

		map_version = reader.ReadBytes(2)
		if map_version != b"\x33\x30":
			print(f"Warning: you are using an unknown / unsupported version of the mapping that is no longer supported, please use a newer one or download an older version of this tool.")
			raise Exception("incompatible mapping")

		reader.ReadBytes(2)

		self.process_map(reader)

	def process_map(self, reader):
		games = {
			"hk4e": "Genshin",
			"hkrpg": "Star Rail",
			"nap": "Zenless Zone Zero"
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
		int24 = lambda: int.from_bytes(reader.ReadBytes(3), "big")

		sectors = {
			# offset | size
			"languages": [int24(), int24()],
			"strings": [int24(), int24()],
			"words": [int24(), int24()],
			"files": [int24(), int24()],
			"keys": [int24(), int24()],
			"music": [int24(), int24()]
		}

		# languages
		reader.SetBufferPos(sectors["languages"][0])
		self.languages = []

		n_langs = reader.ReadInt8()
		for i in range(n_langs):
			size = reader.ReadInt8()
			name = reader.ReadBytes(size).decode("utf-8")
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
		self.keys = {keys_data[i+3:i+key_size].hex(): int.from_bytes(keys_data[i:i+3], "big") for i in range(0, len(keys_data), key_size)}

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
				name = reader.ReadBytes(name_size).decode("utf-8")
				self.music_keys[str(key)] = f"{root}\\{name}"

		# done
		print(f"> Finished loading mapping")
		print(f"=-=-= Voicelines sector =-=-=")
		print(f": {n_langs} languages")
		print(f": {n_files} mapped files")
		print(f": {n_keys} keys")
		if hasMusic:
			print(f": {n_music} musics")

	def get_key(self, key, lang=False):
		if (not key in self.keys) and (not key in self.music_keys):
			return None

		if key in self.music_keys:
			return [self.music_keys[key], ""]

		lang, offset = (self.keys[key] >> 22) & 0x03, self.keys[key] & 0x3FFFFF

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
					string = self.strings[string_offset+1:string_offset+1+string_size].decode("utf-8")
				word.append(string)

			word = "_".join(word)
			name.append(word)

		name = ["\\".join(name)]
		
		if lang:
			name.append(self.languages[lang])

		return name

	def reset(self):
		self.reader = None
		self.languages.clear()
		self.strings.clear()
		self.words.clear()
		self.files.clear()
		self.music_keys.clear()
