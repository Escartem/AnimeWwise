import os
import shutil
import zipfile
import filecmp
import subprocess
from halo import Halo
from progress.bar import PixelBar

# don't question how optimised this is
cwd = os.getcwd()
path = lambda path: os.path.join(cwd, path)
call = lambda args: subprocess.call(args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
spinner = Halo(text="spinner", spinner={'interval': 100, 'frames': ['◜', '◠', '◝', '◞', '◡', '◟']}, placement="right")

def main():
	# Extract tools on first launch
	if not os.path.exists("tools"):
		spinner.text = "Extracting tools for first launch"
		spinner.start()
		with zipfile.ZipFile(path("tools.zip"), "r") as zip:
			zip.extractall(cwd)
		os.remove(path("tools.zip"))
		spinner.stop()

	# Initial cleanup
	if os.path.exists("temp"):
		shutil.rmtree("temp")

	if os.path.exists("output") and len(os.listdir("output")) > 0:
		print("The output folder will be cleared when the program runs, press a key to continue or close this window")
		os.system("pause >nul")
		shutil.rmtree("output")

	# Get all files to process
	hdiff_files = [f for f in os.listdir("audio") if f.endswith(".pck") and os.path.exists(f"patch/{f}.hdiff")]
	alone_files = [f for f in os.listdir("audio") if f.endswith(".pck") and not os.path.exists(f"patch/{f}.hdiff")]
	files = [*hdiff_files, *alone_files]
	print(f"{len(files)} file(s) to extract")
	iteration = 0
	
	for file in files:
		try:
			iteration += 1
			filename = file
			if file in hdiff_files:
				filename = f"{file.split('.')[0]}.hdiff.pck"
			print(f"--- {filename} ({iteration}/{len(files)}) ---")

			alone, steps, curr = False, 7, 1
			if file in alone_files:
				alone, steps = True, 4

			######################################
			### 1 - Extract original .pck file ###
			######################################

			# update files
			if os.path.exists("temp"):
				shutil.rmtree("temp")
			os.makedirs(path("temp"), exist_ok=True)
			shutil.copy(f"audio/{file}", f"temp/{file}")

			output_path = "original_decoded"
			if alone:
				output_path = "wem"

			# prepare args
			args = [
				path("tools/quickbms/quickbms.exe"),
				"-o",
				"-Y",
				path("tools/quickbms/wavescan.bms"),
				path(f"temp/{file}"),
				path(f"temp/{output_path}")
			]

			# update spinner and call program
			spinner.text = f"[{curr}/{steps}] Extracting"
			spinner.start()
			call(args)
			spinner.stop()
			print(f"[{curr}/{steps}] Extracting")

			if alone:
				all_files = os.listdir(path("temp/wem"))

			######################################
			### 2 - Patch the .pck with .hdiff ###
			######################################

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

			if not alone:
				curr += 1

				# prepare args
				args = [
					path("tools/quickbms/quickbms.exe"),
					"-o",
					"-Y",
					path("tools/quickbms/wavescan.bms"),
					path(f"temp/{file}"),
					path(f"temp/patched_decoded")
				]

				# update spinner and call program
				spinner.text = f"[{curr}/{steps}] Extracting patch"
				spinner.start()
				call(args)
				spinner.stop()
				print(f"[{curr}/{steps}] Extracting patch")

				# cleanup useless files to save storage
				os.remove(f"temp/{file}")
				os.remove(f"temp/{file}.hdiff")
				os.remove(f"temp/{file.split('.')[0]}.original.pck")

			####################################
			### 4 - Search new/changed files ###
			####################################

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

			######################################################
			### 7 - Clean everything and move result to output ###
			######################################################

			curr += 1

			# update spinner
			spinner.text = f"[{curr}/{steps}] Cleaning up"
			spinner.start()

			filename = filename.split('.')[0]

			if not alone:
				# update files list
				new_files = [f"{f.split('.')[0]}.mp3" for f in new_files]
				changed_files = [f"{f.split('.')[0]}.mp3" for f in changed_files]

				# prepare folders 
				os.makedirs(path(f"output/{filename}"), exist_ok=True)
				os.makedirs(path("temp/new_files"), exist_ok=True)
				os.makedirs(path("temp/changed_files"), exist_ok=True)

				# split files into corresponding folder
				for file in new_files:
					shutil.move(f"temp/mp3/{file}", f"temp/new_files/{file}")

				for file in changed_files:
					shutil.move(f"temp/mp3/{file}", f"temp/changed_files/{file}")

				# move them to output
				final_path = f"output/{filename}"
				shutil.move("temp/new_files", f"{final_path}/new_files")
				shutil.move("temp/changed_files", f"{final_path}/changed_files")

				# cleanup
				shutil.rmtree("temp/mp3")
			else:
				# for no hdiff files
				os.makedirs(path(f"output/{filename} (no hdiff)"), exist_ok=True)
				shutil.move("temp/mp3", f"output/{filename} (no hdiff)")


			spinner.stop()
			print(f"[{curr}/{steps}] Cleaning up")
		except Exception as e:
			print("An error occured while processing this file ! Skipping to the next one, details of the error bellow :")
			print(e)

	# all files processed
	shutil.rmtree("temp")
	print("Done extracting everything !")

if __name__ == "__main__":
	main()
