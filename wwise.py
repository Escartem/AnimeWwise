# wwise riff header parser
# thanks to hcs and bnnm work

def parse_wwise(reader):
	# default meta config
	metadata = {
		"format": 0,
		"channels": 0,
		"sampleRate": 0,
		"avgBitrate": 0,
		"blockSize": 0,
		"bitsPerSample": 0,
		"extraSize": 0,
		"channelLayout": None,
		"channelType": None,
		"codec": None,
		"codecDisplay": None,
		"layoutType": None,
		"interleaveBlockSize": None,
		"numSamples": None,
		"duration": 0
	}

	if reader.GetStreamLength() == 0:
		print(f"[WARNING] null stream size at {reader.GetName()}, unreadable block")
		return metadata

	header = reader.ReadBytes(4)

	# endian check header
	if header == b"RIFX":
		reader.endianness = "big"
	elif header == b"RIFF":
		reader.endianness = "little"
	else:
		print(f"[WARNING] invalid header {header} at {reader.GetName()}, assuming unreadable")
		return metadata

	# additional check
	reader.SetBufferPos(0x08)
	check = reader.ReadBytes(4)

	if check != b"WAVE" and check != "XWMA":
		print(f"[WARNING] invalid check mark {check}, assuming unreadable")
		return metadata

	# read chunks
	reader.SetBufferPos(0x0C)

	chunks = {}

	while reader.GetBufferPos() < reader.GetStreamLength():
		chunk_type = reader.ReadBytes(4)

		if chunk_type not in [b"fmt ", b"JUNK", b"data", b"akd ", b"cue ", b"LIST", b"smpl"]:
			print(f"[WARNING] unexpected chunk {chunk_type} at {reader.GetName()}")

		formatted_chunk_type = chunk_type.decode("utf-8").replace(" ", "")
		chunk_length = reader.ReadUInt32()

		if chunk_type == b"data" and chunk_length > reader.GetRemainingLength():
			chunk_length = reader.GetRemainingLength()

		chunks[formatted_chunk_type] = {
			"length": chunk_length,
			"offset": reader.GetBufferPos(),
			"data": reader.ReadBytes(chunk_length)
		}

	# reader fmt header
	fmt_length = chunks["fmt"]["length"]
	if fmt_length < 0x10:
		print(f"[WARNING] invalid fmt chunk length {fmt_length} at {reader.GetName()}, skipping")
		return metadata

	reader.SetBufferPos(chunks["fmt"]["offset"])

	metadata["format"] = reader.ReadUInt16()
	metadata["channels"] = reader.ReadUInt16()
	metadata["sampleRate"] = reader.ReadUInt32()
	metadata["avgBitrate"] = reader.ReadUInt32()
	metadata["blockSize"] = reader.ReadUInt16()
	metadata["bitsPerSample"] = reader.ReadUInt16()

	if chunks["fmt"]["length"] > 0x10 and metadata["format"] != 0x0165 and metadata["format"] != 0x0166:
		metadata["extraSize"] = reader.ReadUInt16()

	if metadata["extraSize"] >= 0x06:
		metadata["channelLayout"] = reader.ReadUInt32()

		if metadata["channelLayout"] & 0xFF == metadata["channels"]:
			metadata["channelType"] = (metadata["channelLayout"] >> 8) & 0x0F
			metadata["channelLayout"] = metadata["channelLayout"] >> 12

	if metadata["format"] == 0x0166:
		print(f"[WARNING] XMA2WAVEFORMATEX in fmt at {reader.GetName()}")
		return metadata

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

	# genshin should be *mostly* PTADPCM
	# hsr and zzz should be VORBIS

	if metadata["format"] not in codecs:
		print(f'[WARNING] unknown codec {metadata["format"]} at {reader.GetName()}')
		return metadata

	codec = codecs[metadata["format"]]

	if codec not in ["PTADPCM", "VORBIS"]: # Platinum "PtADPCM" custom ADPCM for Wwise
		print(f"[WARNING] unhandled codec {codec}, need to implement this later")

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
