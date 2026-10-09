> **Remodel counts below are superseded** by `reports/remodels-2026-10-09.md`: repair, signage and demolition-only remodels are now excluded as non-projects, `remodel_subtype` was added, and permit-system tags such as `(MAIN)` are stripped from organization names.

# Default set (new build, shell, addition) vs remodels (2026-10-09)

`project_type` is on permit, Plan Review and site plan candidates. Default set = passed the filter and project_type in (new_build, shell, addition). Used for the pipeline, reports, open-pipeline CSVs, label sheets and enrichment targets. Remodels are in a separate report section and separate CSVs, never in the headline numbers. No raw data was removed.
Mapping: New = new_build, Shell = shell, Addition and Addition and Remodel = addition, Remodel = remodel; a project with several types takes new_build > shell > addition > remodel. Site plans have no work class: type comes from the linked permit project, else a Plan Review application at the same address, else a name/work hint (remodel, tenant improvement, change of use), else `unknown`. Unknown-type site plans with nothing linked stay in the default set and are counted separately.

## Headline (default set), size bands are unknown / under_250k / 250k_to_5m / over_5m
| source | headline | by type | bands | remodels (separate) |
|---|---|---|---|---|
| Issued permit projects, last 12 months | **219** | new_build 145, addition 39, shell 35 | 69 / 45 / 61 / 44 | 2,047 (2,042 unknown size) |
| Issued permit projects, 5 years | 1,170 | | 287 / 172 / 371 / 340 | 10,182 |
| Site plan cases, 5 years | **978** (163 in 12 months, 3.1/wk; 19 in last 28 days) | new_build 383, shell 56, addition 18, unknown type 521 | 631 / 51 / 155 / 141 | 55 |
| Site plan open pipeline | **279** | | 248 / 3 / 18 / 10 | 26 |
| Plan Review, 5 years | **915** | new_build 625, addition 166, shell 124 | 237 / 156 / 314 / 208 | 10,184 |
| Plan Review, last 12 months | 184 (3.5/wk; 10 in last 28 days) | | 51 / 34 / 71 / 28 | 2,163 |
| Plan Review open pipeline | **92** ($2.27B declared) | | 32 / 9 / 34 / 17 | 247 (all unknown size) |

## Change from the previous (remodels-included) numbers
| set | before | after |
|---|---|---|
| Permit projects, 12 months | 2,266 | 219 |
| Site plan cases | 1,033 | 978 (55 moved to remodel) |
| Site plan open pipeline | 305 | 279 |
| Plan Review, 5 years | 11,099 | 915 |
| Plan Review open pipeline | 339 | 92 |

## Other default-set metrics
Site plans linked to a permit: 315 of 978 (32%); lead time median 499 days (p25 346, p75 658). Plan Review linked: 721 of 915 (79%); lead time median 182 days (p25 91, p75 340); by band: over_5m 238 d, 250k_to_5m 172 d, under_250k 110 d, unknown 206 d.

## Label sheets (regenerated)
30 projects total from the default set only, 10 per stage, spread across size bands by quota (3 unknown, 2 under_250k, 3 250k_to_5m, 2 over_5m per stage). Remodels are never sampled, so no unknown-size remodels. Stages: site plan open and Plan Review open are in `reports/manual-labels-site-plans.csv` (20 rows); permit issued (last 12 months) is in `reports/manual-labels-austin.csv` (10 rows). Import: `python -m src.baseline import-labels reports/manual-labels-austin.csv` and `python -m src.phase2 import-labels reports/manual-labels-site-plans.csv`.

## Enrichment (M4): built, dry run only, NOT run
Targets are the default open pipeline: 371 projects (279 site plan, 92 Plan Review). Estimate with assumptions (3 SerpAPI queries per project at $0.01 per call): about $11 for all targets. Hard daily cap is enforced before every call and tested; the cap value in config ($25) is a proposal and not confirmed. See `reports/enrichment-dryrun.md`.
