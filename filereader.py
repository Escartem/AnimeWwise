import struct


class FileReader:
	""" 
	Simplified byte file reader with buffer 
	Not particularly optimised, contains repetitive functions
	In the scope of this project, not everything will be used either

	"""
	def __init__(self, file, endianness: str):
		self.stream = file
		self.endianness = endianness

	def _read(self, mode:str, bufferLength:int, endianness=None) -> bytes:
		# endianness override
		if endianness is None:
			endianness = self.endianness

		endianness = "<" if endianness == "little" else ">"

		return struct.unpack(f"{endianness}{mode}", bytearray(self.stream.read(bufferLength)))[0]

	# read methods
	def ReadInt16(self, endianness=None) -> int:
		return self._read("h", 2, endianness)
	
	def ReadUInt16(self, endianness=None) -> int:
		return self._read("H", 2, endianness)
	
	def ReadInt32(self, endianness=None) -> int:
		return self._read("i", 4, endianness)
	
	def ReadUInt32(self, endianness=None) -> int:
		return self._read("I", 4, endianness)

	def ReadLong(self, endianness=None) -> int:
		return self._read("l", 4, endianness)

	def ReadULong(self, endianness=None) -> int:
		return self._read("L", 4, endianness)

	def ReadLongLong(self, endianness=None) -> int:
		return self._read("q", 8, endianness)

	def ReadULongLong(self, endianness=None) -> int:
		return self._read("Q", 8, endianness)

	def ReadBytes(self, length:int, endianness=None) -> bytes:
		return self._read(f"{str(length)}s", int(length), endianness)

	# buffer utils
	def GetBufferPos(self) -> int:
		return self.stream.tell()

	def SetBufferPos(self, pos:int):
		self.stream.seek(pos)
