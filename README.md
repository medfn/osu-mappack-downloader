# osu! Mappack Downloader

A tool to download and package osu! beatmaps into mappacks

## Features

- Download beatmaps from custom APIs (e.g., catboy.best)
- Optional fallback to osu! official API (osu!supporter required)
- Retry logic and customizable settings
- Automatic zipping of downloaded mappacks


## Setup

1. **Configure:**
   - Edit `config/settings.json` for retry settings, API URLs, etc
   - Place your beatmap links in `data/links.txt` (one per line)

2. **Run the tool:**
   - Run `osu_beatmap_downloader.exe`

3. **Enter information:**
   - A window will open asking for a folder name, input something like `my mappack`

4. **Downloading Beatmaps:**
   - The tool will automaticly make a new folder with the name you provided and put all the downloaded beatmaps there
   - There will be a mappack rar file in your `data/mappacks/` folder

Enjoy your new mappack

---

**osu!** is copyright © peppy and ppy
This tool is not affiliated with or endorsed by ppy