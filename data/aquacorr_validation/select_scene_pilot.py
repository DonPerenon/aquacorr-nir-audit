"""Fix a deterministic QA pilot sample before reading any pilot scene QA."""

import csv
import gzip
import hashlib
import heapq
import json
import math
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "aquacorr_global/aquacorr_matchups.csv.gz"
NIR = {"L5": "rrs_839", "L7": "rrs_835", "L8": "rrs_865", "L9": "rrs_865", "S2A": "rrs_865", "S2B": "rrs_864"}
SEED = "aquacorr-scene-pilot-20261110"


def priority(identifier):
    return int.from_bytes(hashlib.sha256(f"{SEED}|{identifier}".encode()).digest()[:8], "big")


def eligible(row):
    if row["passed_qc"] != "True" or row["source"] in ("", "GLORIA") or row["coord_centroid"] == "1":
        return None
    if row["sensor"] not in NIR or not row["scene_id"] or not row["site_id"]:
        return None
    try:
        value, lat, lon = float(row[NIR[row["sensor"]]]), float(row["lat"]), float(row["lon"])
    except ValueError:
        return None
    if not all(map(math.isfinite, (value, lat, lon))) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return value


def compact(row, value):
    return {k: row[k] for k in ("matchup_id", "site_id", "source", "sensor", "scene_id", "lat", "lon", "date_satellite", "overpass_utc")} | {"native_nir": value}


def main():
    top = {sensor: [] for sensor in NIR}
    flow = Counter()
    with gzip.open(RAW, "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            value = eligible(row)
            if value is None or value <= 0.30:
                continue
            sensor = row["sensor"]
            flow[f"high_eligible_{sensor}"] += 1
            key = priority(row["matchup_id"])
            candidate = (-key, row["matchup_id"], compact(row, value))
            heap = top[sensor]
            if len(heap) < 500:
                heapq.heappush(heap, candidate)
            elif candidate > heap[0]:
                heapq.heapreplace(heap, candidate)
    candidate_keys = {(r["sensor"], r["scene_id"], r["source"])
                      for heap in top.values() for _, _, r in heap}
    low_by_key = {}
    with gzip.open(RAW, "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["sensor"], row["scene_id"], row["source"])
            if key not in candidate_keys:
                continue
            value = eligible(row)
            if value is None or not 0 <= value <= 0.03:
                continue
            p = priority(row["matchup_id"])
            if key not in low_by_key or p < low_by_key[key][0]:
                low_by_key[key] = (p, compact(row, value))
    pairs = []
    for sensor, heap in top.items():
        seen_scenes, seen_sites = set(), set()
        for neg_priority, _, high in sorted(heap, key=lambda item: -item[0]):
            key = (sensor, high["scene_id"], high["source"])
            if key not in low_by_key or high["scene_id"] in seen_scenes or high["site_id"] in seen_sites:
                continue
            low = low_by_key[key][1]
            pairs.append({"sensor": sensor, "high": high, "low": low, "selection_priority": -neg_priority})
            seen_scenes.add(high["scene_id"])
            seen_sites.add(high["site_id"])
            if len(seen_scenes) == 5:
                break
        flow[f"pairs_selected_{sensor}"] = len(seen_scenes)
    if not all(flow[f"pairs_selected_{sensor}"] == 5 for sensor in NIR):
        raise RuntimeError(f"Insufficient same-scene pairs: {dict(flow)}")
    result = {"protocol": json.loads((HERE / "scene_pilot_protocol.json").read_text()),
              "source_sha256": "ea44b8632ee57b6b214410282fa0ab5b6cc16b5b32477f842349552f1d82877c",
              "seed": SEED, "selection_flow": dict(flow), "pairs": pairs}
    path = HERE / "scene_pilot_selection.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"flow": dict(flow), "selected_matchup_ids": [(p["high"]["matchup_id"], p["low"]["matchup_id"]) for p in pairs]}, indent=2))


if __name__ == "__main__":
    main()
