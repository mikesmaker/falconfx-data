"""
FalconFX — One-command OSM data refresh
Runs main.py (download) then convert.py (process) in sequence.
Usage: python3 refresh.py
"""

import subprocess
import sys
import time

def run(script):
    print(f"\n{'='*50}")
    print(f"  Running {script}...")
    print(f"{'='*50}")
    result = subprocess.run([sys.executable, script], check=True)
    return result

start = time.time()

try:
    run('main.py')
    run('convert.py')
    elapsed = round(time.time() - start, 1)
    print(f"\n✅ Refresh complete in {elapsed}s")
    print("   places.js  → copy to falconfx/js/ and redeploy to Netlify")
    print("   places.json → upload to GitHub CDN repo")
except subprocess.CalledProcessError as e:
    print(f"\n❌ Failed on step: {e}")
    sys.exit(1)
