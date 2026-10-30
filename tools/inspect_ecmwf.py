import os
import tempfile
import eccodes
from ecmwf.opendata import Client

DATE = int(os.environ.get("ECMWF_DATE", "20261030"))
TIME = int(os.environ.get("ECMWF_TIME", "12"))
LAT, LON = 49.417362, 17.501343
PARAMS = ["2t", "2r", "msl", "tp", "10u", "10v", "10fg", "tcc", "lcc", "mcc", "hcc"]

def get(gid, key):
    try:
        return eccodes.codes_get(gid, key)
    except Exception:
        return None

def main():
    target = "ecmwf_test.grib2"
    client = Client(source="aws", model="ifs", resol="0p1")
    result = client.retrieve(
        date=DATE, time=TIME, stream="oper", type="fc",
        step=96, param=PARAMS, levtype="sfc", target=target
    )
    print(f"Retrieved ECMWF run {result.datetime}; file {target}; bytes={os.path.getsize(target)}")
    count = 0
    with open(target, "rb") as stream:
        while True:
            gid = eccodes.codes_grib_new_from_file(stream)
            if gid is None:
                break
            count += 1
            nearest = eccodes.codes_grib_find_nearest(gid, LAT, LON)
            print({
                "shortName": get(gid, "shortName"),
                "name": get(gid, "name"),
                "units": get(gid, "units"),
                "step": get(gid, "step"),
                "validityDate": get(gid, "validityDate"),
                "validityTime": get(gid, "validityTime"),
                "typeOfLevel": get(gid, "typeOfLevel"),
                "level": get(gid, "level"),
                "sample": nearest[0].value if nearest else None,
            })
            eccodes.codes_release(gid)
    print(f"Total GRIB messages: {count}")

if __name__ == "__main__":
    main()
