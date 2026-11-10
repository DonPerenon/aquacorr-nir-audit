"""Threshold and same-sensor sensitivity of the AquaCorr site comparison."""
from __future__ import annotations

import collections
import csv
import gzip
import json
import math
from pathlib import Path

from audit import NIR, THRESHOLDS, MAIN_SOURCES, MIN_SITE_MATCHUPS, digest


RAW = Path("data/aquacorr_global/aquacorr_matchups.csv.gz")
OUT = Path("data/aquacorr_audit/sensitivity_results.json")


def main() -> None:
    ownership = collections.defaultdict(set)
    totals = collections.defaultdict(lambda: [0] * (1 + len(THRESHOLDS)))
    with gzip.open(RAW, "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            site, src, sensor = row["site_id"], row["source"], row["sensor"]
            ownership[site].add(src)
            if src not in MAIN_SOURCES or row["passed_qc"] != "True" or not row["chla_value"]:
                continue
            value = row[NIR[sensor]]
            if not value:
                continue
            x = float(value)
            if not math.isfinite(x):
                continue
            for scope in ("ALL", sensor):
                count = totals[(scope, src, site)]
                count[0] += 1
                for j, threshold in enumerate(THRESHOLDS, 1):
                    count[j] += x > threshold
    result = {"raw_sha256": digest(RAW), "script_sha256": digest(Path(__file__)),
              "rule": "Exclusive source per site; >=5 eligible matchups per site within each scope; means of site proportions",
              "thresholds_sr_inverse": THRESHOLDS, "scopes": {}}
    for scope in ("ALL", *NIR):
        groups = {}
        for src in MAIN_SOURCES:
            eligible = [counts for (sc, group, site), counts in totals.items()
                        if sc == scope and group == src and len(ownership[site]) == 1
                        and counts[0] >= MIN_SITE_MATCHUPS]
            groups[src] = {"sites": len(eligible), "matchups": sum(c[0] for c in eligible),
                           "mean_site_fraction": {
                               str(threshold): (sum(c[j] / c[0] for c in eligible) / len(eligible)
                                                if eligible else None)
                               for j, threshold in enumerate(THRESHOLDS, 1)}}
        result["scopes"][scope] = groups
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["scopes"]["ALL"], indent=2))


if __name__ == "__main__":
    main()
