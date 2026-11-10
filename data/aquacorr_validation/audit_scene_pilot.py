"""Sample public same-acquisition QA for the preselected non-GLORIA pilot."""

import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from scene_audit import E84_ITEM, PC_STAC, USGS, get_json, point_query, stac_at_point


HERE = Path(__file__).resolve().parent


def landsat(row):
    lon, lat = float(row["lon"]), float(row["lat"])
    day = row["date_satellite"]
    pathrow = row["scene_id"].split("_")[-2]
    token = f"_{pathrow}_{day.replace('-', '')}_"
    platform = {"L5": "LT05", "L7": "LE07", "L8": "LC08", "L9": "LC09"}[row["sensor"]]
    result = {"scene_id": row["scene_id"], "longitude": lon, "latitude": lat,
              "native_nir_rrs": row["native_nir"]}
    l1, u1 = stac_at_point("landsat-c2l1", lon, lat, day, USGS)
    l1_matches = [item for item in l1.get("features", []) if token in item["id"] and item["id"].startswith(platform + "_")]
    result["l1_search_url"] = u1
    result["l1_product_ids"] = [item["id"] for item in l1_matches]
    l2, u2 = stac_at_point("landsat-c2-l2", lon, lat, day, PC_STAC)
    l2_matches = [item for item in l2.get("features", []) if token in item["id"] and item["id"].startswith(platform + "_")]
    result["l2_search_url"] = u2
    result["l2_product_ids"] = [item["id"] for item in l2_matches]
    if len(l2_matches) == 1:
        values, point_url = point_query("landsat-c2-l2", l2_matches[0]["id"], lon, lat, ["qa_pixel", "nir08"])
        result["point_url"] = point_url
        result["qa_values"] = values
        qa = values.get("qa_pixel")
        if qa is not None:
            qa = int(qa)
            result["qa_pixel"] = qa
            result["qa_bits"] = {"dilated_cloud": bool(qa & 2), "cloud": bool(qa & 8),
                                 "cloud_shadow": bool(qa & 16), "snow": bool(qa & 32),
                                 "water": bool(qa & 128)}
    return result


def sentinel(row):
    lon, lat = float(row["lon"]), float(row["lat"])
    day = row["date_satellite"]
    satellite = row["sensor"]
    tile = next(part[1:] for part in row["scene_id"].split("_") if part.startswith("T") and len(part) == 6)
    item_id = f"{satellite}_{tile}_{day.replace('-', '')}_0_L1C"
    result = {"scene_id": row["scene_id"], "longitude": lon, "latitude": lat,
              "native_nir_rrs": row["native_nir"], "claimed_tile": tile}
    try:
        l1, u1 = get_json(E84_ITEM + item_id)
        result["l1_item_id"] = l1.get("id")
        bbox = l1.get("bbox")
        result["l1_bbox"] = bbox
        result["field_coordinate_in_claimed_tile_bbox"] = (
            bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]) if bbox else None
    except Exception as error:
        u1 = E84_ITEM + item_id
        result["l1_error"] = repr(error)
    result["l1_item_url"] = u1
    l2, u2 = stac_at_point("sentinel-2-l2a", lon, lat, day, PC_STAC)
    l2_matches = [item for item in l2.get("features", [])
                  if item["id"].startswith(satellite + "_")
                  and f"_T{tile}_" in item["id"] and day.replace("-", "") in item["id"]]
    result["l2_search_url"] = u2
    result["l2_product_ids"] = [item["id"] for item in l2_matches]
    if l2_matches:
        versions = []
        for item in l2_matches:
            values, point_url = point_query("sentinel-2-l2a", item["id"], lon, lat, ["SCL", "B8A"])
            versions.append({"item_id": item["id"], "point_url": point_url, "qa_values": values,
                             "scl": int(values["SCL"]) if values.get("SCL") is not None else None})
        result["qa_versions"] = versions
        classes = {v["scl"] for v in versions}
        if len(classes) == 1:
            result["scl"] = classes.pop()
        else:
            result["scl_conflict_across_versions"] = True
    return result


def audit_one(pair_index, label, row):
    result = {"pair_index": pair_index, "label": label, "matchup_id": row["matchup_id"],
              "sensor": row["sensor"], "source": row["source"]}
    try:
        result["scene_check"] = sentinel(row) if row["sensor"].startswith("S2") else landsat(row)
    except Exception as error:
        result["scene_error"] = repr(error)
    return result


def main():
    selected = json.loads((HERE / "scene_pilot_selection.json").read_text())
    jobs = [(i, label, pair[label]) for i, pair in enumerate(selected["pairs"]) for label in ("high", "low")]
    results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        future_map = {pool.submit(audit_one, *job): job for job in jobs}
        for future in as_completed(future_map):
            record = future.result()
            results.append(record)
            check = record.get("scene_check", {})
            print(record["sensor"], record["label"], record["matchup_id"],
                  check.get("qa_pixel", check.get("scl")), record.get("scene_error"), flush=True)
    results.sort(key=lambda row: (row["pair_index"], row["label"] != "high"))
    counts = defaultdict(Counter)
    for record in results:
        key = record["sensor"] + ":" + record["label"]
        check = record.get("scene_check", {})
        counts[key]["selected"] += 1
        if record.get("scene_error"):
            counts[key]["scene_error"] += 1
        if record["sensor"].startswith("S2"):
            if check.get("field_coordinate_in_claimed_tile_bbox") is False:
                counts[key]["outside_claimed_tile_bbox"] += 1
            if check.get("scl") is not None:
                counts[key]["scl_" + str(check["scl"])] += 1
            else:
                counts[key]["missing_scl"] += 1
        else:
            if not check.get("l1_product_ids"):
                counts[key]["l1_not_found_in_usgs_stac"] += 1
            bits = check.get("qa_bits")
            if bits is None:
                counts[key]["missing_qa_pixel"] += 1
            else:
                for bit in ("cloud", "dilated_cloud", "cloud_shadow", "snow", "water"):
                    if bits[bit]:
                        counts[key]["qa_" + bit] += 1
    registry = {"protocol": selected["protocol"], "selection_file": "scene_pilot_selection.json",
                "checks": results, "counts": {k: dict(v) for k, v in counts.items()},
                "interpretation_limit": "Extreme-tail convenience pilot with algorithmic QA; selected points are not a random sample of all waters, and low controls are not ground truth. No population error rate or causal diagnosis."}
    (HERE / "scene_pilot_qa_registry.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(registry["counts"], indent=2))


if __name__ == "__main__":
    main()
