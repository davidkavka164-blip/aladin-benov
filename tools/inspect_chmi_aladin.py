import bz2
import io
import re
import sys
import requests
import eccodes

BASE = "https://opendata.chmi.cz/meteorology/weather/nwp_aladin/CZ_1km"
LAT, LON = 49.417362, 17.501343
FIELDS = [
    "CLSTEMPERATURE", "CLSHUMI_RELATIVE", "MSLPRESSURE",
    "CLSWIND_SPEED", "CLSWIND_DIREC", "CLSRAFAL_MOD_XFU",
    "SURFPREC_TOTAL", "SURFNEBUL_TOTALE", "SURFNEBUL_BASSE",
    "SURFNEBUL_MOYENN", "SURFNEBUL_HAUTE",
]
session = requests.Session()
session.headers["User-Agent"] = "ALADIN-Meteogram-Benov/1.0"

def links(url):
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return re.findall(r'href="([^"]+)"', r.text)

def newest_run():
    candidates = []
    for cycle in ("00", "06", "12", "18"):
        url = f"{BASE}/{cycle}/"
        for name in links(url):
            m = re.search(r"ALADCZ1K4opendata_(\d{10})_", name)
            if m:
                candidates.append((m.group(1), cycle, url, name))
    if not candidates:
        raise RuntimeError("No ALADIN GRIB files found in CHMI directory listings")
    # Latest complete cycle, based on the available filenames.
    dates = sorted({x[0] for x in candidates}, reverse=True)
    for run in dates:
        files = {}
        for date, cycle, url, name in candidates:
            if date == run:
                for field in FIELDS:
                    if f"_{field}." in name:
                        files[field] = url + name
        missing = [f for f in FIELDS if f not in files]
        if not missing:
            return run, files
    raise RuntimeError("No complete ALADIN run; missing fields in newest listings")

def key(gid, name):
    try:
        return eccodes.codes_get(gid, name)
    except Exception:
        return None

def main():
    run, files = newest_run()
    print(f"Selected CHMI ALADIN 1km run: {run} UTC")
    for field, url in files.items():
        print(f"\nFIELD {field}\nURL {url}")
        response = session.get(url, timeout=180)
        response.raise_for_status()
        payload = response.content
        if url.endswith(".bz2"):
            payload = bz2.decompress(payload)
        count = 0
        first = None
        last = None
        nearest_first = None
        nearest_last = None
        stream = io.BytesIO(payload)
        while True:
            gid = eccodes.codes_grib_new_from_file(stream)
            if gid is None:
                break
            count += 1
            meta = {
                k: key(gid, k) for k in (
                    "shortName", "name", "units", "typeOfLevel", "level",
                    "stepType", "stepRange", "startStep", "endStep",
                    "dataDate", "dataTime", "validityDate", "validityTime",
                    "forecastTime", "gridType", "numberOfPoints",
                )
            }
            nearest = eccodes.codes_grib_find_nearest(gid, LAT, LON)
            sample = nearest[0] if nearest else None
            if first is None:
                first, nearest_first = meta, sample
            last, nearest_last = meta, sample
            eccodes.codes_release(gid)
        print(f"MESSAGES {count}")
        print(f"FIRST {first}")
        print(f"FIRST_NEAREST {nearest_first}")
        print(f"LAST {last}")
        print(f"LAST_NEAREST {nearest_last}")
    print("\nInspection complete.")

if __name__ == "__main__":
    main()
