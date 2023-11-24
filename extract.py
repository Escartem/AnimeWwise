import os
import sys
import json
import shutil
import filecmp
import wavescan
import subprocess
from halo import Halo
from progress.bar import PixelBar


cwd = os.getcwd()
path = lambda path: os.path.join(cwd, path)
call = lambda args: subprocess.call(args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
spinner = Halo(text="spinner", spinner={'interval': 100, 'frames': ['◜', '◠', '◝', '◞', '◡', '◟']}, placement="right")
skips = "000000000" # used for debugging

# 1 - original extract
# 2 - patch
# 3 - patch extract
# 4 - filter files
# 5 - wem to wav
# 6 - wav to mp3
# 7 - map names
# 8 - clean up
# 9 - temp clean up

def main():
	# Initial cleanup
	if os.path.exists("temp") and skips[8] != "1":
		shutil.rmtree("temp")

	if os.path.exists("output") and len(os.listdir("output")) > 0:
		print("The output folder needs to be cleared, continue ? [Y/N]")
		select = input(">")
		if select.lower() == "y":
			shutil.rmtree("output")
		else:
			print("Aborting")
			exit()

	# Get all files to process
	hdiff_files = [f for f in os.listdir("audio") if f.endswith(".pck") and os.path.exists(f"patch/{f}.hdiff")]
	alone_files = [f for f in os.listdir("audio") if f.endswith(".pck") and not os.path.exists(f"patch/{f}.hdiff")]
	files = [*hdiff_files, *alone_files]
	
	if len(files) == 0:
		print("No files found !")
		return

	print(f"{len(files)} file(s) to extract")
	iteration = 0

	for file in files:
		try:
			iteration += 1
			filename = file
			if file in hdiff_files:
				filename = f"{file.split('.')[0]}.hdiff.pck"
			print(f"--- {filename} ({iteration}/{len(files)}) ---")

			alone, steps, curr = False, 8, 1
			if file in alone_files:
				alone, steps = True, 5

			######################################
			### 1 - Extract original .pck file ###
			######################################

			if skips[0] != "1":
				# update files
				if os.path.exists("temp"):
					shutil.rmtree("temp")
				os.makedirs(path("temp"), exist_ok=True)
				shutil.copy(f"audio/{file}", f"temp/{file}")

				output_path = "original_decoded"
				if alone:
					output_path = "wem"

				# update spinner and call program
				spinner.text = f"[{curr}/{steps}] Extracting"
				spinner.start()
				wavescan.extract(path(f"temp/{file}"), path(f"temp/{output_path}"))
				spinner.stop()
				print(f"[{curr}/{steps}] Extracting")

				if alone:
					all_files = os.listdir(path("temp/wem"))

			######################################
			### 2 - Patch the .pck with .hdiff ###
			######################################

			if skips[1] != "1":
				if not alone:
					curr += 1

					# update files
					shutil.copy(f"patch/{file}.hdiff", f"temp/{file}.hdiff")
					shutil.move(f"temp/{file}", f"temp/{file.split('.')[0]}.original.pck")

					# prepare args
					args = [
						path("tools/hpatchz/hpatchz.exe"),
						"-f",
						path(f"temp/{file.split('.')[0]}.original.pck"),
						path(f"temp/{file}.hdiff"),
						path(f"temp/{file}")
					]

					# update spinner and call program
					spinner.text = f"[{curr}/{steps}] Patching"
					spinner.start()
					call(args)
					spinner.stop()
					print(f"[{curr}/{steps}] Patching")

			#####################################
			### 3 - Extract patched .pck file ###
			#####################################

			if skips[2] != "1":
				if not alone:
					curr += 1

					# update spinner and call program
					spinner.text = f"[{curr}/{steps}] Extracting patch"
					spinner.start()
					wavescan.extract(path(f"temp/{file}"), path(f"temp/patched_decoded"))
					spinner.stop()
					print(f"[{curr}/{steps}] Extracting patch")

					# cleanup useless files to save storage
					os.remove(f"temp/{file}")
					os.remove(f"temp/{file}.hdiff")
					os.remove(f"temp/{file.split('.')[0]}.original.pck")

			####################################
			### 4 - Search new/changed files ###
			####################################

			if skips[3] != "1":
				if not alone:
					curr += 1

					# update spinner
					spinner.text = f"[{curr}/{steps}] Filtering files"
					spinner.start()

					# compare folders
					diff = filecmp.dircmp(path("temp/original_decoded"), path("temp/patched_decoded"))
					new_files, changed_files = diff.right_only, diff.diff_files
					all_files = [*new_files, *changed_files]

					# merge files
					os.makedirs(path("temp/wem"), exist_ok=True)

					for file in all_files:
						shutil.move(f"temp/patched_decoded/{file}", f"temp/wem/{file}")

					# cleanup useless folders to save storage
					shutil.rmtree("temp/original_decoded")
					shutil.rmtree("temp/patched_decoded")

					spinner.stop()
					print(f"[{curr}/{steps}] Filtering files")

			######################################
			### 5 - Convert .wem files to .wav ###
			######################################

			if skips[4] != "1":
				curr += 1

				# updates folders and progress bar
				os.makedirs(path("temp/wav"), exist_ok=True)
				bar = PixelBar(f"[{curr}/{steps}] Converting to wav ", max=len(all_files), suffix='%(percent).1f%% - %(eta)ds left')

				# convert each file one by one
				for file in all_files:
					args = [
						path("tools/vgmstream/vgmstream-cli.exe"),
						"-o",
						path(f"temp/wav/{file.split('.')[0]}.wav"),
						path(f"temp/wem/{file}")
					]

					call(args)
					bar.next()
				bar.finish()

				# cleanup
				shutil.rmtree("temp/wem")

			######################################
			### 6 - Convert .wav files to .mp3 ###
			######################################

			if skips[5] != "1":
				curr += 1

				# updates folders and progress bar
				os.makedirs(path("temp/mp3"), exist_ok=True)
				bar = PixelBar(f"[{curr}/{steps}] Converting to mp3 ", max=len(all_files), suffix='%(percent).1f%% - %(eta)ds left')

				# update file list
				all_files = [f"{f.split('.')[0]}.wav" for f in all_files]

				# convert each file one by one
				for file in all_files:
					args = [
						path("tools/ffmpeg/ffmpeg.exe"),
						"-i",
						path(f"temp/wav/{file}"),
						"-acodec",
						"libmp3lame",
						"-b:a",
						"192k",
						path(f"temp/mp3/{file.split('.')[0]}.mp3"),
					]

					call(args)
					bar.next()
				bar.finish()

				# cleanup
				shutil.rmtree("temp/wav")

				# update files list
				all_files = [f"{f.split('.')[0]}.mp3" for f in all_files]
				if not alone:
					new_files = [f"{f.split('.')[0]}.mp3" for f in new_files]
					changed_files = [f"{f.split('.')[0]}.mp3" for f in changed_files]

			#########################
			### 7 - Map filenames ###
			#########################

			if skips[6] != "1":
				curr += 1

				# update spinner
				spinner.text = f"[{curr}/{steps}] Mapping names"
				spinner.start()

				languages = ["english", "japanese", "chinese", "korean"]
				mapFiles = [f"{path('mapping/mapping')}{f.capitalize()}.json" for f in languages]
				namesTable = []

				for language in mapFiles:
					with open(language, "r") as f:
						namesTable.append(json.loads(f.read()))
						f.close()

				if alone:
					os.makedirs(path(f"temp/map/unmapped"), exist_ok=True)
				else:
					if len(new_files) > 0:
						os.makedirs(path(f"temp/map/new_files/unmapped"), exist_ok=True)
					if len(changed_files) > 0:
						os.makedirs(path(f"temp/map/changed_files/unmapped"), exist_ok=True)

				# guess lang
				lang = None
				for file in all_files:
					if lang is None or namesTable.index(language) == lang:
						for language in namesTable:
							if lang is None or namesTable.index(language) == lang:
								file_name = file.split(".")[0]

								if file_name in language:
									# lang detected, stick to it
									lang = namesTable.index(language)

				for file in all_files:
					if lang is None:
						language = []
					else:
						language = namesTable[lang]

					file_name = file.split(".")[0]
					base_path = "temp/map"
					if not alone:
						if file in new_files:
							base_path = "temp/map/new_files"
						elif file in changed_files:
							base_path = "temp/map/changed_files"

					if file_name in language:
						# lang detected, stick to it
						lang = namesTable.index(language)

						dir_path = path(f"{base_path}/{language[file_name]['path']}/{language[file_name]['name']}.mp3")
						os.makedirs(os.path.dirname(dir_path), exist_ok=True)
						shutil.copy(path(f"temp/mp3/{file}"), dir_path)
					else:
						shutil.copy(path(f"temp/mp3/{file}"), path(f"{base_path}/unmapped/{file}"))

				# stop spinner
				spinner.stop()
				print(f"[{curr}/{steps}] Mapping names")

			######################################################
			### 8 - Clean everything and move result to output ###
			######################################################

			if skips[7] != "1":
				curr += 1

				# update spinner
				spinner.text = f"[{curr}/{steps}] Cleaning up"
				spinner.start()

				filename = filename.split('.')[0]

				os.rename("temp/map", f"temp/{filename}")
				shutil.move(f"temp/{filename}", f"output/{filename}")

				spinner.stop()
				print(f"[{curr}/{steps}] Cleaning up")

		except Exception as e:
			print("")
			print("An error occured while processing this file ! Skipping to the next one, details of the error bellow :")
			print(f"Line {sys.exc_info()[-1].tb_lineno}, {e}")

	# all files processed
	if os.path.exists("temp") and skips[8] != "1":
		shutil.rmtree("temp")
	print("-"*30)
	print("Done extracting everything !")

if __name__ == "__main__":
	main()
