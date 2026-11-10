"""Classify wavelength coverage among GLORIA pairs missing field-band NIR."""

import csv
import hashlib
import io
import json
import math
import zipfile
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
PAIR_CSV = HERE / "gloria_nir_pairs.csv"
GLORIA_ZIP = HERE / "GLORIA-2022.zip"


def coverage_category(spectrum):
    if spectrum is None:
        return "spectrum_id_absent"
    finite = []
    for nm in range(350, 901):
        try:
            value = float(spectrum.get(f"Rrs_{nm}", "nan"))
        except ValueError:
            continue
        if math.isfinite(value):
            finite.append(nm)
    if not finite:
        return "no_finite_spectrum"
    maximum = max(finite)
    if maximum < 800:
        return "last_finite_below_800_nm"
    if maximum < 850:
        return "last_finite_800_to_849_nm"
    if maximum < 900:
        return "last_finite_850_to_899_nm"
    return "finite_at_900_but_missing_in_band"


def main():
    with PAIR_CSV.open(newline="") as stream:
        missing = [row for row in csv.DictReader(stream) if row["exclusion_reason"] == "missing_field_nir"]
    identifiers = {row["gloria_id"] for row in missing}
    with zipfile.ZipFile(GLORIA_ZIP) as archive:
        with archive.open("GLORIA_2022/GLORIA_Rrs.csv") as raw:
            spectra = {row["GLORIA_ID"]: row for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))
                       if row["GLORIA_ID"] in identifiers}
    counts, high_counts = Counter(), Counter()
    for row in missing:
        category = coverage_category(spectra.get(row["gloria_id"]))
        counts[category] += 1
        if float(row["satellite_nir"]) > 0.30:
            high_counts[category] += 1
    registry = {"status": "Post hoc diagnostic requested by integrated-manuscript fresh-context reviewer",
                "pair_csv_sha256": hashlib.sha256(PAIR_CSV.read_bytes()).hexdigest(),
                "gloria_zip_sha256": hashlib.sha256(GLORIA_ZIP.read_bytes()).hexdigest(),
                "unit": "AquaCorr matchup row, not distinct GLORIA field spectrum",
                "first_exclusion_reason": "missing_field_nir",
                "matchups": len(missing), "distinct_gloria_ids": len(identifiers),
                "last_finite_wavelength_categories": dict(counts),
                "high_satellite_nir_gt_0_30_categories": dict(high_counts),
                "limitation": "This describes the maximum finite wavelength in the original GLORIA spectrum. Field-band availability also depends on sensor response weights; the first-reason screen can conceal other simultaneous exclusions."}
    (HERE / "field_coverage_registry.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(registry, indent=2))


if __name__ == "__main__":
    main()
