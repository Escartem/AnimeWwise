# reader for the .map format i've made to improve reading speed and mapping size
from filereader import FileReader
import os


langs_offsets = {}
keys_data = {}
reader = None


def load_mapping(mapping_file, langs=False):
	global reader

	file = open(mapping_file, "rb")
	reader = FileReader(file, "little") # encoded as little

	# check file
	if reader.ReadBytes(4) != b"ESFM":
		file.close()
		raise Exception("mapping was invalid")

	reader.ReadBytes(2)

	if reader.ReadBytes(2) != b"\x56\x31":
		file.close()
		raise Exception("invalid mapping version")

	reader.ReadBytes(2)

	# read languages
	n_langs = reader.ReadInt8()
	for i in range(n_langs):
		offset = reader.GetBufferPos()
		lang_length = reader.ReadInt8()
		langs_offsets[str(offset)] = reader.ReadBytes(lang_length).decode("utf-8")

	# read keys
	n_keys = reader.ReadInt32()
	for i in range(n_keys):
		key_length = reader.ReadInt8()
		key = reader.ReadBytes(key_length).decode("utf-8")
		lang_offset = reader.ReadInt8()
		data_offset = reader.ReadInt32()
		linked_lang = langs_offsets[str(lang_offset)]
		keys_data[str(key)] = [linked_lang, data_offset]

	if langs:
		return list(langs_offsets.values())
	return True


def get_key(key, lang=False):
	if key not in keys_data.keys():
		return None

	# search data
	data = keys_data[key]
	lang = data[0]

	reader.SetBufferPos(data[1])
	data_length = reader.ReadInt8()
	data = [reader.ReadBytes(data_length).decode("utf-8")]

	if lang:
		data.append(lang)

	return data
