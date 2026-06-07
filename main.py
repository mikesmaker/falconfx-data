import json
import time
import urllib.request
import urllib.parse

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
QUERY = "[out:json][timeout:90];(node[\"name\"](5.45,-0.45,5.85,0.15);way[\"name\"](5.45,-0.45,5.85,0.15););out center tags;"
OUTPUT_FILE = "osm_accra.json"

MAX_RETRIES = 3

for attempt in range(1, MAX_RETRIES + 1):
    print(f"Attempt {attempt}/{MAX_RETRIES}: Downloading map data from Overpass API...")
    try:
        payload = urllib.parse.urlencode({"data": QUERY}).encode("utf-8")
        req = urllib.request.Request(OVERPASS_URL, data=payload, method="POST")
        req.add_header("User-Agent", "osm-downloader/1.0")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read().decode("utf-8")

        parsed = json.loads(raw)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)

        print(f"Done. Saved {len(parsed.get('elements', []))} elements to {OUTPUT_FILE}")
        break
    except Exception as e:
        print(f"Error: {e}")
        if attempt < MAX_RETRIES:
            wait = 10 * attempt
            print(f"Retrying in {wait}s...")
            time.sleep(wait)
        else:
            print("All retries exhausted.")
            raise
