# AnimeWwise
An easy to use tool to extract audio from some anime games, with the original filenames and paths.


![image](https://github.com/user-attachments/assets/ce2c8b19-82a2-42fc-a149-ed9ffbb7c54b)

### ⚠️ Only Genshin, Star Rail and Zenless supported !

# Usage

1. Get the repo by [downloading it](https://github.com/Escartem/WwiseExtract/archive/refs/heads/master.zip) or cloning it (`git clone https://github.com/Escartem/AnimeWwise`)
> [!NOTE]
> This project uses ffmpeg version *3.4.2* which is the latest under 50MB. But it is also slower, if you want to slightly improve extraction speed, consider updating the ffmpeg binary to a [newer version](https://github.com/BtbN/FFmpeg-Builds/releases)
2. Install dependencies -> `pip install -r requirements.txt`
3. Run the app with `python app.py`
4. Select your input folder containing your `.pck` files, it can be your game audio folder directly (if you decide to use this one, make sure the game is not running)
![image](https://github.com/user-attachments/assets/e877a57a-a115-4c2e-beac-27d927d1a37e)
> [!TIP] 
> The audio folder can be found in the following locations
> - `GenshinImpact_Data\StreamingAssets\AudioAsset\...`
> - `StarRail_Data\Persistent\Audio\AudioPackage\Windows\... `
> - `ZenlessZoneZero_Data\StreamingAssets\Audio\Windows\Full\...`
5. Select your hdiff folder if needed
> [!NOTE]
> Diff files are `.hdiff` present in the update patches of the games. If you want to extract an hdiff content, you must have the pck file with the *same name before patch* in the input folder, pck's that do not have a corresponding hdiff file will be extracted normally, when they do have a corresponding hdiff file, *only the hdiff file content is extracted* and not the full pck
6. Select a mapping
> [!WARNING]
> By default, the files extracted from the game don't have names, the mappings are here to help restore the original filenames and paths so it's easier to search, there are only mappings for hoyo games and their coverage varies.
> The mapping does NOT guarantee to recover all the names !
7. After that, you can browse the files you loaded, if you messed up and wanna go back, you can select File > Reset to unload everything and go back to the starting screen.
![image](https://github.com/user-attachments/assets/73e2ece9-9fa7-4149-8674-762adb1ef50c)
> [!WARNING]
> The duration indicator is known to produce wrong results on music files or sfx, please take note when using it
8. In the `Extract` menu, you will be able to select what audio you want, choosing the output folder and audio format. You can extract everything or extract the files you selected
> [!NOTE]
> The program does not check for existing files in the output folder, it will overwrite them, make sure to check your folder before starting the extraction 
9. Extract your files, and enjoy !

# Why was this made

I know there is already dozens of tools that have the exact same purpose, being to extract audio from games or hoyo games, however, I made this anyway because of one functionality that others don't possess, which is file name recovery using mappings, because extracting is cool but browsing thousands of files with no names is just a pain, every single voiceline is a unique file. And I'm also planning a second unique functionality being a lookup tool, giving the user the ability to see every file inside the game, search the ones he needs and then extract them automatically, instead of having to load files and see what's in them. Stay tuned for that one :3

# Performance

The program has been tested and proved to be very efficient with extraction (not conversion), I've loaded the entire english package from genshin at 4.8 (around 17gb) and it took around 15 seconds to load and map every single of the ~100k files inside. And upon extracting them to .wem, it took around 10 seconds as well and during the entire process the program did not exceeded 500mb or so of ram usage. So I would say that it si good enough, however conversion is much slower, especially with ffmpeg (mp3 & ogg), some tweaks may be required to improve the speed.

# Contribute

Feel free to contribute to this project as much as you want, a share would be very appreciated aswell, I'll be glad to know if this helped anyone <3

# Credits

- [@Razmoth](https://github.com/Razmoth) - help on figuring out keys parsing to recover names for genshin and zzz
- [@Dimbreath](https://github.com/Dimbreath) - AnimeGameData, TurnBasedGameData and ZZZData
- [@Kei-Luna](https://github.com/Kei-Luna) - instructions on recovering names for genshin music
- [@davispuh](https://github.com/davispuh) - star rail keys bruteforce tool
- [@bnnm](https://github.com/bnnm) - wwise audio exploration tool
- @hcs - wwise audio extraction script
- [@vgmstream](https://github.com/vgmstream) and their contributors - wwise headers parsing
