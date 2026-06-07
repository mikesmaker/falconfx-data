"""
FalconFX — OSM to places.js converter
======================================
1. Go to: https://overpass-api.de/api/interpreter?data=[out:json][timeout:90];(node["name"](5.45,-0.45,5.85,0.15);way["name"](5.45,-0.45,5.85,0.15););out center tags;
2. Save the downloaded file as osm_accra.json in same folder as this script
3. Run: python3 convert.py
4. Copy the output places.js into your falconfx/js/ folder
"""

import json
import re
import os

INPUT_FILE  = 'osm_accra.json'
OUTPUT_FILE = 'places.js'

# ── CATEGORY MAPPING ─────────────────────────────────────────────────────────
def get_cat(tags):
    a = tags.get('amenity','')
    s = tags.get('shop','')
    t = tags.get('tourism','')
    l = tags.get('leisure','')
    o = tags.get('office','')
    h = tags.get('highway','')
    p = tags.get('place','')
    r = tags.get('religion','')
    b = tags.get('building','')

    if a in ('hospital','clinic','doctors','dentist','pharmacy','nursing_home'): return 'hospital'
    if a in ('school','kindergarten'):                                           return 'school'
    if a in ('university','college','language_school'):                         return 'university'
    if a in ('marketplace',):                                                   return 'market'
    if a in ('fuel',):                                                          return 'fuel'
    if a in ('bank','atm','bureau_de_change'):                                  return 'bank'
    if a in ('police',):                                                        return 'police'
    if a in ('fire_station',):                                                  return 'police'
    if a in ('place_of_worship',):                                              return 'church'
    if a in ('restaurant','fast_food','cafe','bar','pub','food_court'):         return 'food'
    if a in ('cinema','theatre','arts_centre','community_centre','library'):    return 'leisure'
    if a in ('post_office','courthouse','townhall','embassy','consulate'):      return 'govt'
    if a in ('bus_station','ferry_terminal'):                                   return 'transport'
    if s in ('supermarket','department_store','mall','wholesale'):              return 'mall'
    if s and s not in ('',):                                                    return 'mall'
    if t in ('hotel','motel','guest_house','hostel','apartment'):               return 'hotel'
    if t in ('attraction','museum','zoo','aquarium','viewpoint','gallery'):     return 'leisure'
    if l in ('stadium','sports_centre','golf_course','swimming_pool','pitch'):  return 'leisure'
    if l in ('park','garden','nature_reserve','beach'):                         return 'leisure'
    if h in ('bus_stop',):                                                      return 'transport'
    if o in ('government','ngo','diplomatic','educational_institution'):        return 'govt'
    if o:                                                                       return 'office'
    if p in ('suburb','neighbourhood','quarter','town','village','hamlet'):     return 'area'
    if b in ('hospital',):                                                      return 'hospital'
    if b in ('school','university'):                                            return 'school'
    if b in ('hotel',):                                                         return 'hotel'
    if b in ('church','mosque','cathedral','temple'):                           return 'church'
    return 'other'

# ── SKIP FILTERS ─────────────────────────────────────────────────────────────
SKIP_NAMES = {'yes','no','true','false','none','n/a','unknown','undefined'}
SKIP_PATTERNS = re.compile(r'^\d+$|^[A-Z]{1,2}\d+$')  # pure numbers, codes like A1

def should_skip(name, tags):
    if not name or len(name.strip()) < 2:     return True
    if name.lower() in SKIP_NAMES:            return True
    if SKIP_PATTERNS.match(name.strip()):     return True
    # Skip if no useful tags at all
    useful = {'amenity','shop','tourism','leisure','office','highway','place','building'}
    if not any(k in tags for k in useful):    return True
    return False

# ── BUILD ALIASES ─────────────────────────────────────────────────────────────
def build_aliases(tags, name):
    aliases = []
    for key in ('alt_name','loc_name','short_name','official_name','old_name'):
        v = tags.get(key,'').strip()
        if v and v != name and len(v) > 1:
            aliases.append(v)
    # Add name without common suffixes for easier search
    for suffix in [' Hospital',' School',' Market',' Church',' Mosque',
                   ' Station',' Junction',' Clinic',' Hotel',' Road']:
        if name.endswith(suffix):
            short = name[:-len(suffix)].strip()
            if len(short) > 2 and short not in aliases:
                aliases.append(short)
    return aliases[:4]  # max 4 aliases

