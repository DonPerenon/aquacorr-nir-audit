"""Verify published GLORIA derivative files and recompute the paired statistic."""

import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from arp.compute_gloria import analyze


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data/aquacorr_validation"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
    for name, expected in manifest["files"].items():
        path = ROOT / name
        assert path.is_file() and digest(path) == expected, f"Manifest mismatch: {name}"

    field_registry = json.loads((DATA / "gloria_nir_registry.json").read_text())
    diagnostics = json.loads((DATA / "additional_diagnostics_registry.json").read_text())
    assert digest(DATA / "gloria_nir_pairs.csv") == field_registry["derived_csv_sha256"] == diagnostics["pair_csv_sha256"]
    assert digest(DATA / "primary_pairs_for_arp.csv") == diagnostics["arp_input_sha256"]
    with (DATA / "gloria_nir_pairs.csv").open(newline="") as stream:
        pairs = list(csv.DictReader(stream))
    assert len(pairs) == diagnostics["all_gloria_matchups"] == 1535
    primary = [row for row in pairs if row["primary_eligible"] == "True"]
    high = [row for row in primary if float(row["satellite_nir"]) > 0.30]
    assert len(primary) == diagnostics["primary_pairs"] == 348
    assert len(high) == field_registry["counts_and_results"]["primary"]["ALL"]["satellite_nir_gt_0_30"] == 8
    assert all(float(row["field_nir"]) <= 0.30 for row in high)
    flow = Counter(row["exclusion_reason"] or "eligible" for row in pairs)
    for reason, count in flow.items():
        assert count == diagnostics["screening_first_reason"][reason]["matchups"]

    result = json.loads((ROOT / "results/GLORIA_R001_public.json").read_text())[0]
    assert digest(ROOT / result["dataset_provenance"]["path"]) == result["data_sha256"]
    assert digest(ROOT / "arp/compute_gloria.py") == result["code_sha256"]
    recomputed = analyze(ROOT / result["dataset_provenance"]["path"], result["parameters"])
    assert recomputed["numbers"] == result["numbers"], "GLORIA R001 numerical mismatch"
    assert result["numbers"]["n_pairs"] == len(primary)
    with (DATA / "primary_pairs_for_arp.csv").open(newline="") as stream:
        assert result["numbers"]["n_clusters"] == len({row["waterbody_id"] for row in csv.DictReader(stream)})

    pilot = json.loads((DATA / "scene_pilot_qa_registry.json").read_text())
    selection = json.loads((DATA / "scene_pilot_selection.json").read_text())
    assert len(selection["pairs"]) == 30 and len(pilot["checks"]) == 60
    assert {(record["pair_index"], record["label"]) for record in pilot["checks"]} == {
        (index, label) for index in range(30) for label in ("high", "low")}
    for record in pilot["checks"]:
        selected = selection["pairs"][record["pair_index"]][record["label"]]
        assert record["matchup_id"] == selected["matchup_id"]
    distances = json.loads((DATA / "scene_pilot_distance_registry.json").read_text())
    assert distances["selection_sha256"] == digest(DATA / "scene_pilot_selection.json")
    assert distances["n_pairs"] == len(selection["pairs"])
    computed_distances = []
    for pair in selection["pairs"]:
        first, second = pair["high"], pair["low"]
        lat1, lon1 = math.radians(float(first["lat"])), math.radians(float(first["lon"]))
        lat2, lon2 = math.radians(float(second["lat"])), math.radians(float(second["lon"]))
        a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        computed_distances.append(6371 * 2 * math.asin(min(1, math.sqrt(a))))
    assert statistics.median(computed_distances) == distances["median_distance_km"]
    assert sum(value > 10 for value in computed_distances) == distances["pairs_more_than_10_km"]
    coverage = json.loads((DATA / "field_coverage_registry.json").read_text())
    assert coverage["pair_csv_sha256"] == digest(DATA / "gloria_nir_pairs.csv")
    assert coverage["matchups"] == diagnostics["screening_first_reason"]["missing_field_nir"]["matchups"]
    assert sum(coverage["last_finite_wavelength_categories"].values()) == diagnostics["screening_first_reason"]["missing_field_nir"]["matchups"]
    assert sum(coverage["high_satellite_nir_gt_0_30_categories"].values()) == diagnostics["screening_first_reason"]["missing_field_nir"]["satellite_nir_gt_0_30"]
    print(json.dumps({"manifest_files_verified": len(manifest["files"]),
                      "gloria_pairs": len(primary), "gloria_high_pairs": len(high),
                      "r001_exact_numbers": True, "pilot_points": len(pilot["checks"]),
                      "pilot_median_distance_km": statistics.median(computed_distances),
                      "missing_field_nir": coverage["matchups"],
                      "note": "This verifies published derivatives and same-input computation, not original-scene interpretation or a new field experiment."}, indent=2))


if __name__ == "__main__":
    main()
