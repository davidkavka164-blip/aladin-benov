#!/usr/bin/env python3
"""Build the Beňov 7-day forecast from direct CHMI ALADIN and ECMWF IFS GRIB data."""

import bz2
import json
import math
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import eccodes
import requests
from ecmwf.opendata import Client

LAT = 49.417362
LON = 17.501343
CHMI_BASE = "https://opendata.chmi.cz/meteorology/weather/nwp_aladin/CZ_1km"
OUTPUT = "data/forecast.json"

CHMI_FIELDS = {
    "temperature_2m": "CLSTEMPERATURE",
    "relative_humidity_2m": "CLSHUMI_RELATIVE",
    "pressure_msl": "MSLPRESSURE",
    "wind_speed_10m": "CLSWIND_SPEED",
    "wind_direction_10m": "CLSWIND_DIREC",
    "wind_gusts_10m": "CLSRAFAL_MOD_XFU",
    "cloud_cover": "SURFNEBUL_TOTALE",
    "cloud_cover_low": "SURFNEBUL_BASSE",
    "cloud_cover_mid": "SURFNEBUL_MOYENN",
    "cloud_cover_high": "SURFNEBUL_HAUTE",
    "precipitation": "SURFPREC_TOTAL",
}

ECMWF_PARAMS = [
    "2t", "2d", "msl", "tp", "10u", "10v", "10fg",
    "tcc", "lcc", "mcc", "hcc",
]
ECMWF_STEPS = list(range(72, 145, 3)) + [150, 156, 162, 168]

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "ALADIN-Meteogram-Benov/1.0"


def grib_get(gid, key):
    try:
        return eccodes.codes_get(gid, key)
    except Exception:
        return None


