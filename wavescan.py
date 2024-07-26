# Custom rewrite of the Wwise AKPK packages extractor, original by Nicknine and bnnm
import os
import traceback
from bnk import bnk2wem


reader = None
bank_version = 0
wwise_data = []
filename = ""


def get_data(_reader, _filename):
	global wwise_data
	global bank_version
	global reader
	global filename

	filename = _filename
	wwise_data = []
	reader = _reader

	# check file
	if reader.ReadBytes(4) != b"AKPK":
		# file.close()
		raise Exception("not a valid audio file")

	# check endianness
	reader.SetBufferPos(0x08)
	endian_check = reader.ReadLong() # this is the same bytes as the flag sector, which seems to be always 1

	if endian_check == 1:
		endianness = 0 # little
	elif endian_check == 0x1000000:
		endianness = 1 # big
	else:
		raise Exception("couldn't detect endianness")

	# retrieve sectors in header
	reader.SetBufferPos(0x04)

	header_size = reader.ReadLong()
	flag = reader.ReadLong()

	languages_sector_size = reader.ReadLong()
	banks_sector_size = reader.ReadLong()
	sounds_sector_size = reader.ReadLong()
	externals_sector_size = 0

	if languages_sector_size + banks_sector_size + sounds_sector_size + 0x10 < header_size:
		externals_sector_size = reader.ReadLong()

	sectors = [[True, banks_sector_size, 0, 0, "bnk"], [False, sounds_sector_size, 1, 0, "wem"], [False, externals_sector_size, 1, 1, "wem"]]

	# get langs in the file
	try:
		lang_array = get_langs(languages_sector_size)
	except Exception as e:
		raise Exception(f"failed to read languages, {e}, {traceback.format_exc()}")

	# extract each sector
	curr_sector = None
	try:
		for sector in sectors:
			curr_sector = sector
			extract_sector(*sector[1:], endianness, lang_array, bank_version)

			if sector[0] and bank_version == 0:
				if externals_sector_size == 0:
					print("can't detect bank version")
				bank_version = 62
	except Exception as e:
		raise Exception(f"failed to extract sector {curr_sector}, {e}, {traceback.format_exc()}")

	return wwise_data

def get_langs(langs_sector_size):
	string_offset = reader.GetBufferPos()
	lang_array = {}
	langs = reader.ReadLong()

	for i in range(langs):
		lang_offset = reader.ReadLong()
		lang_id = reader.ReadLong()

		lang_offset += string_offset

		current = reader.GetBufferPos()

		reader.SetBufferPos(lang_offset)
		
		# get dummy bytes to detect encoding
		test_byte_1 = reader.ReadBytes(1)
		test_byte_2 = reader.ReadBytes(1)

		reader.SetBufferPos(lang_offset)

		if test_byte_1 == 0 or test_byte_2 == 0:
			lang_name = reader.ReadBytes(0x20).decode("utf-16le", "ignore").replace("\x00", "")
		else:
			lang_name = reader.ReadBytes(0x10).decode("utf-8", "ignore").replace("\x00", "")

		lang_array[lang_id] = lang_name

		reader.SetBufferPos(current)

	reader.SetBufferPos(string_offset + langs_sector_size)

	return lang_array

def detect_bank_version(offset):
	global bank_version

	current = reader.GetBufferPos()
	reader.SetBufferPos(offset)

	# maybe update buffer pos instead
	dummy = reader.ReadLong()
	dummy = reader.ReadLong()

	bank_version = reader.ReadLong()

	if bank_version > 0x1000:
		print("wrong bank version")
		bank_version = 62

	reader.SetBufferPos(current)

def extract_sector(section_size, is_sounds, is_externals, ext, endianness, lang_array, bank_version, filter_bnk_only=0, filter_wem_only=0, include_name=False):
	global wwise_data

	# check sector validity
	if section_size == 0:
		return
	files = reader.ReadLong()
	if files == 0:
		return

	entry_size = (section_size - 0x04) / files

	if entry_size == 0x18:
		alt_mode = 1
	else:
		alt_mode = 0

	for i in range(files):
		# ids must be unsigned here, if signed you need to do id += 2**32 afterwards
		if alt_mode == 1 and is_externals == 1:
			if endianness == 0:
				file_id_2 = reader.ReadULong()
				file_id_1 = reader.ReadULong()
			else:
				file_id_1 = reader.ReadULong()
				file_id_2 = reader.ReadULong()
		else:
			file_id = reader.ReadULong()

		block_size = reader.ReadLong()

		# get file size
		if alt_mode == 1 and is_externals == 1:
			size = reader.ReadLong()
		elif alt_mode == 1:
			size = reader.ReadLongLong()
		else:
			size = reader.ReadLong()

		offset = reader.ReadLong()
		lang_id = reader.ReadLong()

		if block_size != 0:
			offset *= block_size

		# bank version must be detected at this offset
		if is_sounds == 0 and bank_version == 0:
			detect_bank_version(offset)

		# update extension for olders banks using differents codecs
		if is_sounds == 1 and bank_version < 62:
			current = reader.GetBufferPos()

			codec_offset = offset + 0x14
			reader.SetBufferPos(codec_offset)

			codec = reader.ReadInt16()

			if codec == 0x0401 or codec == 0x0166:
				ext = "xma"
			elif codec == 0xFFFF:
				ext = "ogg"
			else:
				ext = "wav"

			reader.SetBufferPos(current)

		# set file path
		if lang_id == 0:
			path = ""
		else:
			path = "".join([f"{e}/" for e in list(lang_array.values())])

		# set file name
		if alt_mode == 1 and is_externals == 1:
			name = f"externals/{path}{file_id_1:08x}{file_id_2:08x}.{ext}"
		else:
			name = f"{path}{file_id}.{ext}"

		# filtering utilities
		if filter_bnk_only == 1 and ext != "bnk":
			continue

		if filter_wem_only == 1 and ext != "wem":
			continue

		# file infos
		if ext == "bnk":
			# get data from bnk
			print(offset)
			pos = reader.GetBufferPos()
			reader.SetBufferPos(offset)
			bnk_data = reader.ReadBytes(size)
			reader.SetBufferPos(pos)

			wems = bnk2wem(bnk_data)

			for wem in wems:
				wwise_data.append([f"{os.path.basename(name).split('.')[0]}_{wem[0]}.wem", offset+wem[1], wem[2], filename])
		else:
			wwise_data.append([os.path.basename(name), offset, size, filename])
