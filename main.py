# main.py

import subprocess
import sys

# Auto-install required packages if missing
def install_if_missing(package):
    try:
        __import__(package)
    except ImportError:
        print(f"📦 Installing missing package: {package}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Check and install
for pkg in ["requests", "flask"]:
    install_if_missing(pkg)

# Now safe to import
import os
import json
import requests
import webbrowser
from flask import Flask, request
from zipfile import ZipFile
import threading

# Constants
CONFIG_FILE = "config.json"
LINKS_FILE = "links.txt"
REDIRECT_URI = "http://localhost:8080/callback"
TOKEN_URL = "https://osu.ppy.sh/oauth/token"
AUTH_URL = "https://osu.ppy.sh/oauth/authorize"
DOWNLOAD_URL = "https://osu.ppy.sh/api/v2/beatmapsets/{}/download"

app = Flask(__name__)
auth_code = None
access_token = None

import json
import os

def load_credentials():
    config_path = "config.json"

    # If file doesn't exist, create an empty one
    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            json.dump({}, f)

    # Load existing config
    with open(config_path, "r") as f:
        try:
            creds = json.load(f)
        except json.JSONDecodeError:
            creds = {}

    # Check if both keys exist, otherwise ask and save
    if "client_id" not in creds or "client_secret" not in creds:
        print("🔑 osu! API credentials not found. Please enter them:")
        client_id = input("Client ID: ").strip()
        client_secret = input("Client Secret: ").strip()
        creds = {
            "client_id": int(client_id),  # or leave as str if preferred
            "client_secret": client_secret
        }
        with open(config_path, "w") as f:
            json.dump(creds, f, indent=4)
        print("✅ Credentials saved to config.json.")
    else:
        print("✅ Loaded stored client_id and client_secret.")

    return creds["client_id"], creds["client_secret"]

client_id, client_secret = load_credentials()

def get_credentials():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        print("✅ Loaded stored client_id and client_secret.")
    else:
        config = {
            "client_id": int(input("Enter your osu! client_id: ").strip()),
            "client_secret": input("Enter your osu! client_secret: ").strip()
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
        print("💾 Saved credentials to config.json")
    return config

@app.route("/callback")
def callback():
    global auth_code
    auth_code = request.args.get("code")
    return "✅ osu! login successful! You can close this tab."

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
        print("❌ links.txt not found.")
        return []
    with open(LINKS_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def download_maps(access_token, beatmap_links, output_folder):
    headers = {"Authorization": f"Bearer {access_token}"}
    os.makedirs(output_folder, exist_ok=True)

    for link in beatmap_links:
        try:
            set_id = link.split("/beatmapsets/")[1].split("#")[0]
            print(f"⬇ Downloading beatmapset {set_id}...")
            resp = requests.get(DOWNLOAD_URL.format(set_id), headers=headers)
            if resp.status_code == 200:
                file_path = os.path.join(output_folder, f"{set_id}.osz")
                with open(file_path, "wb") as f:
                    f.write(resp.content)
                print(f"✅ Saved: {file_path}")
            else:
                print(f"❌ Failed to download {set_id} | HTTP {resp.status_code}")
        except Exception as e:
            print(f"⚠ Error with {link}: {e}")

def zip_folder(folder_name):
    zip_name = f"{folder_name}.zip"
    with ZipFile(zip_name, "w") as zipf:
        for file in os.listdir(folder_name):
            zipf.write(os.path.join(folder_name, file), arcname=file)
    print(f"📦 Zipped to: {zip_name}")

def main():
    global access_token
    creds = get_credentials()
    client_id, client_secret = creds["client_id"], creds["client_secret"]

    auth_url = (
        f"{AUTH_URL}?client_id={client_id}&redirect_uri={REDIRECT_URI}"
        f"&response_type=code&scope=public identify"
    )
    webbrowser.open(auth_url)
    print("🌐 osu! login page opened in browser...")

    # Start Flask app in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(port=8080, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()

    # Wait for the auth_code to be set by the callback
    import time
    while auth_code is None:
        time.sleep(1)

    access_token = exchange_code_for_token(client_id, client_secret)
    if not access_token:
        return

    links = read_links()
    if not links:
        print("⚠ No beatmap links found.")
        return

    folder_name = input("Enter a name for the folder to save beatmaps: ").strip()
    download_maps(access_token, links, folder_name)
    zip_folder(folder_name)

if __name__ == "__main__":
    main()