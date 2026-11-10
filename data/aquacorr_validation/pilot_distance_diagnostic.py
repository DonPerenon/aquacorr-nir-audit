"""Post-review distance diagnostic for selected same-scene pilot controls."""

import hashlib
import json
import math
import statistics
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "scene_pilot_selection.json"


def great_circle_km(first, second):
    lat1, lon1 = math.radians(float(first["lat"])), math.radians(float(first["lon"]))
    lat2, lon2 = math.radians(float(second["lat"])), math.radians(float(second["lon"]))
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(value)))


def main():
    selection = json.loads(SOURCE.read_text())
    pairs = [{"sensor": pair["sensor"], "high_matchup_id": pair["high"]["matchup_id"],
              "low_matchup_id": pair["low"]["matchup_id"],
              "great_circle_distance_km": great_circle_km(pair["high"], pair["low"])}
             for pair in selection["pairs"]]
    distances = [pair["great_circle_distance_km"] for pair in pairs]
    result = {"status": "Post hoc descriptive diagnostic requested by second fresh-context reviewer",
              "selection_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "distance_method": "haversine great-circle distance; Earth radius 6371 km",
              "n_pairs": len(pairs), "median_distance_km": statistics.median(distances),
              "pairs_more_than_10_km": sum(distance > 10 for distance in distances),
              "pair_distances": pairs,
              "limitation": "Same-scene controls are often distant and are not local spatial controls; the selected pilot cannot estimate an archive-wide error rate."}
    (HERE / "scene_pilot_distance_registry.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({key: result[key] for key in ("n_pairs", "median_distance_km", "pairs_more_than_10_km")}, indent=2))


if __name__ == "__main__":
    main()
