"""Reproducible post hoc GLORIA/AquaCorr NIR comparison; Python stdlib only.

All source files are public and pinned in protocol.json. This comparison does
not independently label bad pixels or test an atmospheric-correction mechanism.
"""

from __future__ import annotations

import bisect
import csv
import gzip
import hashlib
import io
import json
import math
import statistics
import tarfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCES = {
    "aquacorr": ROOT / "data/aquacorr_global/aquacorr_matchups.csv.gz",
    "gloria": HERE / "GLORIA-2022.zip",
    "s2_v4": HERE / "sentinel-2-spectral-response-functions-v4.xlsx",
    "s2_v5": HERE / "sentinel-2-spectral-response-functions-v5.xlsx",
    "l7": HERE / "rtcoef_landsat_7_tm_srf.tar.gz",
    "l8": HERE / "rtcoef_landsat_8_oli_srf.tar.gz",
    "protocol": HERE / "protocol.json",
}
NIR = {"L5": "rrs_839", "L7": "rrs_835", "L8": "rrs_865", "L9": "rrs_865", "S2A": "rrs_865", "S2B": "rrs_864"}
FIELDS = ["matchup_id", "gloria_id", "sensor", "scene_id", "site_name", "water_body_type", "date_insitu", "date_satellite", "field_time_utc", "overpass_utc", "hours_apart", "coordinate_distance_m", "gloria_flagged", "passed_qc", "satellite_nir", "field_nir", "nir_difference", "nir_absolute_difference", "same_day", "primary_eligible", "same_day_eligible", "inclusive_flag_eligible", "exclusion_reason"]
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def load_gloria():
    tables = {}
    with zipfile.ZipFile(SOURCES["gloria"]) as archive:
        for stem in ("GLORIA_meta_and_lab", "GLORIA_qc_flags", "GLORIA_Rrs"):
            with archive.open(f"GLORIA_2022/{stem}.csv") as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
                table = {}
                for row in reader:
                    key = row["GLORIA_ID"]
                    if key:
                        if key in table:
                            raise ValueError(f"Duplicate {stem} ID {key}")
                        table[key] = row
                tables[stem] = table
    return tables


