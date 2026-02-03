# decrypt and parse endfield's .chk files for audio

def decrypt(data, offset, count, seed, fileOffset):
	keySeed = seed + (fileOffset >> 2)

	dataIndex = offset
	remaining = count
	alignement = fileOffset & 3

	# head
	if alignement != 0:
		keyValue = key(keySeed)
		toAlign = min(4 - alignement, remaining)

		for i in range(toAlign):
			if dataIndex >= offset + count:
				break
			bytePos = alignement + i
			data[dataIndex] ^= (keyValue >> (bytePos * 8)) & 0xFF
			dataIndex += 1

		remaining -= toAlign
		keySeed += 1

	# body
	nBlocks = remaining // 4

	for i in range(nBlocks):
		keyValue = key(keySeed)
		dataValue = int.from_bytes(data[dataIndex:dataIndex+4], "little") ^ keyValue

		data[dataIndex] = dataValue & 0xFF
		data[dataIndex+1] = (dataValue >> 8) & 0xFF
		data[dataIndex+2] = (dataValue >> 16) & 0xFF
		data[dataIndex+3] = (dataValue >> 24) & 0xFF
		
		dataIndex += 4
		keySeed += 1

	# tail
	trailing = remaining & 3
	if trailing > 0:
		keyValue = key(keySeed)
		for i in range(trailing):
			data[dataIndex] ^= (keyValue >> (i * 8)) & 0xFF
			dataIndex += 1

def key(seed):
	k = ((((seed & 0xFF) ^ 0x9C5A0B29) & 0xFFFFFFFF) * 81861667) & 0xFFFFFFFF
	k = ((k ^ ((seed >> 8) & 0xFF)) * 81861667) & 0xFFFFFFFF
	k = ((k ^ ((seed >> 16) & 0xFF)) * 81861667) & 0xFFFFFFFF
	k = ((k ^ (seed >> 24) & 0xFF) * 81861667) & 0xFFFFFFFF
	return k
