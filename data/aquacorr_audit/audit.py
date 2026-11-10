"""Reproducible, descriptive screen of AquaCorr-Global v1 CSV.

The screen flags unusually high NIR remote-sensing reflectance. A flag is not
proof that the original water-quality measurement or satellite pixel is wrong.
Only Python's standard library is required.
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path


NIR = {
    "L5": "rrs_839", "L7": "rrs_835", "L8": "rrs_865",
    "L9": "rrs_865", "S2A": "rrs_865", "S2B": "rrs_864",
}
THRESHOLDS = (0.05, 0.10, 0.20, 0.30)
MAIN_SOURCES = ("AquaMatch", "AquaSat_v1")
MIN_SITE_MATCHUPS = 5


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def empty_counts() -> dict:
    return {"qc_rows": 0, "nir_missing": 0, "nir_nonfinite": 0,
            "nir_valid": 0, "above": {str(t): 0 for t in THRESHOLDS}}


def add_counts(counts: dict, value: str) -> float | None:
    counts["qc_rows"] += 1
    if not value:
        counts["nir_missing"] += 1
        return None
    try:
        x = float(value)
    except ValueError:
        counts["nir_nonfinite"] += 1
        return None
    if not math.isfinite(x):
        counts["nir_nonfinite"] += 1
        return None
    counts["nir_valid"] += 1
    for t in THRESHOLDS:
        counts["above"][str(t)] += x > t
    return x


def audit(source: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    overall = empty_counts()
    by_sensor = collections.defaultdict(empty_counts)
    by_source = collections.defaultdict(empty_counts)
    sites = collections.defaultdict(lambda: [0, 0])
    owners = collections.defaultdict(set)
    all_rows = qc_true = chla_rows = 0
    with gzip.open(source, "rt", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"site_id", "source", "sensor", "passed_qc", "chla_value"} | set(NIR.values())
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Missing required columns")
        for row in reader:
            all_rows += 1
            sensor, src, site = row["sensor"], row["source"], row["site_id"]
            if sensor not in NIR or not src or not site:
                raise ValueError(f"Invalid sensor/source/site at row {all_rows + 1}")
            owners[site].add(src)
            chla = bool(row["chla_value"])
            chla_rows += chla
            qc = row["passed_qc"]
            if qc not in ("True", "False"):
                raise ValueError(f"Invalid QC flag at row {all_rows + 1}")
            if qc != "True":
                continue
            qc_true += 1
            value = row[NIR[sensor]]
            x = add_counts(overall, value)
            add_counts(by_sensor[sensor], value)
            add_counts(by_source[src], value)
            if chla and x is not None and src in MAIN_SOURCES:
                pair = sites[(src, site)]
                pair[0] += 1
                pair[1] += x > 0.30
    if overall["qc_rows"] != qc_true or sum(v["qc_rows"] for v in by_sensor.values()) != qc_true:
        raise AssertionError("QC count reconciliation failed")
    if any(c["qc_rows"] != c["nir_missing"] + c["nir_nonfinite"] + c["nir_valid"]
           for c in [overall, *by_sensor.values(), *by_source.values()]):
        raise AssertionError("NIR count reconciliation failed")

    selected = {src: [] for src in MAIN_SOURCES}
    for (src, site), (n, high) in sites.items():
        if n >= MIN_SITE_MATCHUPS and len(owners[site]) == 1:
            selected[src].append((site, n, high))
    for src in MAIN_SOURCES:
        selected[src].sort()
    out_csv = output / "site_highnir_source.csv"
    with out_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("unit_id", "group", "value", "n_matchups", "high_nir_matchups"))
        for src in MAIN_SOURCES:
            for site, n, high in selected[src]:
                writer.writerow((src + ":" + site, src, format(high / n, ".17g"), n, high))

    registry = {
        "id": "AQ001", "analysis_intent": "exploratory_descriptive",
        "dataset": "AquaCorr-Global v1", "doi": "10.5281/zenodo.21927415",
        "license": "CC-BY-4.0", "raw_file": str(source),
        "raw_sha256": digest(source), "derived_csv": str(out_csv),
        "derived_sha256": digest(out_csv),
        "prior_exposure": "Before this protocol, a few rows and source-level counts were inspected; this is not blind preregistration.",
        "definitions": {
            "native_nir_band_by_sensor": NIR, "thresholds_sr_inverse": THRESHOLDS,
            "high_nir": "NIR Rrs > 0.30 sr^-1; descriptive screening flag, not an error label",
            "selected_site": "Only nonempty-chla, passed_qc, finite-native-NIR matchups; >=5 per site; one source per site ID",
            "main_groups": MAIN_SOURCES,
        },
        "all_rows": all_rows, "qc_true_rows": qc_true, "chla_nonempty_rows": chla_rows,
        "overall_qc": overall, "by_sensor_qc": dict(sorted(by_sensor.items())),
        "by_source_qc": dict(sorted(by_source.items())),
        "selected_sites": {src: {"sites": len(items), "matchups": sum(n for _, n, _ in items),
                                 "high_nir_matchups": sum(high for _, _, high in items)}
                           for src, items in selected.items()},
        "limitations": [
            "High NIR does not establish the pixel's physical surface or the mechanism of the signal.",
            "Native NIR central wavelengths differ across sensors.",
            "Source groups differ in geography, time, field methods and waterbody composition; no causal comparison.",
            "Multiple matchups at a site are correlated; site is the aggregate unit for source comparison.",
            "The selected site comparison is restricted to two sources and excludes multi-source site IDs.",
        ],
    }
    (output / "descriptive_results.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    return registry


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.source, args.output)
    print(json.dumps({k: result[k] for k in ("all_rows", "qc_true_rows", "chla_nonempty_rows", "selected_sites")}, indent=2))
