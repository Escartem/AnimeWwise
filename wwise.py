# wwise riff header parser
# thanks to hcs and bnnm work

def parse_wwise(reader):
	header = reader.ReadBytes(4)

	# endian check header
	if header == b"RIFX":
		reader.endianness = "big"
	elif header == b"RIFF":
		reader.endianness = "little"
	else:
		raise Exception("invalid header")

	# additional check
	reader.SetBufferPos(0x08)
	check = reader.ReadBytes(4)

	if check != b"WAVE" and check != "XWMA":
		raise Exception("invalid file")

	# read chunks
	reader.SetBufferPos(0x0C)

	chunks = {}

	while reader.GetBufferPos() < reader.GetStreamLength():
		# relevants chunks types
		# "fmt "
		# "data"
		# "JUNK"

		chunk_type = reader.ReadBytes(4)

		if chunk_type not in [b"fmt ", b"JUNK", b"data"]:
			raise Exception("invalid chunk")

		formatted_chunk_type = chunk_type.decode("utf-8").replace(" ", "")
		chunk_length = reader.ReadUInt32()
		chunks[formatted_chunk_type] = {
			"length": chunk_length,
			"offset": reader.GetBufferPos(),
			"data": reader.ReadBytes(chunk_length)
		}

	# reader fmt header
	if chunks["fmt"]["length"] < 0x10:
		raise Exception("invalid fmt chunk length")

	reader.SetBufferPos(chunks["fmt"]["offset"])

	metadata = {
		"format": reader.ReadUInt16(),
		"channels": reader.ReadUInt16(),
		"sampleRate": reader.ReadUInt32(),
		"avgBitrate": reader.ReadUInt32(),
		"blockSize": reader.ReadUInt16(),
		"bitsPerSample": reader.ReadUInt16(),
		"extraSize": 0,
		"channelLayout": None,
		"channelType": None,
		"codec": None,
		"codecDisplay": None,
		"layoutType": None,
		"interleaveBlockSize": None,
		"numSamples": None,
		"duration": None
	}

	if chunks["fmt"]["length"] > 0x10 and metadata["format"] != 0x0165 and metadata["format"] != 0x0166:
		metadata["extraSize"] = reader.ReadUInt16()

	if metadata["extraSize"] >= 0x06:
		metadata["channelLayout"] = reader.ReadUInt32()

		if metadata["channelLayout"] & 0xFF == metadata["channels"]:
			metadata["channelType"] = (metadata["channelLayout"] >> 8) & 0x0F
			metadata["channelLayout"] = metadata["channelLayout"] >> 12

	if metadata["format"] == 0x0166:
		raise Exception("XMA2WAVEFORMATEX in fmt")

	# parse codec
	codecs = {
		0x0001: "PCM",
		0x0002: "IMA",
		0x0069: "IMA",
		0x0161: "XWLA",
		0x0162: "XWMA",
		0x0165: "XMA2",
		0x0166: "XMA2",
		0xAAC0: "AAC",
		0xFFF0: "DSP",
		0xFFFB: "HEVAG",
		0xFFFC: "ATRAC9",
		0xFFFE: "PCM",
		0xFFFF: "VORBIS",
		0x3039: "OPUSNX",
		0x3040: "OPUS",
		0x3041: "OPUSWW",
		0x8311: "PTADPCM"
	}

	# genshin should be PTADPCM
	# hsr and zzz should be VORBIS

	if metadata["format"] not in codecs:
		raise Exception("unknown codec")

	codec = codecs[metadata["format"]]

	if codec not in ["PTADPCM", "VORBIS"]: # Platinum "PtADPCM" custom ADPCM for Wwise
		print(f"unhandled codec -> {codec}")

	metadata["codec"] = codec

	# codec name
	codecs_names = {
		"PTADPCM": "Platinum 4-bit ADPCM",
		"VORBIS": "Custom Vorbis"
	}

	if codec in codecs_names:
		metadata["codecDisplay"] = codecs_names[codec]
	else:
		metadata["codecDisplay"] = codec

	# parse more infos
	if metadata["codec"] == "PTADPCM":
		metadata["layoutType"] = "interleave"
		metadata["interleaveBlockSize"] = metadata["blockSize"] // metadata["channels"]

		metadata["numSamples"] = int((chunks["data"]["length"] / (metadata["channels"] * metadata["interleaveBlockSize"])) * (2 + (metadata["interleaveBlockSize"] - 0x05) * 2))
		metadata["duration"] = metadata["numSamples"] / metadata["sampleRate"]

	return metadata

	# TODO: parse VORBIS
