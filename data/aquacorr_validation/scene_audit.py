"""Query public STAC and QA endpoints for selected GLORIA scene points."""

import csv
import io
import json
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path


HERE = Path(__file__).resolve().parent
USGS = "https://landsatlook.usgs.gov/stac-server/search"
PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_POINT = "https://planetarycomputer.microsoft.com/api/data/v1/item/point/"
E84_ITEM = "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l1c/items/"


def get_json(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "AquaCorr-NIR-audit/0.1"}), timeout=30) as response:
        return json.load(response), url


def meta_rows():
    with zipfile.ZipFile(HERE / "GLORIA-2022.zip") as archive:
        with archive.open("GLORIA_2022/GLORIA_meta_and_lab.csv") as raw:
            return {r["GLORIA_ID"]: r for r in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))}


def select_cases_and_controls(rows):
    eligible = [r for r in rows if r["primary_eligible"] == "True"]
    high = [r for r in eligible if float(r["satellite_nir"]) > 0.30]
    chosen = [("high", r) for r in high]
    seen_l8_scenes = set()
    for case in high:
        if case["sensor"] != "L8" or case["scene_id"] in seen_l8_scenes:
            continue
        seen_l8_scenes.add(case["scene_id"])
        controls = [r for r in eligible if r["sensor"] == "L8"
                    and r["site_name"] == case["site_name"]
                    and r["scene_id"] != case["scene_id"]
                    and float(r["satellite_nir"]) <= 0.03]
        controls.sort(key=lambda r: (abs((date.fromisoformat(r["date_satellite"]) - date.fromisoformat(case["date_satellite"])).days), int(r["matchup_id"])))
        if controls:
            chosen.append(("control_different_date", controls[0]))
    high_s2_scenes = {r["scene_id"] for r in high if r["sensor"].startswith("S2")}
    for scene in sorted(high_s2_scenes):
        controls = [r for r in eligible if r["scene_id"] == scene and float(r["satellite_nir"]) <= 0.03]
        controls.sort(key=lambda r: (float(r["satellite_nir"]), int(r["matchup_id"])))
        if controls:
            chosen.append(("control_same_scene", controls[0]))
    return sorted(chosen, key=lambda pair: (pair[1]["scene_id"], pair[0], int(pair[1]["matchup_id"])))


def point_query(collection, item, lon, lat, assets):
    reply, url = get_json(f"{PC_POINT}{lon},{lat}", [("collection", collection), ("item", item)] + [("assets", a) for a in assets])
    return {name.split("_b1")[0]: value for name, value in zip(reply.get("band_names", []), reply.get("values", []))}, url


def stac_at_point(collection, lon, lat, day, endpoint):
    d = date.fromisoformat(day)
    params = {"collections": collection, "bbox": f"{lon-0.0001},{lat-0.0001},{lon+0.0001},{lat+0.0001}",
              "datetime": f"{d.isoformat()}T00:00:00Z/{(d+timedelta(days=1)).isoformat()}T00:00:00Z", "limit": 30}
    return get_json(endpoint, params)


def audit_l8(row, lon, lat):
    day = row["date_satellite"]
    pathrow = row["scene_id"].split("_")[-2]
    token = f"_{pathrow}_{day.replace('-', '')}_"
    l1, l1_url = stac_at_point("landsat-c2l1", lon, lat, day, USGS)
    l1_matches = [f for f in l1.get("features", []) if token in f["id"]]
    l2, l2_url = stac_at_point("landsat-c2-l2", lon, lat, day, PC_STAC)
    l2_matches = [f for f in l2.get("features", []) if token in f["id"]]
    result = {"claimed_l1_scene_found": bool(l1_matches), "l1_stac_url": l1_url,
              "l1_product_id": l1_matches[0]["id"] if l1_matches else None,
              "l2_stac_url": l2_url, "l2_product_id": l2_matches[0]["id"] if l2_matches else None}
    if l2_matches:
        values, point_url = point_query("landsat-c2-l2", l2_matches[0]["id"], lon, lat,
                                        ["qa_pixel", "nir08", "red", "green", "blue", "swir16"])
        qa = values.get("qa_pixel")
        result.update({"qa_values": values, "point_url": point_url,
                       "qa_pixel_bits": {"cloud": bool(int(qa) & 8), "dilated_cloud": bool(int(qa) & 2),
                                         "cloud_shadow": bool(int(qa) & 16), "snow": bool(int(qa) & 32),
                                         "clear": bool(int(qa) & 64), "water": bool(int(qa) & 128)} if qa is not None else None})
    return result


def audit_s2(row, lon, lat):
    scene_parts = row["scene_id"].split("_")
    satellite = scene_parts[0]
    day = row["date_satellite"]
    tile = next(part[1:] for part in scene_parts if part.startswith("T") and len(part) == 6)
    item_id = f"{satellite}_{tile}_{day.replace('-', '')}_0_L1C"
    try:
        l1, l1_url = get_json(E84_ITEM + item_id)
    except Exception as error:
        l1, l1_url = {}, E84_ITEM + item_id
        l1_error = str(error)
    else:
        l1_error = None
    bbox = l1.get("bbox")
    in_bbox = bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3] if bbox else None
    l2, l2_url = stac_at_point("sentinel-2-l2a", lon, lat, day, PC_STAC)
    l2_matches = [f for f in l2.get("features", [])
                  if f"_T{tile}_" in f["id"] and f["id"].startswith(satellite + "_")
                  and day.replace("-", "") in f["id"]]
    result = {"l1_item_url": l1_url, "l1_item_id": l1.get("id"), "l1_error": l1_error,
              "claimed_tile": tile, "claimed_tile_bbox": bbox,
              "field_coordinate_in_claimed_tile_bbox": in_bbox,
              "l2_stac_url": l2_url, "l2_item_id": l2_matches[0]["id"] if l2_matches else None,
              "other_l2_tiles_at_point": [f["id"] for f in l2.get("features", []) if f not in l2_matches]}
    if l2_matches:
        values, point_url = point_query("sentinel-2-l2a", l2_matches[0]["id"], lon, lat,
                                        ["SCL", "B8A", "B04", "B03", "B02", "B11"])
        result.update({"qa_values": values, "point_url": point_url})
    return result


def main():
    with (HERE / "gloria_nir_pairs.csv").open(newline="") as stream:
        selected = select_cases_and_controls(list(csv.DictReader(stream)))
    meta = meta_rows()
    audited = []
    for label, row in selected:
        field = meta[row["gloria_id"]]
        lon, lat = float(field["Longitude"]), float(field["Latitude"])
        record = {"selection": label, "matchup_id": row["matchup_id"], "gloria_id": row["gloria_id"],
                  "scene_id": row["scene_id"], "site_name": row["site_name"],
                  "longitude": lon, "latitude": lat, "satellite_nir_rrs": float(row["satellite_nir"]),
                  "field_nir_rrs": float(row["field_nir"])}
        try:
            record["scene_check"] = audit_l8(row, lon, lat) if row["sensor"] == "L8" else audit_s2(row, lon, lat)
        except Exception as error:
            record["scene_error"] = repr(error)
        audited.append(record)
        print(row["matchup_id"], label, record.get("scene_check", {}).get("qa_values"), record.get("scene_error"), flush=True)
    registry = {"protocol": json.loads((HERE / "scene_audit_protocol.json").read_text()),
                "cases": audited,
                "limitations": "Point-level QA only. No georeferenced 3x3 native Level-1 pixel extraction or independent ACOLITE rerun was performed; L2 QA/SCL are algorithmic products and are not ground-truth labels."}
    (HERE / "scene_qa_registry.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
