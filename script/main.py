# osu_mappack_downloader/main.py

import subprocess
import sys
import os
import json
import requests
import webbrowser
from flask import Flask, request
from zipfile import ZipFile
import threading
import time

# Auto-install required packages if missing
def install_if_missing(package):
    try:
        __import__(package)
    except ImportError:
        print(f"📦 Installing missing package: {package}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

for pkg in ["requests", "flask"]:
    install_if_missing(pkg)

def get_base_dir():
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller bundle
        return os.path.dirname(sys.executable)
    else:
        # Running as a script
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = get_base_dir()
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

LINKS_FILE = os.path.join(DATA_DIR, "links.txt")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DOWNLOADS_DIR = os.path.join(DATA_DIR, "downloads")
MAPPACKS_DIR = os.path.join(DATA_DIR, "mappacks")

REDIRECT_URI = "http://localhost:8080/callback"
TOKEN_URL = "https://osu.ppy.sh/oauth/token"
AUTH_URL = "https://osu.ppy.sh/oauth/authorize"
OSU_DOWNLOAD_URL = "https://osu.ppy.sh/api/v2/beatmapsets/{}/download"

# Make sure necessary directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(MAPPACKS_DIR, exist_ok=True)

# Flask app to receive OAuth callback
app = Flask(__name__)
auth_code = None
access_token = None

@app.route("/callback")
def callback():
    global auth_code
    auth_code = request.args.get("code")
    return "✅ osu! login successful! You can close this tab."

def get_or_prompt_credentials():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump({}, f)

    with open(CONFIG_FILE, "r") as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError:
            config = {}

    if "client_id" not in config or "client_secret" not in config:
        print("🔑 osu! API credentials not found. Please enter them:")
        config["client_id"] = int(input("Client ID: ").strip())
        config["client_secret"] = input("Client Secret: ").strip()
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        print("✅ Credentials saved.")

    return config["client_id"], config["client_secret"]

def exchange_code_for_token(client_id, client_secret):
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }
    response = requests.post(TOKEN_URL, data=data)
    if response.status_code == 200:
        print("✅ Access token received.")
        return response.json()["access_token"]
    else:
        print("❌ Failed to get access token:", response.text)
        return None

def read_links():
    if not os.path.exists(LINKS_FILE):
        print(f"⚠ {LINKS_FILE} not found. Please add your beatmap links there.")
        return []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

DEFAULT_SETTINGS = {
    "retries": 5,
    "custom_apis": [
        "https://catboy.best/d/{id}"
    ],
    "retry_delay_seconds": 2,
    "zip_after_download": True,
    "skip_existing": True,
    "enable_osu_api_fallback": False
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=4)
        print(f"Created default {SETTINGS_FILE}. You can customize it.")
        return DEFAULT_SETTINGS
    with open(SETTINGS_FILE, "r") as f:
        try:
            settings = json.load(f)
        except Exception:
            print(f"⚠ Error reading {SETTINGS_FILE}, using defaults.")
            return DEFAULT_SETTINGS
    for k, v in DEFAULT_SETTINGS.items():
        if k not in settings:
            settings[k] = v
    return settings

def zip_folder(folder_name):
    folder_path = os.path.join(DOWNLOADS_DIR, folder_name)
    zip_path = os.path.join(MAPPACKS_DIR, f"{folder_name}.zip")
    if not os.path.exists(folder_path):
        print(f"⚠ Folder {folder_path} does not exist, skipping zip.")
        return
    with ZipFile(zip_path, "w") as zipf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, folder_path)
                zipf.write(file_path, arcname)
    print(f"📦 Zipped mappack: {zip_path}")