def finite(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or abs(value) >= 9998:
        return None
    return value


def nearest_value(gid):
    nearest = eccodes.codes_grib_find_nearest(gid, LAT, LON)
    return finite(nearest[0].value) if nearest else None


def find_chmi_runs():
    runs = {}
    for cycle in ("00", "12"):
        directory = f"{CHMI_BASE}/{cycle}/"
        response = SESSION.get(directory, timeout=60)
        response.raise_for_status()
        names = re.findall(r'href="([^"]+)"', response.text)
        for name in names:
            match = re.search(r"ALADCZ1K4opendata_(\d{10})_", name)
            if not match:
                continue
            run = match.group(1)
            if not run.endswith(cycle):
                continue
            item = runs.setdefault(run, {})
            for variable, suffix in CHMI_FIELDS.items():
                if f"_{suffix}." in name:
                    item[variable] = urljoin(directory, name)

    complete = [
        (run, files) for run, files in runs.items()
        if all(variable in files for variable in CHMI_FIELDS)
    ]
    complete.sort(key=lambda item: item[0], reverse=True)
    if not complete:
        raise RuntimeError("ČHMÚ: nebyl nalezen úplný běh ALADIN 1 km (00/12 UTC).")
    return complete


def read_chmi_field(url, variable):
    response = SESSION.get(url, timeout=240)
    response.raise_for_status()
    payload = response.content
    if url.endswith(".bz2"):
        payload = bz2.decompress(payload)

    values = {}
    with tempfile.TemporaryFile() as stream:
        stream.write(payload)
        stream.seek(0)
        while True:
            gid = eccodes.codes_grib_new_from_file(stream)
            if gid is None:
                break
            try:
                lead = grib_get(gid, "endStep")
                if lead is None:
                    lead = grib_get(gid, "step")
                lead = int(lead)
                value = nearest_value(gid)
                if value is not None:
                    if variable == "temperature_2m":
                        value -= 273.15
                    elif variable == "pressure_msl":
                        value /= 100.0
                    elif variable == "relative_humidity_2m" or variable.startswith("cloud_cover"):
                        if 0 <= value <= 1.5:
                            value *= 100.0
                    values[lead] = value
            finally:
                eccodes.codes_release(gid)

    required = range(1, 73) if variable == "precipitation" else range(0, 73)
    missing = [hour for hour in required if hour not in values]
    if missing:
        raise RuntimeError(
            f"ČHMÚ: {variable} má neúplnou časovou řadu; chybí {missing[:8]}"
        )
    return values


def load_chmi(run, files):
    print(f"Načítám ČHMÚ ALADIN 1 km, běh {run} UTC")
    raw = {}
    for variable, url in files.items():
        print(f"  ČHMÚ {variable}: {url}")
        raw[variable] = read_chmi_field(url, variable)

    hourly = {name: [None] * 73 for name in CHMI_FIELDS}
    for variable, values in raw.items():
        if variable != "precipitation":
            hourly[variable] = [values[h] for h in range(73)]

    # SURFPREC_TOTAL is a running total from the start of the ALADIN run.
    cumulative = raw["precipitation"]
    hourly["precipitation"][0] = 0.0
    for hour in range(1, 73):
        previous = cumulative.get(hour - 1, 0.0)
        current = cumulative[hour]
        amount = current - previous
        hourly["precipitation"][hour] = max(0.0, amount)

    print("  ČHMÚ srážky – kumulativní vzorek:",
          [round(cumulative[h], 4) for h in range(1, min(7, len(cumulative)) + 1)])
    return hourly


def relative_humidity_from_dewpoint(temp_k, dewpoint_k):
    if temp_k is None or dewpoint_k is None:
        return None
    temp_c = temp_k - 273.15
    dew_c = dewpoint_k - 273.15
    a, b = 17.625, 243.04
    exponent = (a * dew_c / (b + dew_c)) - (a * temp_c / (b + temp_c))
    return max(0.0, min(100.0, 100.0 * math.exp(exponent)))


def load_ecmwf(run):
    run_date = int(run[:8])
    run_time = int(run[8:])
    target = "ecmwf_forecast.grib2"
    print(
        f"Načítám ECMWF IFS HRES 0,25°, běh {run} UTC, "
        f"kroky {ECMWF_STEPS[0]}–{ECMWF_STEPS[-1]} h"
    )
    client = Client(source="ecmwf", model="ifs", resol="0p25")
    result = client.retrieve(
        date=run_date,
        time=run_time,
        stream="oper",
        type="fc",
        step=ECMWF_STEPS,
        param=ECMWF_PARAMS,
        levtype="sfc",
        target=target,
    )
    print(f"  ECMWF běh potvrzen: {result.datetime}; soubor {os.path.getsize(target)} B")

    raw = {
        "2t": {}, "2d": {}, "msl": {}, "tp": {},
        "10u": {}, "10v": {}, "10fg": {},
        "tcc": {}, "lcc": {}, "mcc": {}, "hcc": {},
    }
    with open(target, "rb") as stream:
        while True:
            gid = eccodes.codes_grib_new_from_file(stream)
            if gid is None:
                break
            try:
                short_name = grib_get(gid, "shortName")
                step = grib_get(gid, "step")
                if short_name in raw and step is not None:
                    raw[short_name][int(step)] = nearest_value(gid)
            finally:
                eccodes.codes_release(gid)

    for key in ("2t", "2d", "msl", "tp", "10u", "10v", "tcc", "lcc", "mcc", "hcc"):
        missing = [step for step in ECMWF_STEPS if step not in raw[key]]
        if missing:
            raise RuntimeError(f"ECMWF: chybí {key} pro kroky {missing[:8]}")
    missing_gust = [step for step in ECMWF_STEPS if step not in raw["10fg"]]
    if missing_gust:
        print(f"  Upozornění: ECMWF nemá nárazy větru pro kroky {missing_gust[:8]}")

    points = {}
    for step in ECMWF_STEPS:
        temp_k = raw["2t"][step]
        dew_k = raw["2d"][step]
        u = raw["10u"][step]
        v = raw["10v"][step]
        points[step] = {
            "temperature_2m": temp_k - 273.15 if temp_k is not None else None,
            "relative_humidity_2m": relative_humidity_from_dewpoint(temp_k, dew_k),
            "pressure_msl": raw["msl"][step] / 100.0 if raw["msl"][step] is not None else None,
            "wind_u": u,
            "wind_v": v,
            "wind_gusts_10m": raw["10fg"].get(step),
            "cloud_cover": raw["tcc"][step] * 100.0 if raw["tcc"][step] is not None else None,
            "cloud_cover_low": raw["lcc"][step] * 100.0 if raw["lcc"][step] is not None else None,
            "cloud_cover_mid": raw["mcc"][step] * 100.0 if raw["mcc"][step] is not None else None,
            "cloud_cover_high": raw["hcc"][step] * 100.0 if raw["hcc"][step] is not None else None,
            "precipitation_total_mm": raw["tp"][step] * 1000.0 if raw["tp"][step] is not None else None,
        }
    return points


def interpolate(left, right, fraction):
    if left is None:
        return right
    if right is None:
        return left
    return left + (right - left) * fraction


def wind_components(speed, direction):
    if speed is None or direction is None:
        return None, None
    radians = math.radians(direction)
    return -speed * math.sin(radians), -speed * math.cos(radians)


def wind_from_components(u, v):
    if u is None or v is None:
        return None, None
    speed = math.hypot(u, v)
    direction = (math.degrees(math.atan2(-u, -v)) + 360.0) % 360.0
    return speed, direction


def merge_forecasts(base, chmi, ecmwf):
    names = [
        "temperature_2m", "relative_humidity_2m", "pressure_msl",
        "wind_gusts_10m", "cloud_cover", "cloud_cover_low",
        "cloud_cover_mid", "cloud_cover_high",
    ]
    result = {name: [None] * 169 for name in names}
    result["precipitation"] = [None] * 169
    result["snowfall"] = [None] * 169
    wind_u = [None] * 169
    wind_v = [None] * 169

    for name in names:
        result[name][:73] = chmi[name]
    result["precipitation"][:73] = chmi["precipitation"]
    result["snowfall"] = [None] * 169

    for hour in range(73):
        wind_u[hour], wind_v[hour] = wind_components(
            chmi["wind_speed_10m"][hour],
            chmi["wind_direction_10m"][hour],
        )

    intervals = list(zip(ECMWF_STEPS[:-1], ECMWF_STEPS[1:]))
    for low, high in intervals:
        left = {}
        if low == 72:
            for name in names:
                left[name] = chmi[name][72]
            left_u, left_v = wind_u[72], wind_v[72]
        else:
            left = ecmwf[low]
            left_u, left_v = left["wind_u"], left["wind_v"]

        right = ecmwf[high]
        for hour in range(low + 1, high + 1):
            fraction = (hour - low) / (high - low)
            for name in names:
                result[name][hour] = interpolate(left[name], right[name], fraction)
            wind_u[hour] = interpolate(left_u, right["wind_u"], fraction)
            wind_v[hour] = interpolate(left_v, right["wind_v"], fraction)

        # ECMWF total precipitation is cumulative in metres from forecast start.
        amount = right["precipitation_total_mm"] - left.get(
            "precipitation_total_mm",
            ecmwf[low]["precipitation_total_mm"] if low in ecmwf else None,
        )
        if amount is None or not math.isfinite(amount):
            raise RuntimeError(f"ECMWF: nelze vypočítat srážky mezi {low} a {high} h")
        rate = max(0.0, amount) / (high - low)
        for hour in range(low + 1, high + 1):
            result["precipitation"][hour] = rate

    result["wind_speed_10m"] = [None] * 169
    result["wind_direction_10m"] = [None] * 169
    for hour in range(169):
        speed, direction = wind_from_components(wind_u[hour], wind_v[hour])
        result["wind_speed_10m"][hour] = speed
        result["wind_direction_10m"][hour] = direction

    times = [
        (base + timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for hour in range(169)
    ]
    result["time"] = times
    return result


def main():
    candidates = find_chmi_runs()
    last_error = None
    for run, files in candidates:
        try:
            base = datetime.strptime(run, "%Y%m%d%H").replace(tzinfo=timezone.utc)
            chmi = load_chmi(run, files)
            ecmwf = load_ecmwf(run)
            hourly = merge_forecasts(base, chmi, ecmwf)
            os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
            payload = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "run_utc": base.isoformat(),
                "location": {"name": "Beňov", "latitude": LAT, "longitude": LON},
                "sources": {
                    "hours_0_72": "ČHMÚ ALADIN 1 km",
                    "hours_72_168": "ECMWF IFS HRES 0.25°",
                    "licence": "CC BY 4.0",
                },
                "hourly": hourly,
            }
            with open(OUTPUT, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
                stream.write("\n")
            print(
                f"Hotovo: {OUTPUT}, {len(hourly['time'])} hodin, "
                f"běh {run} UTC, {os.path.getsize(OUTPUT)} B"
            )
            print(
                "Přechod modelů: 72 h; poslední hodnoty:",
                {key: hourly[key][-1] for key in (
                    "temperature_2m", "wind_speed_10m", "precipitation",
                    "cloud_cover", "pressure_msl"
                )}
            )
            return
        except Exception as exc:
            last_error = exc
            print(f"Běh {run} se nepodařilo sestavit: {exc}")
    raise RuntimeError(f"Nepodařilo se sestavit úplnou předpověď: {last_error}")


if __name__ == "__main__":
    main()
