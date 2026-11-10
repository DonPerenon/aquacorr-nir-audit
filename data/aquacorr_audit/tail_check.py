"""Post-review exploratory upper-tail diagnostic for AquaCorr native NIR Rrs.

This does not validate pixel identity or establish a cause. It checks the
publisher's Rrs = rho_w / pi convention against extreme archived values.
"""
from __future__ import annotations

import collections
import csv
import gzip
import heapq
import json
import math
from pathlib import Path

from audit import NIR, digest


RAW = Path("data/aquacorr_global/aquacorr_matchups.csv.gz")
META = Path("data/aquacorr_global/aquacorr_metadata.json")
OUT = Path("data/aquacorr_audit/upper_tail_results.json")
SWIR = {
    "L5": "rrs_1678", "L7": "rrs_1650", "L8": "rrs_1609",
    "L9": "rrs_1608", "S2A": "rrs_1614", "S2B": "rrs_1610",
}
SPECTRUM = {
    "L5": (486, 571, 660, 839, 1678, 2217),
    "L7": (479, 561, 661, 835, 1650, 2208),
    "L8": (443, 483, 561, 655, 865, 1609, 2201),
    "L9": (443, 482, 561, 654, 865, 1608, 2201),
    "S2A": (492, 560, 665, 865, 1614, 2202),
    "S2B": (492, 559, 665, 864, 1610, 2186),
}
THRESHOLDS = (1 / math.pi, 1.0)


def bucket() -> dict:
    return {"nir_finite": 0, "above_1_over_pi": 0, "above_1": 0,
            "above_1_with_swir_finite": 0, "above_1_with_swir_above_0_1": 0,
            "above_1_with_swir_above_0_3": 0, "max_nir": None,
            "above_1_centroid_coordinates": 0}


def add(b: dict, nir: float, swir: float | None, centroid: str) -> None:
    b["nir_finite"] += 1
    b["above_1_over_pi"] += nir > THRESHOLDS[0]
    if b["max_nir"] is None or nir > b["max_nir"]:
        b["max_nir"] = nir
    if nir > 1:
        b["above_1"] += 1
        b["above_1_centroid_coordinates"] += centroid == "1"
        if swir is not None:
            b["above_1_with_swir_finite"] += 1
            b["above_1_with_swir_above_0_1"] += swir > 0.1
            b["above_1_with_swir_above_0_3"] += swir > 0.3


def main() -> None:
    metadata = json.loads(META.read_text())
    if metadata["atmospheric_correction"]["rrs_convention"] != "Rrs = rho_w / pi (Mobley 1999)":
        raise ValueError("Publisher's reflectance convention changed")
    overall = bucket()
    sensor = collections.defaultdict(bucket)
    source = collections.defaultdict(bucket)
    sites = set()
    scenes = set()
    top: list[tuple[float, int, dict]] = []
    top_by_sensor = {}
    top_by_source = {}
    with gzip.open(RAW, "rt", newline="") as stream:
        for i, row in enumerate(csv.DictReader(stream)):
            if row["passed_qc"] != "True":
                continue
            band = NIR[row["sensor"]]
            if not row[band]:
                continue
            nir = float(row[band])
            if not math.isfinite(nir):
                continue
            swir_text = row[SWIR[row["sensor"]]]
            swir = float(swir_text) if swir_text else None
            if swir is not None and not math.isfinite(swir):
                swir = None
            for b in (overall, sensor[row["sensor"]], source[row["source"]]):
                add(b, nir, swir, row["coord_centroid"])
            if nir > 1:
                sites.add((row["source"], row["site_id"]))
                scenes.add(row["scene_id"])
                record = {k: row[k] for k in ("matchup_id", "site_id", "source", "sensor", "scene_id", "date_satellite", "lat", "lon", "window_valid_pixels", "coord_centroid")}
                record.update({"native_nir_band": band, "native_nir_rrs": nir,
                               "native_swir_band": SWIR[row["sensor"]], "native_swir_rrs": swir,
                               "native_nir_window_median": row[band + "_median"],
                               "native_nir_window_mean": row[band + "_mean"],
                               "native_nir_window_std": row[band + "_std"],
                               "native_nir_window_cv": row[band + "_cv"],
                               "pipeline_flags": {k: row[k] for k in ("flag_negative_rrs", "flag_high_cv", "flag_insufficient_pixels", "flag_high_sza", "flag_acolite", "passed_qc")},
                               "available_spectrum": {f"rrs_{w}": float(row[f"rrs_{w}"])
                                                      for w in SPECTRUM[row["sensor"]] if row[f"rrs_{w}"]}})
                if row["sensor"] not in top_by_sensor or nir > top_by_sensor[row["sensor"]]["native_nir_rrs"]:
                    top_by_sensor[row["sensor"]] = record
                if row["source"] not in top_by_source or nir > top_by_source[row["source"]]["native_nir_rrs"]:
                    top_by_source[row["source"]] = record
                if len(top) < 12:
                    heapq.heappush(top, (nir, i, record))
                else:
                    heapq.heappushpop(top, (nir, i, record))
    if overall["nir_finite"] != sum(b["nir_finite"] for b in sensor.values()) or overall["above_1"] != sum(b["above_1"] for b in source.values()):
        raise AssertionError("Upper-tail totals do not reconcile")
    output = {
        "id": "AQTAIL001", "analysis_intent": "post_review_exploratory_diagnostic",
        "trigger": "Independent reviewer requested physical plausibility check after observing Rrs > 1 sr^-1; no hypothesis was changed or erased.",
        "raw_sha256": digest(RAW), "metadata_sha256": digest(META),
        "script_sha256": digest(Path(__file__)),
        "published_rrs_convention": metadata["atmospheric_correction"]["rrs_convention"],
        "thresholds_sr_inverse": {"rho_w_equivalent_gt_1": 1 / math.pi, "rrs_gt_1": 1.0},
        "overall_qc": overall,
        "by_sensor_qc": dict(sorted(sensor.items())),
        "by_source_qc": dict(sorted(source.items())),
        "unique_source_site_pairs_with_nir_gt_1": len(sites),
        "unique_scenes_with_nir_gt_1": len(scenes),
        "largest_twelve": [record for _, _, record in sorted(top, reverse=True)],
        "largest_per_sensor": dict(sorted(top_by_sensor.items())),
        "largest_per_source": dict(sorted(top_by_source.items())),
        "interpretation_limit": "Values and the publisher's convention are checked, but no original image or in situ radiometric reference was validated; high NIR/SWIR cannot establish pixel identity or a processing error mechanism.",
    }
    OUT.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: output[k] for k in ("published_rrs_convention", "overall_qc", "unique_source_site_pairs_with_nir_gt_1", "unique_scenes_with_nir_gt_1")}, indent=2))


if __name__ == "__main__":
    main()
