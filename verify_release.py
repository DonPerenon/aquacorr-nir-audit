"""Check the public release and recompute its registered site-level statistic."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from arp.compute import analyze


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data/aquacorr_global/aquacorr_matchups.csv.gz"
RAW_SHA256 = "ea44b8632ee57b6b214410282fa0ab5b6cc16b5b32477f842349552f1d82877c"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    manifest = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
    for rel, expected in manifest["files"].items():
        path = ROOT / rel
        assert path.is_file() and sha256(path) == expected, rel
    registry = json.loads((ROOT / "results/R001_public.json").read_text())
    assert len(registry) == 1 and registry[0]["id"] == "R001"
    result = registry[0]
    site_csv = ROOT / result["dataset_provenance"]["path"]
    assert sha256(site_csv) == result["data_sha256"]
    assert sha256(ROOT / "arp/compute.py") == result["code_sha256"]
    computed = analyze(site_csv, result["parameters"])
    assert computed["numbers"] == result["numbers"], "R001 numerical mismatch"
    if RAW.is_file():
        assert sha256(RAW) == RAW_SHA256, "Raw archive SHA-256 mismatch"
    print(json.dumps({"release_files_verified": len(manifest["files"]),
                      "r001_exact_numbers": True, "raw_archive_verified": RAW.is_file(),
                      "site_count": computed["numbers"]["n_a"] + computed["numbers"]["n_b"]}, indent=2))


if __name__ == "__main__":
    main()
