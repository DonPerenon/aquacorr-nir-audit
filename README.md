# AquaCorr-Global v1 native NIR audit and GLORIA follow-up

This is a public release for an **exploratory, archive-specific numerical audit** and a selected field-spectrum and scene-QA follow-up. It is not a validated bad-pixel classifier or an independent reprocessing of satellite scenes. The initial follow-up manuscript received major comments in fresh-context AI review; the corrected research report is a working document and has not been approved for journal submission.

## Source and attribution

The source is *AquaCorr-Global: A Multi-Sensor, Multi-Decadal Water Quality Matchup Dataset for Inland and Coastal Waters*, version 1, by M. S. Ghazi Zadeh Hashemi and contributors, DOI [10.5281/zenodo.21927415](https://doi.org/10.5281/zenodo.21927415), licensed CC BY 4.0 according to the Zenodo record. The full compressed CSV is distributed by the source archive and is intentionally **not** copied here. The source archive's MD5 for `aquacorr_matchups.csv.gz` is `b26f8acca092110bcd833d0bfedb33c3`; the verified local SHA-256 was `ea44b8632ee57b6b214410282fa0ab5b6cc16b5b32477f842349552f1d82877c`.

The analysis files here are derivatives of that source and retain this attribution. `data/aquacorr_global/aquacorr_metadata.json` and `zenodo_record.json` are copies of publicly provided source metadata. The metadata file contains a placeholder DOI; the Zenodo record DOI above is authoritative.

The follow-up also uses the original GLORIA hyperspectral field dataset by Lehmann and collaborators, DOI [10.1594/PANGAEA.948492](https://doi.org/10.1594/PANGAEA.948492), licensed CC BY 4.0. GLORIA is an instrument-independent field source, but it is **not an untouched holdout**: the AquaCorr publisher already used GLORIA in visible-band validation. The original GLORIA ZIP and sensor response files are not copied into this repository; their sources and hashes are recorded in `data/aquacorr_validation/gloria_nir_registry.json`.

## Contents

- `data/aquacorr_audit/audit.py`: full-stream descriptive screen and site table.
- `data/aquacorr_audit/flow.py`: eligibility and cohort-composition reconciliation.
- `data/aquacorr_audit/sensitivity.py`: descriptive threshold and same-sensor checks.
- `data/aquacorr_audit/tail_check.py`: post-review exploratory upper-tail diagnostic.
- `data/aquacorr_audit/*.json` and `site_highnir_source.csv`: derived results, the full original calculation manifest and saved same-input reproduction output, and one-row-per-site analysis data. The original manifest also names local run files that are not part of this minimal public repository.
- `arp/compute.py` and `arp/core.py`: exact Python implementation used for the site-level bootstrap/permutation result `R001`.
- `results/R001_public.json`: numerical copy of the original `R001` registry. **Only** its local filesystem path was replaced with the repository-relative site-table path. The original registry SHA-256 is recorded in `results/R001_original_sha256.txt`.
- `verify_release.py`: checks release hashes and recalculates `R001`; with the raw CSV present, also verifies the raw source checksum.
- `docs/AQUACORR_GLORIA_VALIDATION_REPORT_2026-11-10.md`: full working report, screening flow, field comparison, scene-QA pilot, reviewer response and remaining limitations.
- `data/aquacorr_validation/*.py`: field-spectrum join and response integration, scene/tile QA lookups, fixed pilot selection and post-review diagnostics, including spectral-coverage and control-distance audits.
- `data/aquacorr_validation/*.csv` and `*.json`: derived GLORIA pair table, selected analysis pairs, per-waterbody biases, source/result registries, selected pilot rows and raw QA-query results. The original source archives are not included.
- `arp/compute_gloria.py` and `results/GLORIA_R001_public.json`: the exact code bytes and public copy of the paired waterbody statistic from the blocked ARP follow-up run. The public copy only changes its source CSV path to a repository-relative path.
- `results/GLORIA_INDEPENDENT_REVIEW.json`, `results/GLORIA_SECOND_INDEPENDENT_REVIEW.json`, and `results/AQUACORR_V5_INDEPENDENT_REVIEW.json`: fresh-context AI reviews of the first follow-up draft, expanded report, and integrated working manuscript. The initial major reporting concerns were addressed; the later reviewers found no major concern while stating the limits of their checks. The integrated manuscript itself is not published here and awaits author approval.
- `verify_gloria_release.py`: verifies release hashes, the GLORIA source-to-analysis flow, pilot row identity, and exactly recomputes the paired statistic from the published derivative table.

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
python3 verify_gloria_release.py
```

`verify_release.py` checks the original audit's published derivatives and recalculates its `R001`; with the raw CSV present, it also checks that archive's hash. `verify_gloria_release.py` checks the follow-up derivatives and recalculates its paired statistic. Both check the fixed file hashes in `RELEASE_MANIFEST.json`. Re-running scripts may change JSON formatting or script-hash metadata if code or Python changes.

The GLORIA verifier works from the included derivatives alone. To regenerate those derivatives from source, download the AquaCorr CSV above, the original [GLORIA ZIP](https://doi.org/10.1594/PANGAEA.948492), the official [Sentinel-2 response v4 and v5 workbooks](https://sentiwiki.copernicus.eu/web/s2-documents), and the [Landsat 7](https://nwp-saf.eumetsat.int/downloads/rtcoef_info/visir_srf/rtcoef_landsat_7_tm_srf.html) and [Landsat 8](https://nwp-saf.eumetsat.int/downloads/rtcoef_info/visir_srf/rtcoef_landsat_8_oli_srf.html) response archives. Put them under `data/aquacorr_validation/` with the filenames specified in `validate_gloria.py`, verify hashes against `gloria_nir_registry.json`, then run `validate_gloria.py`, `build_arp_input.py`, and `additional_diagnostics.py` in that order. `scene_audit.py` and `audit_scene_pilot.py` query public external STAC and point APIs, whose products may change; their saved responses and URLs are in the registries. The full archive scan for `select_scene_pilot.py` requires the AquaCorr CSV at `data/aquacorr_global/aquacorr_matchups.csv.gz`.

## Rights and reuse

The original dataset is CC BY 4.0. Reuse of derived data and result tables should credit the AquaCorr-Global creators and the DOI above. The scripts are shared for inspection and reproducibility; no separate software license is granted in this release pending the research owner's licensing decision.