def download_maps(access_token, beatmap_links, folder_name, osu_session=None, settings=None):
    if settings is None:
        settings = DEFAULT_SETTINGS
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    output_folder = os.path.join(DOWNLOADS_DIR, folder_name)
    os.makedirs(output_folder, exist_ok=True)

    downloaded = 0
    failed = 0
    total = len(beatmap_links)

    retries = settings.get("retries", 5)
    custom_apis = settings.get("custom_apis", ["https://catboy.best/d/{id}"])
    retry_delay = settings.get("retry_delay_seconds", 2)
    skip_existing = settings.get("skip_existing", True)
    enable_osu_api_fallback = settings.get("enable_osu_api_fallback", False)

    for link in beatmap_links:
        try:
            # Extract beatmapset ID
            set_id = link.split("/beatmapsets/")[1].split("#")[0]
        except IndexError:
            print(f"❌ Invalid link format: {link}")
            failed += 1
            continue

        file_path = os.path.join(output_folder, f"{set_id}.osz")

        # Skip if already downloaded
        if skip_existing and os.path.exists(file_path):
            print(f"⚠ {file_path} already exists, skipping.")
            downloaded += 1
            continue

        # Try all custom APIs with retries
        success = False
        for api_url in custom_apis:
            for attempt in range(1, retries + 1):
                try:
                    url = api_url.format(id=set_id)
                    print(f"⬇ [{attempt}/{retries}] Trying {url} ...")
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200 and resp.content:
                        with open(file_path, "wb") as f:
                            f.write(resp.content)
                        print(f"✅ Downloaded from {url}: {file_path}")
                        downloaded += 1
                        success = True
                        break
                    else:
                        print(f"⚠ {url} failed | HTTP {resp.status_code}")
                except Exception as e:
                    print(f"⚠ Error from {url}: {e}")
                if attempt < retries:
                    time.sleep(retry_delay)
            if success:
                break

        if success:
            continue

        # Fallback to osu! official API if enabled
        if enable_osu_api_fallback:
            try:
                print(f"⬇ Trying fallback from osu! website for {set_id}...")
                osu_url = OSU_DOWNLOAD_URL.format(set_id)
                cookies = {"osu_session": osu_session} if osu_session else {}
                resp = requests.get(osu_url, headers=headers, cookies=cookies)
                if resp.status_code == 200 and resp.content:
                    with open(file_path, "wb") as f:
                        f.write(resp.content)
                    print(f"✅ Downloaded from osu! site: {file_path}")
                    downloaded += 1
                else:
                    print(f"❌ osu! fallback failed for {set_id} | HTTP {resp.status_code}")
                    failed += 1
            except Exception as e:
                print(f"⚠ osu! fallback error for {set_id}: {e}")
                failed += 1
        else:
            print(f"❌ All custom APIs failed for {set_id}. osu! API fallback is disabled.")
            failed += 1

    return downloaded, failed, total

def main():
    settings = load_settings()
    enable_osu_api_fallback = settings.get("enable_osu_api_fallback", False)

    access_token = None

    if enable_osu_api_fallback:
        # Only perform OAuth if fallback is enabled
        client_id, client_secret = get_or_prompt_credentials()

        # Open OAuth link in browser
        auth_url = (
            f"{AUTH_URL}?client_id={client_id}&redirect_uri={REDIRECT_URI}"
            f"&response_type=code&scope=public identify"
        )
        webbrowser.open(auth_url)
        print("🌐 osu! login page opened in browser...")

        # Start Flask listener
        flask_thread = threading.Thread(target=lambda: app.run(port=8080, use_reloader=False))
        flask_thread.daemon = True
        flask_thread.start()

        while auth_code is None:
            time.sleep(1)

        access_token = exchange_code_for_token(client_id, client_secret)
        if not access_token:
            return

    links = read_links()
    if not links:
        print("⚠ No beatmap links found.")
        return

    folder_name = input("📁 Enter name for beatmap folder: ").strip()
    downloaded, failed, total = download_maps(access_token, links, folder_name, settings=settings)
    if settings.get("zip_after_download", True):
        zip_folder(folder_name)

    # Show results
    print("\n===== Download Results =====")
    print(f"Total beatmaps: {total}")
    print(f"Downloaded:     {downloaded}")
    print(f"Failed:         {failed}")
    print("============================")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()