def load_s2(path, sheet):
    """Read official S2 A/B average B8A response from OOXML without openpyxl."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet}.xml"))
        result = []
        for row in root.findall(".//m:sheetData/m:row", NS):
            cells = {}
            for cell in row.findall("m:c", NS):
                address = cell.get("r", "")
                if address.startswith(("A", "J")) and cell.get("t") != "s":
                    v = cell.find("m:v", NS)
                    if v is not None:
                        cells[address.rstrip("0123456789")] = number(v.text)
            if cells.get("A") is not None and cells.get("J") is not None:
                result.append((cells["A"], max(cells["J"], 0.0)))
    if not result or not (700 < max(w for w, _ in result) < 3000):
        raise ValueError(f"Unusable S2 response: {path}, sheet {sheet}")
    return result


def load_landsat(path, channel):
    with tarfile.open(path) as archive:
        name = next(m.name for m in archive.getmembers() if m.name.endswith(f"_ch{channel}.txt"))
        lines = archive.extractfile(name).read().decode("ascii").splitlines()
    result = []
    for line in lines:
        parts = line.split()
        if len(parts) != 2:
            continue
        wavenumber, response = number(parts[0]), number(parts[1])
        if wavenumber and response is not None:
            result.append((1e7 / wavenumber, max(response, 0.0)))
    result.sort()
    return result


def interpolate(points, wavelength):
    wavelengths = [x for x, _ in points]
    index = bisect.bisect_left(wavelengths, wavelength)
    if index == 0:
        return points[0][1] if wavelength == points[0][0] else 0.0
    if index == len(points):
        return 0.0
    x0, y0 = points[index - 1]
    x1, y1 = points[index]
    return y0 + (y1 - y0) * (wavelength - x0) / (x1 - x0)


def response_weights(points):
    """Trapezoid-rule integration on the 1-nm field grid, with coverage audit."""
    points = sorted(points)
    full = sum((x1 - x0) * (y0 + y1) / 2 for (x0, y0), (x1, y1) in zip(points, points[1:]))
    grid = [(nm, interpolate(points, nm)) for nm in range(350, 901)]
    weights = [y * (0.5 if nm in (350, 900) else 1.0) for nm, y in grid]
    coverage = sum(weights) / full
    if not 0.99 <= coverage <= 1.01:
        raise ValueError(f"Response outside GLORIA 350-900 nm: {coverage}")
    total = sum(weights)
    return [weight / total for weight in weights], coverage


def field_bandpass(spectrum, weights):
    total = 0.0
    for nm, weight in zip(range(350, 901), weights):
        if weight < 1e-7:
            continue
        value = number(spectrum.get(f"Rrs_{nm}"))
        if value is None:
            return None
        total += value * weight
    return total


def distance_m(a_lat, a_lon, b_lat, b_lon):
    values = [number(x) for x in (a_lat, a_lon, b_lat, b_lon)]
    if any(x is None for x in values):
        return None
    a, b, c, d = map(math.radians, values)
    h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1.0, math.sqrt(h)))


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "T")).replace(tzinfo=None)
    except ValueError:
        return None


def quantiles(values):
    if not values:
        return None
    values = sorted(values)
    def at(fraction):
        index = fraction * (len(values) - 1)
        low = math.floor(index)
        high = math.ceil(index)
        return values[low] + (values[high] - values[low]) * (index - low)
    return {"median": at(0.5), "q1": at(0.25), "q3": at(0.75)}


def summarize(rows):
    result = {}
    subsets = {
        "all_gloria": rows,
        "primary": [r for r in rows if r["primary_eligible"]],
        "same_day": [r for r in rows if r["same_day_eligible"]],
        "inclusive_flag": [r for r in rows if r["inclusive_flag_eligible"]],
    }
    for name, subset in subsets.items():
        by_sensor = defaultdict(list)
        for row in subset:
            by_sensor[row["sensor"]].append(row)
        groups = {"ALL": subset, **by_sensor}
        result[name] = {}
        for sensor, group in sorted(groups.items()):
            pairs = [r for r in group if r["field_nir"] is not None and r["satellite_nir"] is not None]
            high = [r for r in pairs if r["satellite_nir"] > 0.30]
            result[name][sensor] = {
                "matchups": len(group), "paired_values": len(pairs),
                "distinct_gloria_ids": len({r["gloria_id"] for r in group}),
                "distinct_scenes": len({r["scene_id"] for r in group}),
                "satellite_nir_gt_0_30": len(high),
                "high_distinct_gloria_ids": len({r["gloria_id"] for r in high}),
                "high_distinct_scenes": len({r["scene_id"] for r in high}),
                "field_nir_gt_0_30": sum(r["field_nir"] > 0.30 for r in pairs),
                "high_satellite_and_high_field": sum(r["field_nir"] > 0.30 for r in high),
                "satellite_nir": quantiles([r["satellite_nir"] for r in pairs]),
                "field_nir": quantiles([r["field_nir"] for r in pairs]),
                "signed_error": quantiles([r["nir_difference"] for r in pairs]),
                "absolute_error": quantiles([r["nir_absolute_difference"] for r in pairs]),
                "high_satellite_field_nir": quantiles([r["field_nir"] for r in high]),
                "high_satellite_signed_error": quantiles([r["nir_difference"] for r in high]),
            }
    result["exclusions_first_reason"] = dict(Counter(r["exclusion_reason"] or "eligible" for r in rows))
    return result


def main():
    protocol = json.loads(SOURCES["protocol"].read_text())
    tables = load_gloria()
    responses = {
        "L7": load_landsat(SOURCES["l7"], "04"),
        "L8": load_landsat(SOURCES["l8"], "05"),
        "S2A": load_s2(SOURCES["s2_v4"], 2),
        "S2B": load_s2(SOURCES["s2_v4"], 3),
    }
    weights_and_coverage = {sensor: response_weights(curve) for sensor, curve in responses.items()}
    v5_weights = {sensor: response_weights(load_s2(SOURCES["s2_v5"], sheet))[0]
                  for sensor, sheet in (("S2A", 2), ("S2B", 3))}
    rows = []
    v5_diffs = []
    with gzip.open(SOURCES["aquacorr"], "rt", newline="") as raw:
        for source in csv.DictReader(raw):
            if source["source"] != "GLORIA":
                continue
            sensor = source["sensor"]
            gid = source["site_id"].removeprefix("GLORIA_")
            meta = tables["GLORIA_meta_and_lab"].get(gid)
            flags = tables["GLORIA_qc_flags"].get(gid)
            spectrum = tables["GLORIA_Rrs"].get(gid)
            field = field_bandpass(spectrum, weights_and_coverage[sensor][0]) if sensor in responses and spectrum else None
            satellite = number(source.get(NIR.get(sensor, "")))
            field_time = parse_time(meta["Date_Time_UTC"]) if meta else None
            overpass = parse_time(source["overpass_utc"])
            hours = abs((overpass - field_time).total_seconds()) / 3600 if overpass and field_time else None
            same_day = bool(overpass and field_time and overpass.date() == field_time.date())
            distance = distance_m(meta["Latitude"], meta["Longitude"], source["lat"], source["lon"]) if meta else None
            flagged = flags.get("Flagged") if flags else None
            passed = source["passed_qc"] == "True"
            common = bool(meta and flags and spectrum and sensor in responses and passed and satellite is not None and field is not None and distance is not None and distance <= 100 and same_day)
            primary = common and flagged == "0" and hours is not None and hours <= 3
            same_day_eligible = common and flagged == "0"
            inclusive_flag = common and hours is not None and hours <= 3
            checks = [
                (bool(meta and flags and spectrum), "unmatched_gloria_id"),
                (sensor in responses, "no_bandpass_curve"),
                (passed, "satellite_qc_failed"),
                (satellite is not None, "missing_satellite_nir"),
                (field is not None, "missing_field_nir"),
                (flagged == "0", "gloria_flagged"),
                (same_day, "different_utc_day_or_missing_time"),
                (hours is not None and hours <= 3, "more_than_3_hours"),
                (distance is not None and distance <= 100, "coordinate_mismatch_gt_100m"),
            ]
            reason = next((label for yes, label in checks if not yes), "")
            row = {
                "matchup_id": source["matchup_id"], "gloria_id": gid, "sensor": sensor,
                "scene_id": source["scene_id"], "site_name": meta["Site_name"] if meta else "",
                "water_body_type": meta["Water_body_type"] if meta else "",
                "date_insitu": source["date_insitu"], "date_satellite": source["date_satellite"],
                "field_time_utc": meta["Date_Time_UTC"] if meta else "", "overpass_utc": source["overpass_utc"],
                "hours_apart": hours, "coordinate_distance_m": distance, "gloria_flagged": flagged,
                "passed_qc": passed, "satellite_nir": satellite, "field_nir": field,
                "nir_difference": satellite - field if satellite is not None and field is not None else None,
                "nir_absolute_difference": abs(satellite - field) if satellite is not None and field is not None else None,
                "same_day": same_day, "primary_eligible": primary,
                "same_day_eligible": same_day_eligible, "inclusive_flag_eligible": inclusive_flag,
                "exclusion_reason": reason,
            }
            rows.append(row)
            if primary and sensor in v5_weights:
                field_v5 = field_bandpass(spectrum, v5_weights[sensor])
                if field_v5 is not None:
                    v5_diffs.append(field_v5 - field)
    if len(rows) != 1535:
        raise AssertionError(f"Source count changed: {len(rows)}")
    rows.sort(key=lambda x: int(x["matchup_id"]))
    out = HERE / "gloria_nir_pairs.csv"
    with out.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "protocol": protocol["title"], "source_sha256": {key: sha256(path) for key, path in SOURCES.items()},
        "derived_csv_sha256": sha256(out),
        "response_coverage_350_900": {sensor: coverage for sensor, (_, coverage) in weights_and_coverage.items()},
        "s2_v5_minus_v4_field_bandpass": quantiles(v5_diffs),
        "counts_and_results": summarize(rows),
        "interpretation_guardrail": "This is a post hoc, overlapping-archive field measurement comparison, not an untouched holdout or an independently labelled pixel-error study."
    }
    (HERE / "gloria_nir_registry.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"primary": summary["counts_and_results"]["primary"],
                      "exclusions": summary["counts_and_results"]["exclusions_first_reason"],
                      "coverage": summary["response_coverage_350_900"]}, indent=2))


if __name__ == "__main__":
    main()
