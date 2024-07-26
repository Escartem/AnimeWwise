# bnk reader because they exist in the game
import io
from filereader import FileReader

def bnk2wem(data):
	# gets raw data from object
	reader = FileReader(io.BytesIO(data), "little")

	bkhd_signature = reader.ReadBytes(4)

	if bkhd_signature != b"\x42\x4B\x48\x44":
		raise Exception("not a valid bnk")

	bkhd_size = reader.ReadUInt32()
	reader.ReadBytes(bkhd_size)

	if reader.GetBufferPos() == reader.GetStreamLength():
		return [] # empty bnk

	didx_signature = reader.ReadBytes(4)

	if didx_signature != b"\x44\x49\x44\x58":
		return [] # invalid index signature (hirc block instead ?)

	didx_size = reader.ReadUInt32()
	n_wems = didx_size // 12
	wems = []

	for i in range(n_wems):
		wem_id = reader.ReadUInt32()
		wem_offset = reader.ReadUInt32()
		wem_size = reader.ReadUInt32()
		wems.append([wem_id, wem_offset, wem_size])

	data_signature = reader.ReadBytes(4)

	if data_signature != b"\x44\x41\x54\x41":
		return [] # invalid data signature (missing sector ?)

	data_size = reader.ReadUInt32()
	data_offset = reader.GetBufferPos()

	for wem in wems:
		wem[1] += data_offset

	return wems
