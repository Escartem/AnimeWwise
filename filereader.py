import io
import os
import struct


class FileReader:
	""" 
	File reader for files, not much too say
	"""

	def __init__(self, file, endianness:str, name:str=None):
		self.stream = file
		self.endianness = endianness
		if name:
			self.name = name

	def _read(self, mode:str, bufferLength:int, endianness:str=None) -> bytes:
		# endianness override
		if endianness is None:
			endianness = self.endianness

		endianness = "<" if endianness == "little" else ">"

		return struct.unpack(f"{endianness}{mode}", bytearray(self.stream.read(bufferLength)))[0]

	# read methods
	def ReadInt8(self, endianness:str=None) -> int:
		return self._read("b", 1, endianness)

	def ReadUInt8(self, endianness:str=None) -> int:
		return self._read("B", 1, endianness)

	def ReadInt16(self, endianness:str=None) -> int:
		return self._read("h", 2, endianness)
	
	def ReadUInt16(self, endianness:str=None) -> int:
		return self._read("H", 2, endianness)
	
	def ReadInt32(self, endianness:str=None) -> int:
		return self._read("i", 4, endianness)
	
	def ReadUInt32(self, endianness:str=None) -> int:
		return self._read("I", 4, endianness)

	def ReadLong(self, endianness:str=None) -> int:
		return self._read("l", 4, endianness)

	def ReadULong(self, endianness:str=None) -> int:
		return self._read("L", 4, endianness)

	def ReadLongLong(self, endianness:str=None) -> int:
		return self._read("q", 8, endianness)

	def ReadULongLong(self, endianness:str=None) -> int:
		return self._read("Q", 8, endianness)

	def ReadBytes(self, length:int, endianness:str=None) -> bytes:
		return self._read(f"{str(length)}s", int(length), endianness)

	# buffer utils
	def GetBufferPos(self) -> int:
		return self.stream.tell()

	def SetBufferPos(self, pos:int):
		self.stream.seek(pos)

	def GetStreamLength(self) -> int:
		if isinstance(self.stream, io.BytesIO):
			return self.stream.getbuffer().nbytes
		elif isinstance(self.stream, io.BufferedReader):
			pos = self.GetBufferPos()
			self.stream.seek(0, os.SEEK_END)
			length = self.GetBufferPos()
			self.SetBufferPos(pos)
			return length
		else:
			raise Exception("unknown buffer type")

	def GetRemainingLength(self) -> int:
		return self.GetStreamLength() - self.GetBufferPos()

	def GetName(self) -> str:
		if self.name:
			return self.name
		return ""
