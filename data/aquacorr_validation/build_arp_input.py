"""Build the paired, waterbody-clustered ARP input from the validated pair table."""

import csv
import io
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

with zipfile.ZipFile(HERE / "GLORIA-2022.zip") as archive:
    with archive.open("GLORIA_2022/GLORIA_meta_and_lab.csv") as raw:
        meta = {row["GLORIA_ID"]: row for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))}

with (HERE / "gloria_nir_pairs.csv").open(newline="") as raw:
    pairs = [row for row in csv.DictReader(raw) if row["primary_eligible"] == "True"]

out = HERE / "primary_pairs_for_arp.csv"
with out.open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=["pair_id", "waterbody_id", "satellite_nir", "field_nir"])
    writer.writeheader()
    for row in pairs:
        info = meta[row["gloria_id"]]
        country, site = info["Country"].strip(), info["Site_name"].strip()
        if not country or not site:
            raise ValueError(f"Missing waterbody label for {row['gloria_id']}")
        writer.writerow({"pair_id": row["matchup_id"], "waterbody_id": f"{country}|{site}",
                         "satellite_nir": row["satellite_nir"], "field_nir": row["field_nir"]})
print(f"Wrote {len(pairs)} pairs to {out}")
