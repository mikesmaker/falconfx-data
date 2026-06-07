"""
Creates the public 'falconfx-data' GitHub repo and pushes places.json + places.js.
Reads GITHUB_TOKEN from the environment.
"""

import os
import json
import base64
import urllib.request
import urllib.error

TOKEN = os.environ.get("GITHUB_TOKEN", "")
if not TOKEN:
    raise RuntimeError("GITHUB_TOKEN environment variable is not set.")

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "falconfx-pusher/1.0",
    "Content-Type": "application/json",
}

def gh(method, path, body=None):
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code

# ── 1. Get authenticated username ────────────────────────────────────────────
user_data, status = gh("GET", "/user")
if status != 200:
    raise RuntimeError(f"Auth failed ({status}): {user_data}")
username = user_data["login"]
print(f"Authenticated as: {username}")

REPO = "falconfx-data"

# ── 2. Create repo (idempotent — skip if already exists) ─────────────────────
repo_data, status = gh("POST", "/user/repos", {
    "name": REPO,
    "description": "FalconFX — Accra places database (OpenStreetMap)",
    "private": False,
    "auto_init": True,
})
if status == 201:
    print(f"Created repo: {username}/{REPO}")
elif status == 422:
    print(f"Repo already exists: {username}/{REPO} — continuing...")
else:
    raise RuntimeError(f"Failed to create repo ({status}): {repo_data}")

# ── 3. Push files ─────────────────────────────────────────────────────────────
FILES = ["places.json", "places.js"]

for filename in FILES:
    print(f"Pushing {filename}...", end=" ", flush=True)
    with open(filename, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    api_path = f"/repos/{username}/{REPO}/contents/{filename}"

    # Check if file already exists (get its SHA for update)
    existing, s = gh("GET", api_path)
    sha = existing.get("sha") if s == 200 else None

    body = {
        "message": f"Update {filename} — {sum(1 for _ in open(filename))} lines",
        "content": content_b64,
    }
    if sha:
        body["sha"] = sha

    result, status = gh("PUT", api_path, body)
    if status in (200, 201):
        print("✅")
    else:
        print(f"❌ ({status}): {result}")

# ── 4. Print CDN links ────────────────────────────────────────────────────────
print(f"\n🎉 All done! Your CDN links:")
print(f"\n  places.json (jsdelivr — fast, cached):")
print(f"  https://cdn.jsdelivr.net/gh/{username}/{REPO}@main/places.json")
print(f"\n  places.js (jsdelivr — fast, cached):")
print(f"  https://cdn.jsdelivr.net/gh/{username}/{REPO}@main/places.js")
print(f"\n  Raw GitHub (always latest):")
print(f"  https://raw.githubusercontent.com/{username}/{REPO}/main/places.json")
print(f"\n  places-loader.js update line:")
print(f"  const PLACES_CDN_URL = 'https://cdn.jsdelivr.net/gh/{username}/{REPO}@main/places.json';")
