# AnimeWwise
Extract audio from .pck and .hdiff to mp3 with this tool. It can in theory extract any pck or hdiff file from any game even though it was made for Genshin Impact. There are others tools that do the same but none of them were working so I just made my own.

# Usage

1. Get the repo by [downloading it](https://github.com/Escartem/WwiseExtract/archive/refs/heads/master.zip) or cloning it (`git clone https://github.com/Escartem/WwiseExtract`)
> ℹ️ This project uses ffmpeg version *3.4.2* which is the latest under 50Mb. But it is also slower, if you want to slightly improve extraction speed, consider updating the ffmpeg binary to a [newer version](https://github.com/BtbN/FFmpeg-Builds/releases)
2. Install dependencies -> `pip install -r requirements.txt`
3. Place all of your `.pck` files in the *audio* folder and `.pck.hdiff` in the *patch* folder
> ⚠️ If you want to extract an hdiff content, you must place the pck file with the *same name before patch* in the *audio* folder, pck's that do not have a corresponding hdiff file will be extracted normally, when they do have a corresponding hdiff file, *only the hdiff file content is extracted* and not the full pck
4. Start the program -> `python extract.py`
5. After finishing, everything will be in the *output* folder in the mp3 format (ogg may be added later)

---

## ℹ️ There is a separate branch called `dev` that may includes new features, you can check it out if you want to get them early. Those features are, as of right now :
- export files with their original names
- more export formats support
- reverse search ?

---

### And that's pretty much it, if you have any issue, suggestion or anything just open an issue or create a pr :)
