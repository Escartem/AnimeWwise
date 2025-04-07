# memory manager to prevent redundant calls to files and save up disk usage
import os
import mmap

class Allocator:
	def __init__(self):
		self.files = {}

	def load_file(self, path, name):
		with open(path, "rb") as f:
			mmap_object = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

		self.files[name] = mmap_object

	def unload_file(self, name):
		self.files[name].close()

	def read_at(self, file, offset, size):
		mmap_object = self.files[file]
		mmap_object.seek(offset)
		data = mmap_object.read(size)
		return data

	def free_mem(self):
		for file in list(self.files.keys()):
			self.files[file].close()
		self.files.clear()
