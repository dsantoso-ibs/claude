> **Superseded in part (2026-10-09):** the valuation threshold was removed afterwards. Passed counts, linking and Plan Review lead-time figures below describe the earlier >= $250k version; see `reports/threshold-removal-impact.md` for current numbers.

# Phase 2 analysis: Austin Site Plan Cases + Plan Review Cases (M7.0 to M7.5)
As of 2026-10-09. All numbers come from `reports/phase2-2026-10-09.md`, `reports/open-pipeline-validation.md` and ad-hoc queries noted below. Region: City of Austin permitting jurisdiction only.

## 1. Headline
1. **Lead is large.** Site plan submitted to building permit issued: **median 532 days (about 76 weeks)**, p25 385, p75 660 (n=206 linked cases). Plan Review application to building permit issued: **median 213 days (about 30 weeks)**, p25 100, p75 355 (n=395). Both are measured only on projects that already reached a permit, so they understate the true lead (see section 6).
2. **The open pipeline exists and is validated.** 305 passed site plan cases (open status, submitted in the last 24 months, no permit found) and 47 Plan Review applications ($1.26B declared, not yet issued, no permit). An independent check of 40 random open-pipeline cases against the full Austin permit dataset found **0 missing new-construction permits** (the other 8 had only demolition/remodel/repair permits, which suggests projects already moving).
3. **Contacts are better than at permit stage but still partial.** A business owner entity is named on 53% of open site plan cases, an applicant organization on 73%, either on 87%. Plan Review has an owner on only 21% of open applications.
4. **Phase 1 had a blind spot, now quantified.** Of 228 commercial new/shell/addition projects permitted in the last 12 months, **105 (46%) report a valuation below $100k and 70 report `$0` or `$1`**. The valuation filter cannot see them. The new `valuation_unreported` exclusion reason now makes this visible, but it still needs a decision (section 7).
5. **Novelty is still not measured.** No baseline exists and the 30-project sheet has not been labelled.

## 2. M7.0 to M7.1: data in hand
| dataset | rows loaded | window | idempotent re-run |
|---|---|---|---|
| Site Plan Cases `mavg-96ck` | 2,944 | applications since 2021-10-05 (60 months; spec said 24) | 0 new rows |
| Plan Review Cases `n8ck-xkda` | 1,127 (valuation >= $100k) | applied since 2021-10-05 | 0 new rows |
| Issued permits `3syk-w9eu` | 9,300 (extended from 12 to 60 months, plus commercial new/shell/addition at any valuation) | issued since 2021-10-05 | 0 new rows |
Personal fields (names, phones, street addresses, case managers, appraisal id) are dropped before storage; verified no `*phone*`, `*fullname*`, `*full_name*` keys in stored payloads. Organization fields that look like a person are nulled and flagged `owner_is_individual`.
Why 60 months: a site plan reaches a building permit about 1.5 years later, so 24 months of cases could never show a full lead time. Why more permits: otherwise a 2023 case built in 2024 would look "open".
Note: Plan Review's `permit_number` is not unique in the source (1 duplicate in 1,128 rows), so 1 row was overwritten.

## 3. M7.2: filter results (Site Plan Cases)
2,944 cases: **1,033 passed**, 1,911 excluded: status expired/withdrawn/etc. 1,257; work type not a building project (extension, utility line, boat dock, street, etc.) 483; infrastructure/boat dock use 76; unknown use 76; demolition only 11; single-family/duplex 8.
Passed by use: commercial 561, multi-family 155, public/civic 148, industrial 87, housing (unclear) 82. 47 passed cases look multi-family by name though classed commercial or housing.
Rate: **19 in the last 28 days (4.8 a week); 176 in the last 12 months (3.4 a week).**
Older rows use free-text land use (372 distinct values), so classification is by ordered regex rules in `config.yaml`; the 76 `unknown_use` cases are genuinely unknown ("Unk", "N/A", "PUD", blank).
Plan Review: 1,127 loaded, **498 passed** (>= $250k, construction work class, commercial/multi-family class, live status); 92 in the last 12 months (1.8 a week).
Size hints: not usable for current cases (units last filled 2022, building sq ft 2020, acres on 7 of 1,015 recent cases). Valuation from the linked permit is the only size signal.

## 4. M7.3: linking
- Method: normalized address plus geo within 100 m; permit must be issued on or after the case date; site plans link only to new/shell/addition permits (an interior remodel is not what a site plan produces). Owner/applicant vs contractor name is a supporting signal only (+0.10, 4 cases used it).
- Site plans: **206 of 1,033 passed cases linked (20%)** at score >= 0.85, plus **187 in the review bucket** (0.60 to 0.85, not yet inspected). Among approved/closed cases 25% linked. All 206 links are exact-address (202) or exact-address plus name (4).
- By submission year (linked): 2021 33%, 2022 27%, 2023 26%, 2024 21%, 2025 15%, 2026 1%. The decline is mostly time, not quality: recent cohorts have not had time to reach a permit.
- Plan Review: **395 of 498 (79%)** linked.
- Two linking defects were found and fixed during this work: a fuzzy address match (`301 W 14TH ST` vs `301 W 5TH ST`) and remodel permits being used as link targets.

