# AquaCorr-Global v1 native NIR audit: code and derived results

This is a public release candidate for an **exploratory, archive-specific numerical audit**. It is not a validated bad-pixel classifier or an independent reprocessing of satellite scenes. The associated manuscript has not been submitted or accepted by a journal.

## Source and attribution

The source is *AquaCorr-Global: A Multi-Sensor, Multi-Decadal Water Quality Matchup Dataset for Inland and Coastal Waters*, version 1, by M. S. Ghazi Zadeh Hashemi and contributors, DOI [10.5281/zenodo.21927415](https://doi.org/10.5281/zenodo.21927415), licensed CC BY 4.0 according to the Zenodo record. The full compressed CSV is distributed by the source archive and is intentionally **not** copied here. The source archive's MD5 for `aquacorr_matchups.csv.gz` is `b26f8acca092110bcd833d0bfedb33c3`; the verified local SHA-256 was `ea44b8632ee57b6b214410282fa0ab5b6cc16b5b32477f842349552f1d82877c`.

The analysis files here are derivatives of that source and retain this attribution. `data/aquacorr_global/aquacorr_metadata.json` and `zenodo_record.json` are copies of publicly provided source metadata. The metadata file contains a placeholder DOI; the Zenodo record DOI above is authoritative.

## Contents

- `data/aquacorr_audit/audit.py`: full-stream descriptive screen and site table.
- `data/aquacorr_audit/flow.py`: eligibility and cohort-composition reconciliation.
- `data/aquacorr_audit/sensitivity.py`: descriptive threshold and same-sensor checks.
- `data/aquacorr_audit/tail_check.py`: post-review exploratory upper-tail diagnostic.
- `data/aquacorr_audit/*.json` and `site_highnir_source.csv`: derived results and one-row-per-site analysis data.
- `arp/compute.py` and `arp/core.py`: exact Python implementation used for the site-level bootstrap/permutation result `R001`.
- `results/R001_public.json`: numerical copy of the original `R001` registry. **Only** its local filesystem path was replaced with the repository-relative site-table path. The original registry SHA-256 is recorded in `results/R001_original_sha256.txt`.
- `verify_release.py`: checks release hashes and recalculates `R001`; with the raw CSV present, also verifies the raw source checksum.

All code uses the Python standard library. The work was developed with substantial AI assistance in study design, scripting, computation, drafting, and audit. A human author must independently review and accept responsibility for any manuscript based on it. The site contrast is observational and source cohorts differ in geography and sensor composition. The bootstrap interval is conditional on the selected sites and does not establish a causal or population effect. Thresholds are screening descriptions, not verified error labels. The upper-tail diagnostic was added after reviewer feedback.

## Reproduction

Use Python 3.11 or later from this directory. Obtain `aquacorr_matchups.csv.gz` and `aquacorr_metadata.json` from the DOI above and put them in `data/aquacorr_global/`. Check the compressed CSV against the source MD5 and the SHA-256 above. The included metadata copy has SHA-256 `c6f038c657ca233beddcd4747dead661861d227129529ba23b743cdd53a1f96b`.

```sh
python3 verify_release.py
python3 data/aquacorr_audit/audit.py --source data/aquacorr_global/aquacorr_matchups.csv.gz --output data/aquacorr_audit
python3 data/aquacorr_audit/flow.py
python3 data/aquacorr_audit/sensitivity.py
python3 data/aquacorr_audit/tail_check.py
python3 verify_release.py
```

The first verification checks the published derived files and recalculates `R001`; the second also verifies the raw archive when present. For a byte-exact check of every derived file, compare the output hashes to `RELEASE_MANIFEST.json`. Re-running scripts may change JSON formatting or script-hash metadata only if the code or Python runtime is altered.

## Rights and reuse

The original dataset is CC BY 4.0. Reuse of derived data and result tables should credit the AquaCorr-Global creators and the DOI above. The scripts are shared for inspection and reproducibility; no separate software license is granted in this candidate package pending the research owner's licensing decision.
