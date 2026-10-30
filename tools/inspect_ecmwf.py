import requests
import eccodes
import os

DATE = "20261030"
TIME = "12"
STEP = 96
LAT, LON = 49.417362, 17.501343
ROOTS = [
    "https://data.ecmwf.int/forecasts",
    "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com",
]
PATHS = [
    f"{DATE}/{TIME}z/ifs/0p1/oper/{DATE}{TIME}0000-{STEP}h-oper-fc-sfc.grib2",
    f"{DATE}/{TIME}z/ifs/0p25/oper/{DATE}{TIME}0000-{STEP}h-oper-fc.grib2",
]
session = requests.Session()
session.headers["User-Agent"] = "ALADIN-Meteogram-Benov/1.0"

def main():
    selected = None
    for root in ROOTS:
        for path in PATHS:
            url = f"{root}/{path}"
            try:
                r = session.get(url, stream=True, timeout=90)
                print(f"CHECK {r.status_code} {r.headers.get('Content-Length')} {url}")
                if r.status_code == 200:
                    selected = (url, r)
                    break
                r.close()
            except Exception as exc:
                print(f"CHECK ERROR {url}: {exc}")
        if selected:
            break
    if not selected:
        raise RuntimeError("No direct ECMWF GRIB file found at tested URLs")
    url, response = selected
    target = "ecmwf_test.grib2"
    with open(target, "wb") as out:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                out.write(chunk)
    response.close()
    print(f"Downloaded {url}; bytes={os.path.getsize(target)}")
    count = 0
    with open(target, "rb") as stream:
        while True:
            gid = eccodes.codes_grib_new_from_file(stream)
            if gid is None:
                break
            count += 1
            nearest = eccodes.codes_grib_find_nearest(gid, LAT, LON)
            def get(k):
                try: return eccodes.codes_get(gid, k)
                except Exception: return None
            print({
                "shortName": get("shortName"), "name": get("name"),
                "units": get("units"), "step": get("step"),
                "validityDate": get("validityDate"),
                "validityTime": get("validityTime"),
                "typeOfLevel": get("typeOfLevel"), "level": get("level"),
                "sample": nearest[0].value if nearest else None,
            })
            eccodes.codes_release(gid)
    print(f"Total GRIB messages: {count}")

if __name__ == "__main__":
    main()
