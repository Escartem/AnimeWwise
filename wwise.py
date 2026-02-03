# wwise riff header parser
# thanks to hcs and bnnm work
import io
from vfs import decrypt
from filereader import FileReader

def parse_wwise(data, name, fid):
	reader = FileReader(io.BytesIO(data), "little", name=name)

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
		return None

	header = reader.ReadBytes(4)

	if header not in ["RIFF", "RIFX"]:
		# file may be vfs encrypted, however this is painfully slow so by default it will skip this and return no metadata

		if False: # set to true to parse metadata
			data = bytearray(data)
			wem_id = 0
			try:
				wem_id = int(fid[:-4])
			except ValueError:
				try:
					wem_id = int(fid[:-4], 16)
				except ValueError:
					return None
			decrypt(data, 0, len(data), wem_id, 0)
			if data[0:4] not in [b"RIFF", b"RIFX"]:
				print(f"[WARNING] invalid header {header} at {reader.GetName()}, assuming unreadable")
				return None
			reader = FileReader(io.BytesIO(data), "little", name=name) # reset reader
			header = reader.ReadBytes(4)
		else:
			return metadata

	# endian check header
	if header == b"RIFX":
		reader.endianness = "big"
	elif header == b"RIFF":
		reader.endianness = "little"
	else:
		print(f"[WARNING] invalid header {header} at {reader.GetName()}, assuming unreadable")
		return None

	# additional check
	reader.SetBufferPos(0x08)
	check = reader.ReadBytes(4)

	if check != b"WAVE" and check != "XWMA":
		print(f"[WARNING] invalid check mark {check}, assuming unreadable")
		return None

	# read chunks
	reader.SetBufferPos(0x0C)

	chunks = {}

	while reader.GetBufferPos() < reader.GetStreamLength():
		chunk_type = reader.ReadBytes(4)

		if chunk_type not in [b"fmt ", b"JUNK", b"data", b"akd ", b"cue ", b"LIST", b"smpl", b"hash", b"seek"]:
			print(f"[WARNING] unexpected chunk {chunk_type} at {reader.GetName()}")

		formatted_chunk_type = chunk_type.decode("utf-8").replace(" ", "")
		chunk_length = reader.ReadUInt32()

		if chunk_length > reader.GetRemainingLength():
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
		return None

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
		return None

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
		return None

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

	# parse duration
	if metadata["codec"] == "PTADPCM":
		metadata["layoutType"] = "interleave"
		metadata["interleaveBlockSize"] = metadata["blockSize"] // metadata["channels"]

		metadata["numSamples"] = int((chunks["data"]["length"] / (metadata["channels"] * metadata["interleaveBlockSize"])) * (2 + (metadata["interleaveBlockSize"] - 0x05) * 2))
		metadata["duration"] = metadata["numSamples"] / metadata["sampleRate"]
	
	elif metadata["codec"] == "VORBIS":
		if (metadata["blockSize"] != 0 or metadata["bitsPerSample"] != 0):
			print(f"[WARNING] worbis type at {reader.GetName()}, skipping")
			return None

		if "vorb" in chunks:
			# vorb chunk only in wwise earlier to 2012, therefore impossible for mihoyo games
			print(f"[WARNING] found vorb chunk at {reader.GetName()}, is this the correct game ?")
			return None

		extra_offset = chunks["fmt"]["offset"] + 0x18

		if metadata["extraSize"] != 0x30:
			print(f"[WARNING] unknown extra wwise size at {reader.GetName()}, skipping")
			return None

		data_offset = 0x10
		blocks_offset = 0x28
		# define header to type 2, packet to modified and codebook to aoTuV603, required ?

		# this somehow breaks and don't read correctly, why :c
		# stream_size * 8 * sample_rate / num_samples = bitrate * 1000
		metadata["numSamples"] = reader.ReadInt32(extra_offset)
		setup_offset = reader.ReadUInt32(extra_offset + data_offset)
		audio_offset = reader.ReadUInt32(extra_offset + data_offset + 0x04)

		block_size_1_exp = reader.ReadUInt8(extra_offset + blocks_offset)
		block_size_0_exp = reader.ReadUInt8(extra_offset + blocks_offset + 0x01)
		# if both exp are equals and extra size is 0x30, then reset packet type to standard

		chunks["data"]["offset"] -= audio_offset

		# ignore packets update and codebooks parse attempts, not implemented
		metadata["layoutType"] = "none"
		metadata["duration"] = metadata["numSamples"] / metadata["sampleRate"]

	return metadata