# ── MAIN ─────────────────────────────────────────────────────────────────────
def convert():
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: {INPUT_FILE} not found.")
        print("Download it from the URL at the top of this file.")
        return

    print(f"Loading {INPUT_FILE}...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    elements = data.get('elements', [])
    print(f"Raw elements: {len(elements):,}")

    seen     = set()
    places   = []
    skipped  = 0

    for el in elements:
        tags = el.get('tags', {})
        name = tags.get('name', '').strip()

        if should_skip(name, tags): skipped += 1; continue

        # Coordinates
        if el['type'] == 'node':
            lat, lng = el.get('lat'), el.get('lon')
        else:
            c = el.get('center', {})
            lat, lng = c.get('lat'), c.get('lon')

        if not lat or not lng:      skipped += 1; continue

        # Deduplicate by name + rounded position
        key = f"{name.lower()}_{round(lat,3)}_{round(lng,3)}"
        if key in seen:             skipped += 1; continue
        seen.add(key)

        cat     = get_cat(tags)
        aliases = build_aliases(tags, name)

        places.append({
            'name':    name,
            'aliases': aliases,
            'lat':     round(lat, 6),
            'lng':     round(lng, 6),
            'cat':     cat,
        })

    # Sort: areas first, then alphabetical
    cat_order = {'area':0,'transport':1,'hospital':2,'school':3,'university':4,
                 'market':5,'govt':6,'bank':7,'police':8,'church':9,'hotel':10,
                 'food':11,'mall':12,'leisure':13,'fuel':14,'office':15,'road':16,'other':17}
    places.sort(key=lambda p: (cat_order.get(p['cat'],99), p['name'].lower()))

    print(f"Places extracted: {len(places):,}")
    print(f"Skipped: {skipped:,}")

    # ── WRITE OUTPUT ─────────────────────────────────────────────────────────
    # Group by category for readable output
    by_cat = {}
    for p in places:
        by_cat.setdefault(p['cat'], []).append(p)

    lines = []
    lines.append('/* ═══════════════════════════════════════════════════════')
    lines.append(f'   FALCONFX — ACCRA PLACES DATABASE')
    lines.append(f'   {len(places):,} locations extracted from OpenStreetMap')
    lines.append(f'   Generated by convert.py — re-run to refresh')
    lines.append(' ═══════════════════════════════════════════════════════')
    lines.append('   HOW TO SEARCH: type 2+ chars in the search box')
    lines.append('   Results score: exact > starts-with > contains > alias')
    lines.append('═══════════════════════════════════════════════════════ */')
    lines.append('')
    lines.append('window.ACCRA_PLACES = [')
    lines.append('')

    cat_labels = {
        'area':'NEIGHBOURHOODS & COMMUNITIES','transport':'TRANSPORT HUBS',
        'hospital':'HOSPITALS & CLINICS','school':'SCHOOLS',
        'university':'UNIVERSITIES & COLLEGES','market':'MARKETS',
        'govt':'GOVERNMENT & LANDMARKS','bank':'BANKS & FINANCE',
        'police':'POLICE & EMERGENCY','church':'CHURCHES & MOSQUES',
        'hotel':'HOTELS','food':'RESTAURANTS & FOOD','mall':'MALLS & SHOPPING',
        'leisure':'LEISURE & SPORTS','fuel':'FUEL STATIONS',
        'office':'OFFICES & COMPANIES','road':'ROADS & STREETS','other':'OTHER',
    }

    for cat, ps in sorted(by_cat.items(), key=lambda x: cat_order.get(x[0],99)):
        label = cat_labels.get(cat, cat.upper())
        lines.append(f'/* ═══ {label} ({len(ps):,}) ═══ */')
        for p in ps:
            name_esc = p['name'].replace("'", "\\'")
            alias_str = ','.join(f"'{a.replace(chr(39), chr(92)+chr(39))}'" for a in p['aliases'])
            lines.append(
                f"{{name:'{name_esc}',aliases:[{alias_str}],"
                f"lat:{p['lat']},lng:{p['lng']},cat:'{p['cat']}'}},")
        lines.append('')

    lines.append('];')
    lines.append('')

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    # Also write places.json for CDN hosting
    json_file = 'places.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(places, f, ensure_ascii=False, separators=(',', ':'))

    size_kb   = os.path.getsize(OUTPUT_FILE) // 1024
    json_kb   = os.path.getsize(json_file) // 1024
    print(f"\n✅ Done!")
    print(f"   places.js  → {size_kb:,} KB  (copy to falconfx/js/ and deploy)")
    print(f"   places.json → {json_kb:,} KB  (upload to GitHub for CDN)")
    print(f"   Total places: {len(places):,}")
    print(f"\nNext steps:")
    print(f"  1. Copy places.js to falconfx/js/ and deploy to Netlify")
    print(f"  2. Create a free GitHub repo called 'falconfx-data'")
    print(f"  3. Upload places.json to that repo")
    print(f"  4. Update PLACES_CDN_URL in places-loader.js with your GitHub username")
    print(f"     e.g. https://cdn.jsdelivr.net/gh/YOUR_USERNAME/falconfx-data@main/places.json")

if __name__ == '__main__':
    convert()
