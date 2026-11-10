"""Reviewer-requested post hoc screening and waterbody influence summaries."""

import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

with (HERE / "gloria_nir_pairs.csv").open(newline="") as stream:
    rows = list(csv.DictReader(stream))
with (HERE / "primary_pairs_for_arp.csv").open(newline="") as stream:
    pairs = list(csv.DictReader(stream))

if len(rows) != 1535 or len(pairs) != 348:
    raise AssertionError("Source or primary-pair count changed")

def stat(values):
    return statistics.mean(values) if values else None

flow = {}
for reason, group in sorted({reason: [r for r in rows if (r["exclusion_reason"] or "eligible") == reason]
                              for reason in {r["exclusion_reason"] or "eligible" for r in rows}}.items()):
    flow[reason] = {"matchups": len(group), "satellite_nir_gt_0_30": sum(bool(r["satellite_nir"]) and float(r["satellite_nir"]) > 0.30 for r in group),
                    "by_sensor": dict(Counter(r["sensor"] for r in group))}

clusters = defaultdict(list)
for row in pairs:
    clusters[row["waterbody_id"]].append({"pair_id": row["pair_id"],
        "bias": float(row["satellite_nir"]) - float(row["field_nir"]),
        "high": float(row["satellite_nir"]) > 0.30})
cluster_summary = []
for cluster, values in clusters.items():
    diffs = [v["bias"] for v in values]
    cluster_summary.append({"waterbody_id": cluster, "n_pairs": len(values),
                            "n_high_satellite_nir": sum(v["high"] for v in values),
                            "mean_signed_bias": statistics.mean(diffs),
                            "median_signed_bias": statistics.median(diffs)})
cluster_summary.sort(key=lambda r: r["mean_signed_bias"], reverse=True)
means = [r["mean_signed_bias"] for r in cluster_summary]
overall = statistics.mean(means)
leave_one_out = [{"waterbody_id": r["waterbody_id"],
                  "mean_without_waterbody": (sum(means) - r["mean_signed_bias"]) / (len(means) - 1)}
                 for r in cluster_summary]
without_high = []
for cluster, values in clusters.items():
    remaining = [v["bias"] for v in values if not v["high"]]
    if remaining:
        without_high.append(statistics.mean(remaining))

result = {
    "status": "Post hoc diagnostics requested by fresh-context reviewer; not in the initial local analysis plan",
    "pair_csv_sha256": hashlib.sha256((HERE / "gloria_nir_pairs.csv").read_bytes()).hexdigest(),
    "arp_input_sha256": hashlib.sha256((HERE / "primary_pairs_for_arp.csv").read_bytes()).hexdigest(),
    "screening_first_reason": flow,
    "all_gloria_matchups": len(rows),
    "all_gloria_high_satellite_nir": sum(bool(r["satellite_nir"]) and float(r["satellite_nir"]) > 0.30 for r in rows),
    "primary_pairs": len(pairs), "primary_waterbodies": len(clusters),
    "waterbody_bias_mean": overall,
    "waterbody_bias_median": statistics.median(means),
    "waterbody_bias_min": min(means), "waterbody_bias_max": max(means),
    "positive_bias_waterbodies": sum(value > 0 for value in means),
    "waterbody_results": cluster_summary,
    "leave_one_waterbody_out": leave_one_out,
    "leave_one_out_mean_range": [min(r["mean_without_waterbody"] for r in leave_one_out), max(r["mean_without_waterbody"] for r in leave_one_out)],
    "mean_waterbody_bias_after_removing_high_satellite_pairs": stat(without_high),
    "waterbodies_after_removing_high_satellite_pairs": len(without_high),
    "limitation": "Waterbody labels are country plus site name; equal-waterbody weighting and leave-one-out are descriptive. The high-pair removal is data-dependent sensitivity analysis."
}
(HERE / "additional_diagnostics_registry.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
with (HERE / "waterbody_bias.csv").open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(cluster_summary[0]))
    writer.writeheader()
    writer.writerows(cluster_summary)
print(json.dumps({k: result[k] for k in ("screening_first_reason", "waterbody_bias_mean", "waterbody_bias_median", "waterbody_bias_min", "waterbody_bias_max", "positive_bias_waterbodies", "leave_one_out_mean_range", "mean_waterbody_bias_after_removing_high_satellite_pairs")}, indent=2))
