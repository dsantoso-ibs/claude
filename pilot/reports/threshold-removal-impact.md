# Impact of removing the valuation threshold (2026-10-09)

**Change:** no valuation rule in the filter for permits, site plans or Plan Review (the $250k floor, the `valuation_unreported` reason and the $100k ingest floor are gone). All class, work-class, use and status rules are unchanged. New descriptive field `size_band` (`unknown`, `under_250k`, `250k_to_5m`, `over_5m`) on all three candidate tables; it never includes or excludes anything.

**size_band source, best available valuation:** permit project: own max `total_job_valuation`, else a linked Plan Review application. Plan Review: own valuation, else linked permit project. Site plan: linked permit project, else a Plan Review application at the same address. A reported valuation of $1,000 or less ($0/$1 placeholders) counts as `unknown`. Bands: `under_250k` is above the placeholder and below $250k; `250k_to_5m` is $250k to $5M inclusive; `over_5m` is above $5M. Thresholds are in `config.yaml` (`size_band`).

**Fetch scope changed too**, otherwise the filter would still be blind to small projects: permits and Plan Review are now fetched by class only (commercial `C-` and multi-family `R- 104/105/106/213/214`), all work classes, 5 years. Raw permits 9,300 to 21,014; Plan Review 1,127 to 14,702. Single-family permit classes are no longer fetched, so the `single_family_or_duplex` exclusion count is now near zero for permits and Plan Review (it still applies to site plans).

## Passed counts, before and after
| set | before | after | change |
|---|---|---|---|
| Permit projects passed, last 12 months (phase 1 window) | 100 | **2,266** | x22.7 |
| Permit projects passed, 5 years | 687 | **11,352** | x16.5 |
| Site plan cases passed | 1,033 | **1,033** | none (site plans never had a valuation rule) |
| Plan Review passed, 5 years | 498 | **11,099** | x22.3 |
| Plan Review passed, last 12 months | 92 | **2,347** | x25.5 |

## What the new passes are
Permit projects passed, last 12 months (2,266), by size band and project type:
| | unknown | under_250k | 250k_to_5m | over_5m | total |
|---|---|---|---|---|---|
| new / shell / addition | 69 | 45 | 61 | 44 | **219** |
| remodel only | 2,042 | 1 | 4 | 0 | **2,047** |
| all | 2,111 | 46 | 65 | 44 | 2,266 |
**90% of the increase is remodel-only projects (commercial tenant fit-outs) and 99.8% of those have no usable valuation**, so the band cannot tell them apart. The 219 new/shell/addition projects are the closer comparison to the old 100: 109 of them are at or above $250k by best available valuation (65 + 44), in line with the old 100, plus 45 under $250k and 69 unknown.
Excluded in the 12-month window after the change: structures only 217, work class not construction 285, solar/EV 81, status 24 (before: valuation_unreported 194 and below_valuation 173 were the two largest).

Size bands (unknown / under_250k / 250k_to_5m / over_5m):
| set | total | unknown | under_250k | 250k_to_5m | over_5m |
|---|---|---|---|---|---|
| Permits passed, 12 months | 2,266 | 2,111 | 46 | 65 | 44 |
| Permits passed, 5 years | 11,352 | 10,439 | 179 | 394 | 340 |
| Site plans passed | 1,033 | 681 | 52 | 158 | 142 |
| Site plans passed, 12 months | 176 | 170 | 0 | 4 | 2 |
| Site plan open pipeline | 305 | 271 | 3 | 20 | 11 |
| Plan Review passed, 5 years | 11,099 | 10,345 | 177 | 343 | 234 |
| Plan Review passed, 12 months | 2,347 | 2,212 | 34 | 73 | 28 |
| Plan Review open pipeline | 339 | 279 | 9 | 34 | 17 |

## Other metrics that moved
| metric | before | after |
|---|---|---|
| Site plans linked to a permit | 206 (20%) | 315 (30%) |
| Site plan lead time, median (p25 to p75) | 532 d (385 to 660), n=206 | 499 d (346 to 658), n=315 |
| Site plan open pipeline | 305 | 305 (unchanged) |
| Plan Review linked to a permit | 395 (79%) | 10,217 (92%) |
| Plan Review lead time by band, median | all passed (>= $250k): 213 d | over_5m 218 d; 250k_to_5m 150 d; under_250k 100 d; unknown 40 d |
| Plan Review open pipeline | 47 ($1.26B declared) | 339 ($2.27B; 279 have unknown size) |

## Things to know
1. **The Plan Review lead time is no longer one number.** The unbanded median fell to 43 days only because 9,600 small remodel applications dominate. Quote it by band (over $5M: 218 days, matching the earlier 213).
2. **A linking defect appeared and was fixed.** With far more permits per address, a Plan Review application could link to a neighbouring tenant's permit; the same projects dropped to 82 to 114 days. Links now require the same work class (New to New/Shell, etc.). Test added. Site plan links already required new/shell/addition permits.
3. **Site plan sizes are mostly unknown** (74% of passed; 89% of the open pipeline) because the dataset has no valuation and most open cases have no permit yet. Plan Review at the same address filled 34 of the open cases.
4. **The phase 1 label sheet changed.** `reports/manual-labels-austin.csv` was regenerated from the new 2,266 passed projects and is now mostly remodels with unknown size, which is a poor sample for the novelty test. Nothing had been labelled. Recommend sampling only new/shell/addition projects, or stratifying by band, before anyone labels it. I have not changed this.
5. **Options if the remodel volume is not wanted** (not applied): filter on work-class group in reports (new/shell/addition vs remodel-only), or drop `Remodel` from `include_work_classes` for permits.
