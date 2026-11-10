"""Eligibility flow and selected-cohort composition for the AquaCorr audit."""
from __future__ import annotations

import collections
import csv
import gzip
import json
import math
from pathlib import Path

from audit import NIR, MAIN_SOURCES, digest


RAW = Path("data/aquacorr_global/aquacorr_matchups.csv.gz")
DERIVED = Path("data/aquacorr_audit/site_highnir_source.csv")
OUTPUT = Path("data/aquacorr_audit/eligibility_flow.json")


def main() -> None:
    selected = {}
    with DERIVED.open(newline="") as f:
        for row in csv.DictReader(f):
            selected[row["unit_id"]] = (int(row["n_matchups"]), int(row["high_nir_matchups"]))
    steps = collections.defaultdict(lambda: collections.Counter())
    sites = collections.defaultdict(lambda: collections.defaultdict(set))
    ownership = collections.defaultdict(set)
    eligible_site_rows = collections.Counter()
    composition = collections.defaultdict(lambda: {"sensors": collections.Counter(),
                                                "latitude_bands": collections.Counter(),
                                                "hemispheres": collections.Counter(),
                                                "centroid_coordinates": 0,
                                                "matchups": 0, "high_nir_matchups": 0})
    site_observed = collections.defaultdict(lambda: [0, 0])
    with gzip.open(RAW, "rt", newline="") as f:
        for row in csv.DictReader(f):
            src = row["source"]
            site = row["site_id"]
            ownership[site].add(src)
            if src not in MAIN_SOURCES:
                continue
            unit = src + ":" + site
            x = steps[src]
            x["all_source_rows"] += 1
            sites[src]["all_source_rows"].add(site)
            if not row["chla_value"]:
                continue
            x["chla_nonempty"] += 1
            sites[src]["chla_nonempty"].add(site)
            if row["passed_qc"] != "True":
                continue
            x["chla_and_passed_qc"] += 1
            sites[src]["chla_and_passed_qc"].add(site)
            value = row[NIR[row["sensor"]]]
            try:
                nir = float(value)
            except ValueError:
                continue
            if not math.isfinite(nir):
                continue
            x["chla_qc_finite_nir"] += 1
            sites[src]["chla_qc_finite_nir"].add(site)
            eligible_site_rows[(src, site)] += 1
            if unit not in selected:
                continue
            x["selected_matchups"] += 1
            sites[src]["selected_matchups"].add(site)
            c = composition[src]
            c["matchups"] += 1
            c["high_nir_matchups"] += nir > 0.30
            if row["coord_centroid"] not in ("0", "1"):
                raise ValueError(f"Invalid coord_centroid for {unit}")
            c["centroid_coordinates"] += row["coord_centroid"] == "1"
            c["sensors"][row["sensor"]] += 1
            lat = float(row["lat"])
            c["hemispheres"]["north" if lat >= 0 else "south"] += 1
            c["latitude_bands"]["tropical" if abs(lat) < 23.5 else
                                  "midlatitude" if abs(lat) < 45 else "highlatitude"] += 1
            y = site_observed[unit]
            y[0] += 1
            y[1] += nir > 0.30
    if len(site_observed) != len(selected) or any(tuple(site_observed[u]) != selected[u] for u in selected):
        mismatched = [u for u in selected if tuple(site_observed[u]) != selected[u]]
        raise AssertionError(f"Selected-cohort reconciliation failed for {len(mismatched)} units")
    exclusion = collections.defaultdict(lambda: {"multiple_source_site_ids": {"sites": 0, "rows": 0},
                                              "fewer_than_five": {"sites": 0, "rows": 0},
                                              "retained": {"sites": 0, "rows": 0}})
    for (src, site), n in eligible_site_rows.items():
        if len(ownership[site]) > 1:
            category = "multiple_source_site_ids"
        elif n < 5:
            category = "fewer_than_five"
        else:
            category = "retained"
        exclusion[src][category]["sites"] += 1
        exclusion[src][category]["rows"] += n
    for src in MAIN_SOURCES:
        e = exclusion[src]
        if sum(e[k]["sites"] for k in e) != len(sites[src]["chla_qc_finite_nir"]):
            raise AssertionError(f"Site exclusion flow mismatch for {src}")
        if sum(e[k]["rows"] for k in e) != steps[src]["chla_qc_finite_nir"]:
            raise AssertionError(f"Row exclusion flow mismatch for {src}")
        if e["retained"]["sites"] != len(sites[src]["selected_matchups"]) or e["retained"]["rows"] != steps[src]["selected_matchups"]:
            raise AssertionError(f"Retained cohort mismatch for {src}")
    result = {"id": "AQFLOW001", "raw_sha256": digest(RAW),
              "derived_sha256": digest(DERIVED), "script_sha256": digest(Path(__file__)),
              "note": "Counts follow the exact stages used by the derived site-level CSV. After finite NIR, classify multi-source site IDs first, then fewer-than-five eligible matchups, then retained; categories are exclusive.",
              "sources": {src: {"row_flow": dict(steps[src]),
                                "site_flow": {k: len(v) for k, v in sites[src].items()},
                                "post_finite_nir_exclusions": exclusion[src],
                                "selected_composition": {
                                    k: dict(v) if isinstance(v, collections.Counter) else v
                                    for k, v in composition[src].items()}}
                          for src in MAIN_SOURCES}}
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["sources"], indent=2))


if __name__ == "__main__":
    main()