## 5. M7.4: metrics
| metric | site plans | plan review |
|---|---|---|
| passed per week (last 28 d / 12 m) | 4.8 / 3.4 | 1.8 / 1.8 |
| share linked to a permit | 20% | 79% |
| lead time median (p25, p75) days | 532 (385, 660), n=206 | 213 (100, 355), n=395 |
| lead time status | not provisional (n >= 30) | not provisional |
| open pipeline | 305 cases | 47 applications, $1.26B |
| owner entity / applicant org on open pipeline | 53% / 73% | 21% / 68% |

Lead time by group (site plans): multi-family median 542 d (n=49); commercial 544 d (n=95); industrial, public/civic and housing 458 d (n=62).
Open pipeline by status: Approved and Released 110, Awaiting Update 66, In Review 45, CC Approved 23, Waiting on Legal 16, Intake Pending 13, CC Pending 13. By use: commercial 226, public/civic 42, housing 27, industrial 10. Median age since submission 318 days.
Stage progression: **31 of the 47 open Plan Review applications already had a passed site plan at the same address**, so the two sources show the same projects at successive stages.
Frequent applicants (engineering/permit firms, not owners) in the open pipeline: Kimley-Horn 18, GarzaEMC 9, LJA 6, 360 Professional Services 6, Sandlin Services 6, Bleyl 6. Public owners (City of Austin, Round Rock ISD, AISD) are common among named owners.

## 6. Validity and caveats
- **Right-censoring.** Lead time exists only for cases that reached a permit. Medians by year (2021: 510 d, 2022: 578, 2023: 534, 2024: 501, 2025: 428) fall for recent years because only fast cases have finished. The real median for all cases is longer. 14 of 206 leads exceed 3 years (site plans normally expire after 3 years), so a few links may be a later unrelated permit at the same address.
- **Open pipeline validation:** 40 random open cases submitted before 2026-04, checked against the full permit dataset by address with no valuation floor: 32 no building permit found, 8 only demolition/remodel/repair, **0 missed new-construction permits**. An earlier version of the pipeline missed 6 of 40 because of the valuation floor; that was fixed by ingesting commercial new/shell/addition permits at any valuation. This is a check of the pipeline's internal consistency; it does not prove that cases are good sales opportunities.
- **Unexplained:** Plan Review's own applied-to-issued median is 442 days, longer than application to building-permit issue (213 days). Its `issued_date` probably means something other than "review finished". Do not quote the 442 figure as a review duration.
- **Hand checks are not independent.** I reviewed 20 passed and 20 excluded site plan cases and about 12 linked pairs while tuning, and changed rules after (demolition-only names, link targets). Someone else should do the checks in `reports/handcheck-site-plans.csv` and `reports/handcheck-site-plan-links.csv` (20 linked pairs and 10 unlinked cases).
- `Housing` cannot separate single-family from multi-family; all 82 `housing_unclear` cases pass, flagged by name where possible. Some applicant fields contain system tags such as "(MAIN)" or "**MAIN**".
- Plan Review has a $1B industrial application (475 Patton Ave) earlier seen with `$1` on its building permits; large declared valuations are unverified.
- The 100 phase 1 permit projects in the 12-month window replaced the earlier 106 because the window is now defined by a project's first issue date, not by whichever permit was fetched.

## 7. Decisions needed
1. **Unreported valuations.** Add a class-based route for commercial new/shell/addition projects with `$0`/`$1` valuation (about 70 a year), e.g. take valuation from Plan Review when available, or pass them with a `valuation_unknown` flag. Today they are excluded as `valuation_unreported`.
2. **Who labels** the 30 open-pipeline site plan cases (`reports/manual-labels-site-plans.csv`, 10 multi-family, 10 commercial, 10 other) and the 40 permit projects (`reports/manual-labels-austin.csv`). Until then novel share is unmeasured and the continue/stop verdict cannot be given.
3. **Independent hand checks** (two sheets above).
4. Whether the open pipeline should treat design/permit firms (Kimley-Horn, etc.) as contacts or only owner entities.
5. Still pending from the addendum, not started: TABS access research (section 7) and zoning freshness check (section 8).

## 8. Files
`reports/phase2-2026-10-09.md` (metrics) | `open-pipeline-site-plans.csv` (305) | `open-pipeline-plan-review.csv` (47) | `open-pipeline-validation.md` | `manual-labels-site-plans.csv` | `handcheck-site-plans.csv` | `handcheck-site-plan-links.csv` | code: `src/phase2_ingest.py`, `phase2.py`, `report_phase2.py`, `validate_pipeline.py`, `entities.py` | 20 tests.
