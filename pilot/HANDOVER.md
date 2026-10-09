# Handover: Baucore Austin own-sourcing pilot (as of 2026-10-09)

Repo: `dsantoso-ibs/claude`, branch `claude/austin-permit-pilot-m0`, code in `pilot/`, spec in `docs/pilot-spec.md`. Re-run: see `pilot/README.md`.

## 1. Goal (from spec)
Measure whether open city permit data surfaces new construction projects missing from Baucore's paid feeds (ibau, Barbour ABI, myProjectSales) and Baucore's own data, and whether usable contacts can be found. Measurement pilot, additive to feeds, lives inside Baucore. Austin first, LA second. Decision rule: **continue** if novel share >= 30% AND contact yield >= 50% of novel projects; otherwise stop or rethink.

## 2. Status
| Milestone | Status |
|---|---|
| M0 schema discovery | Done (`pilot/reports/austin-schema.md`) |
| M1 ingest (12-month backfill + delta, idempotent) | Done. 561 raw permits; re-runs add 0 duplicates |
| M2 normalize + filter | Built, 14 tests pass. **Hand check of 20 passed + 20 excluded still owed** (`reports/filter-summary.md`) |
| M3 baseline match | Matcher built + tested, but **no baseline exists**. Manual spot-check sheet generated (`reports/manual-labels-austin.csv`, 40 projects) and **not yet labelled** |
| M4 enrichment | **Deferred by decision** (`enrichment.enabled: false`) |
| M5 report | Built; verdict currently **NOT MEASURABLE** |
| M6 Los Angeles | Not started (dataset `pi9x-tg5x` on data.lacity.org) |

## 3. Current extraction result (Austin, 2025-10-09 to 2026-10-09)
- Raw permits stored: **561** (valuation >= $100k floor; only building permits carry valuation).
- Projects (grouped by `masterpermitnum`): **213**. Passed filter: **106** (about 2.0/week overall; 9 in the last 28 days = 2.2/week).
- Excluded: 59 below $250k, 15 structures only (C-329), 9 not commercial/multi-family, 8 non-construction work class, 6 solar/EV, 6 single-family or duplex, 2 excluded status, 2 excluded class keyword.
- Contractor/applicant business named on 105 of 106 passed projects (general contractors, e.g. Bartlett Cocke, Rogers-O'Brien, Ryan Companies). No contractor appears on more than 3 projects.
- Passed per month (value): 2025-10: 4 ($125M); 11: 5 ($12M); 12: 10 ($241M); 2026-01: 7 ($8M); 02: 5 ($44M); 03: 8 ($50M); 04: 7 ($66M); 05: 19 ($318M); 06: 7 ($918M); 07: 7 ($497M); 08: 16 ($176M); 09: 10 ($98M).
- **Not measurable yet:** novel share (no baseline labels), contact yield (no enrichment), enrichment cost per project (no enrichment).

## 4. Decisions made (locked)
- Additive to existing feeds; inside Baucore; reps and agencies both; Austin then LA; DACH out of scope.
- Valuation field: `total_job_valuation`, applied per project, threshold >= $250,000.
- **A permit is not a project.** `total_job_valuation` is copied onto every permit sharing a `masterpermitnum` (e.g. one school = 3 permits at $380M each). Candidates are grouped by `masterpermitnum`, falling back to `permit_number`. This is a deliberate deviation from the spec's permit-level `candidates` table.
- Personal data: keep `applicant_org`; drop `applicant_full_name`, phones, street addresses and `contractor_full_name` **before** raw storage. (The spec assumed no applicant fields; the live dataset has them.)
- Work classes kept: New, Shell, Addition, Addition and Remodel, Remodel. Remodel/addition-only projects need a commercial (`C-`) class. Excluded: demolition, interior demo, repair, change out, irrigation, signs, residential remodels.
- Use class: commercial and multi-family (`C-` classes, `R-` 104/105/106/213/214); exclude single-family, secondary apartment and duplex codes 101/102/103; exclude a project whose only class is `C- 329`.
- Excluded statuses (prefix match): VOID, Withdrawn, Cancelled, Denied, Revoked, Rejected, Aborted.
- Solar/PV and EV-charging descriptions excluded (spec: solar is trade-only).
- Region = metro or county (assumed Travis, Williamson, Hays). Austin dataset covers City of Austin jurisdiction only.
- No baseline available, no enrichment for now.
- Salesforce MCP was checked: it is IBS's internal CRM (sales, invoices, DevOps), with no Baucore project or feed data, so it is not a baseline source.

## 5. Risks and caveats
- **Low volume:** about 2 qualifying projects a week. Four weeks gives about 9-10 projects, too few to test a 30% threshold. Plan: measure on the 12-month set and report the last 4 weeks separately. Older projects are more likely to already be in feeds, so the 12-month novel share is conservative (understates novelty).
- Manual spot-check of 40 projects gives roughly +/-15 points of uncertainty at 95%; the report prints the Wilson interval and says INCONCLUSIVE when it straddles 30%.
- Contractor-on-permit is only a **proxy**. It is a general contractor, not an owner, developer or architect, so it does not count toward the 50% contact-yield test. Until enrichment is enabled, the best possible verdict is "provisional continue".
- Lat/lon present on about 85% of all permits (about 60% of recent qualifying projects), so address matching must carry M3.
- Filter rules were tuned while looking at the same samples; the hand check should be done on fresh eyes. Possible misclassification: `7817 W SH 71` ($76M) is classed as two-family plus three/four-family and may be mostly duplexes.
- The 40-project sample has been drawn from a fixed seed, so re-running gives the same projects unless the filter changes.

## 6. Open items / next steps
1. Someone with Project Match or ibau access labels the 40 rows in `pilot/reports/manual-labels-austin.csv` (`in_baseline` = y/n/unsure, plus `found_in`), then `python -m src.baseline import-labels <file>` and `python -m src.report austin`.
2. Do the 20 + 20 hand check of the filter (`pilot/reports/filter-summary.md`).
3. If a feed export becomes available, load it with `python -m src.baseline load ...` and run `match`.
4. Decide when to enable enrichment (M4). Needs the Google enrichment and Selfi interfaces/credentials and a daily cost cap. Needed for contact yield and cost-plus regional pricing.
5. Optional: M6 Los Angeles to prove the pipeline handles a second schema through config only.
6. Optional: obtain a Socrata app token (`SOCRATA_APP_TOKEN`) for the daily delta, and schedule the daily run.

## 7. How the filter decides (project level, all values in `pilot/config.yaml`)
1. Project valuation >= $250,000.
2. At least one building permit (`BP`); projects with only trade permits are excluded.
3. Not every permit status is in the excluded list.
4. At least one work class in the allowed list.
5. At least one allowed use class; description not solar/EV; not only `C- 329`.
6. Remodel/addition-only projects must have a `C-` class.
Every excluded project stores one `exclude_reason`.

## 8. Files
- `pilot/config.yaml`: all thresholds, field map, filter rules, region, decision thresholds.
- `pilot/src/`: `sources/socrata.py`, `discover.py`, `ingest.py`, `normalize.py`, `filter.py`, `run_filter.py`, `baseline.py`, `report.py`, `schema.py`, `config.py`.
- `pilot/tests/test_core.py`: 14 tests (address normalization, filter rules, grouping, idempotency, matching, verdict, labels).
- `pilot/reports/`: `austin-schema.md`, `filter-summary.md`, `austin-candidates.csv` (all 213 projects), `manual-labels-austin.csv`, `pilot-2026-10-09.md/.csv`.
- `pilot/data/pilot.sqlite` is git-ignored; rebuild with the commands in the README (about a minute).

## 9. All 106 passed projects (sorted by valuation)
| # | project key | address | valuation USD | work class | use class | contractor | issued | permits |
|---|---|---|---|---|---|---|---|---|
| 1 | 13107658 | 6915 BRIDGE POINT PKWY | 830,000,000 | New | C- 104 Three & Four Family Bldgs + C- 105 Five or More Family Bldgs +  | Harvey-Cleary Builders ***MAIN*** | 2026-06-08 | 77 |
| 2 | 13532840 | 3935 BRIGHT LIGHT BLVD | 380,000,000 | New | C- 326 Schools & Other Educational Bldgs | Bartlett Cocke General Contractors (MAIN) | 2026-07-23 | 3 |
| 3 | 13257587 | 62 E AVE | 154,000,000 | New|Shell | C- 105 Five or More Family Bldgs + C- 321 Pkg Garage Bldg & Open Deck | Summit Design Build | 2026-05-08 | 2 |
| 4 | 13538837 | 2915 E CESAR CHAVEZ ST | 100,000,000 | New | C- 105 Five or More Family Bldgs + C- 321 Pkg Garage Bldg & Open Deck | JLB Builders, LLC | 2025-10-09 | 7 |
| 5 | 13539107 | 512 SABINE ST | 79,500,000 | New|Shell | C- 105 Five or More Family Bldgs + C- 321 Pkg Garage Bldg & Open Deck  | Ryan Companies US INC | 2026-07-01 | 9 |
| 6 | 13114310 | 7817 W SH 71 | 76,000,000 | New|Shell | C- 103 Two Family Bldgs + C- 104 Three & Four Family Bldgs + C- 105 Fi | Morgan PRL Construction LLC | 2025-12-11 | 18 |
| 7 | 13527831 | 4810 GONZALES ST | 51,750,000 | New|Shell | C- 105 Five or More Family Bldgs + C- 321 Pkg Garage Bldg & Open Deck | The NRP Contractors, LLC | 2026-09-29 | 2 |
| 8 | 13617546 | 1412 NORSEMAN TER | 51,150,000 | New | C- 326 Schools & Other Educational Bldgs | Joeris General Contractors***MAIN*** | 2026-08-19 | 1 |
| 9 | 13513914 | 4812 GONZALES ST | 50,000,000 | New | C- 321 Pkg Garage Bldg & Open Deck | NRP Contractors II, LLC | 2025-12-29 | 1 |
| 10 | 13150876 | 2631 KRAMER LN | 48,000,000 | New | C- 105 Five or More Family Bldgs + C- 321 Pkg Garage Bldg & Open Deck  | OHT Construction LLC ***MAIN*** | 2026-08-27 | 6 |
| 11 | 13500054 | 2206 BLUE MEADOW DR | 47,183,562 | New | C- 326 Schools & Other Educational Bldgs | Hill & Wilkinson GC | 2025-12-02 | 1 |
| 12 | 13091575 | 1420 E HOWARD LN | 39,719,000 | New | C- 105 Five or More Family Bldgs | Journeyman Construction | 2026-05-08 | 16 |
| 13 | 12286908 | 1900 ALDRICH ST | 36,000,000 | Shell | C- 324 Office, Bank & Professional Bldgs | Cadence McShane Construction Company | 2026-06-18 | 1 |
| 14 | 13476069 | 5600 SUNSHINE DR | 35,587,000 | New | C- 326 Schools & Other Educational Bldgs | Adolfson & Peterson Construction | 2026-04-16 | 1 |
| 15 | 13575229 | 1326 LAMAR SQUARE DR | 32,500,000 | New | C- 105 Five or More Family Bldgs | Bailey Elliott Construction, Inc. D/B/A BEC Austin | 2026-05-13 | 1 |
| 16 | 13505915 | 1106 W DITTMAR RD | 30,400,000 | New | C- 323 Hospital & Institutional Bldgs | The Christman Company | 2026-07-27 | 1 |
| 17 | 12768207 | 1320 ART DILLY DR | 30,000,000 | Shell | C- 105 Five or More Family Bldgs | Bartlett Cocke General Contractors (MAIN) | 2026-05-26 | 1 |
| 18 | 13544797 | 6420 HELEN MILLER VW | 28,000,000 | New | C- 321 Pkg Garage Bldg & Open Deck + C- 324 Office, Bank & Professiona | HOAR Construction LLC | 2026-08-04 | 2 |
| 19 | 13688451 | 6801 NORTHEAST DR | 25,000,000 | New | C- 326 Schools & Other Educational Bldgs | Rogers-O'Brien Construction | 2026-06-26 | 2 |
| 20 | 13686134 | 3733 DROSSETT DR | 23,899,293 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Braintec USA, Inc. | 2026-06-26 | 2 |
| 21 | 13574251 | 823 TILLERY ST | 23,000,000 | New | C- 105 Five or More Family Bldgs | Camden Development | 2025-10-14 | 1 |
| 22 | 13638616 | 3505 MONTOPOLIS DR | 22,000,000 | New | C- 324 Office, Bank & Professional Bldgs + C- 329 Com Structures Other | ZAPALAC/REED CONSTRUCTION CO., LP | 2026-03-30 | 3 |
| 23 | 13540590 | 5516 HUMMING BIRD LN | 20,000,000 | New | C- 105 Five or More Family Bldgs | ICON Builders, LLC | 2026-02-17 | 1 |
| 24 | 13429438 | 10095 E US 290 HWY SVRD EB | 18,000,000 | New | C- 320 Industrial Bldgs | Pritchard Associates, Inc. | 2025-12-18 | 2 |
| 25 | 13492633 | 1103 W 24TH ST | 17,662,614 | New|Shell | C- 105 Five or More Family Bldgs + C- 321 Pkg Garage Bldg & Open Deck | OGH Development | 2026-09-28 | 2 |
| 26 | 13661108 | 11900 VISTA PARKE DR | 17,510,428 | New | C- 322 Service Station & Repair Garage | Bartlett Cocke General Contractors (MAIN) | 2026-05-08 | 2 |
| 27 | 13572242 | 811 W LIVE OAK ST | 17,000,000 | New | C- 213 Hotels, Motels, & Tourist Cabins | La Corsha Hospitality Group | 2025-12-15 | 1 |
| 28 | 13448832 | 6405 BERKMAN DR | 17,000,000 | New | C- 105 Five or More Family Bldgs | ICON Builders, LLC | 2026-02-09 | 1 |
| 29 | 13490322 | 7734 MC KINNEY FALLS PKWY | 15,000,000 | New | C- 327 Stores & Customer Services | PrimeHaven Development LLC | 2026-03-18 | 1 |
| 30 | 13609932 | 2901 S US 183 HWY NB | 15,000,000 | New | C- 328 Commercial Other Nonresident Bldg | Burns & McDonnell Engineering Company, Inc | 2026-04-21 | 1 |
| 31 | 13548477 | 6410 FM 969 RD | 14,175,165 | New | C- 105 Five or More Family Bldgs | Bailey Elliott Construction, Inc. D/B/A BEC Austin | 2025-12-01 | 1 |
| 32 | 12566164 | 4401 TILLEY ST | 13,855,000 | New | C- 326 Schools & Other Educational Bldgs | Joeris General Contractors***MAIN*** | 2026-08-19 | 1 |
| 33 | 13705527 | 12520 HARRIS BRANCH PKWY | 12,300,000 | New | C- 320 Industrial Bldgs + C- 329 Com Structures Other Than Bldg | Kingham Dalton Wilson | 2026-08-13 | 2 |
| 34 | 13444480 | 12221 TECH RIDGE BLVD | 11,000,000 | New | C- 213 Hotels, Motels, & Tourist Cabins | Deffenbaugh Building Co | 2026-05-12 | 1 |
| 35 | 13619488 | 1715 W CESAR CHAVEZ ST | 10,357,457 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Cadence McShane Construction Company | 2026-04-07 | 1 |
| 36 | 13380842 | 6620 ED BLUESTEIN BLVD SB | 10,067,000 | New | C- 105 Five or More Family Bldgs | DMJ Construction Services LLC | 2026-09-04 | 3 |
| 37 | 13613839 | 1307 E BRAKER LN | 10,000,000 | New | C- 319 Churches and Othr Religious Bldgs | G Creek INC.***MAIN*** | 2025-12-19 | 1 |
| 38 | 13340914 | 4611 TILLEY ST | 9,000,000 | New | C- 326 Schools & Other Educational Bldgs | Zapalac/Reed (MAIN) Construction Company | 2026-09-14 | 1 |
| 39 | 13547304 | 3006 BOWMAN AVE | 8,989,991 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Knight Construction | 2026-08-05 | 1 |
| 40 | 13576235 | 2220 E M FRANKLIN AVE | 7,000,000 | New | C- 324 Office, Bank & Professional Bldgs | Sturzenbecker Construction Co., Inc. | 2026-03-24 | 2 |
| 41 | 13629604 | 700 SOLITUDE DR | 6,904,310 | New | C- 324 Office, Bank & Professional Bldgs | Protrac Solutions LLC | 2026-05-27 | 1 |
| 42 | 13590902 | 625 E 10TH ST | 6,779,859 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | STR Constructors | 2025-11-17 | 1 |
| 43 | 13453080 | 11500 CANVAS LN | 6,000,000 | New|Shell | C- 327 Stores & Customer Services + C- 329 Com Structures Other Than B | John King Construction Company  **MAIN** | 2025-12-22 | 6 |
| 44 | 13599426 | 3101 E YAGER LN | 6,000,000 | New | C- 328 Commercial Other Nonresident Bldg | C.E. Gleeson Constructors, Inc. | 2026-02-27 | 1 |
| 45 | 13565758 | 4411 MEINARDUS DR | 5,500,000 | New | C- 321 Pkg Garage Bldg & Open Deck | Noble General Contractors | 2026-05-14 | 3 |
| 46 | 13637624 | 8306 CROSS PARK DR | 5,000,000 | New | C- 320 Industrial Bldgs | Flynn Construction***Main | 2026-05-18 | 1 |
| 47 | 13626650 | 5010 W US 290 HWY WB | 3,400,000 | New | C- 327 Stores & Customer Services | Jerry Kachel Builders, Inc | 2026-05-22 | 1 |
| 48 | 13414679 | 5217 WINNEBAGO LN | 3,000,000 | New | C- 324 Office, Bank & Professional Bldgs | TG EdwardsConstruction Inc. | 2026-09-28 | 1 |
| 49 | 13588649 | 714 E BEN WHITE BLVD SVRD WB | 3,000,000 | New | C- 322 Service Station & Repair Garage | HCI Commercial | 2026-07-09 | 1 |
| 50 | 13686271 | 1205 SHELDON CV | 3,000,000 | New | C- 318 Amusement, Social & Rec Bldgs | DKC Construction Group | 2026-08-20 | 1 |
| 51 | 13758265 | 3801 N LAMAR BLVD | 2,980,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | CM Constructors *MAIN* | 2026-09-29 | 1 |
| 52 | 13497801 | 2307 EUCLID AVE | 2,558,020 | New | C- 319 Churches and Othr Religious Bldgs | G Creek INC.***MAIN*** | 2026-07-21 | 1 |
| 53 | 13562281 | 13802 FM 812 RD | 2,500,000 | New | C- 320 Industrial Bldgs | Diamond One Construction Inc DBA Steelwood Inc | 2026-05-27 | 1 |
| 54 | 13514216 | 1010 E CESAR CHAVEZ ST | 2,300,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | AR Lucas Construction | 2026-05-20 | 1 |
| 55 | 13621621 | 1610 DUNGAN LN | 2,200,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | IE2 CONSTRUCTION, INC | 2026-03-19 | 1 |
| 56 | 13563126 | 7200 SPRINGFIELD DR | 2,200,000 | New | C- 327 Stores & Customer Services | Northstar Construction Services, LLC | 2026-08-18 | 1 |
| 57 | 13346045 | 912 BASTROP HWY SB | 2,091,600 | New | C- 324 Office, Bank & Professional Bldgs | Engen Contracting, Inc. | 2025-11-06 | 3 |
| 58 | 13168285 | 5800 E PARMER LN | 2,050,000 | New|Shell | C- 327 Stores & Customer Services + C- 329 Com Structures Other Than B | Hunington Properties | 2026-08-27 | 2 |
| 59 | 12897513 | 5811 PALO BLANCO LN | 2,000,000 | New | C- 328 Commercial Other Nonresident Bldg | Spawglass Contractors Inc | 2026-01-30 | 1 |
| 60 | 13371400 | 7504 COTA VISTA DR | 2,000,000 | New | C- 105 Five or More Family Bldgs + C- 328 Commercial Other Nonresident | Skybeck Construction, LLC | 2026-01-15 | 16 |
| 61 | 13526363 | 9801 W PARMER LN | 1,800,000 | New | C- 328 Commercial Other Nonresident Bldg | Capitol Painting and Construction | 2026-05-05 | 1 |
| 62 | 13676600 | 601 W BRAKER LN | 1,800,000 | New | C- 319 Churches and Othr Religious Bldgs | Braun and Butler Construction | 2026-05-28 | 1 |
| 63 | 13646920 | 3101 E YAGER LN | 1,600,000 | Shell | C- 327 Stores & Customer Services | Flintrock Commercial | 2026-04-29 | 1 |
| 64 | 12853765 | 1806 W BRAKER LN | 1,500,000 | New | C- 318 Amusement, Social & Rec Bldgs | Siegert Design And Construction | 2025-10-22 | 1 |
| 65 | 13572304 | 10037 MENCHACA RD | 1,500,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Oak Valley Construction LLC | 2025-12-01 | 1 |
| 66 | 13646811 | 601 RIO GRANDE ST | 1,500,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | CTC Contractors, LLC | 2026-04-22 | 1 |
| 67 | 13539148 | 9220 W PARMER LN | 1,500,000 | New | C- 322 Service Station & Repair Garage | 1020 Construction | 2026-05-06 | 1 |
| 68 | 13697365 | 5707 SOUTHWEST PKWY | 1,500,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Turner Construction | 2026-08-14 | 1 |
| 69 | 13693094 | 5800 E PARMER LN | 1,500,000 | New | C- 327 Stores & Customer Services | The Struthoff Company, Inc. (***MAIN***) | 2026-07-19 | 1 |
| 70 | 13565591 | 1600 WHELESS LN | 1,350,000 | New | C- 105 Five or More Family Bldgs | NGR Constructions and Consulting Engg LLC | 2026-08-10 | 1 |
| 71 | 13622213 | 1802 CROSSING PL | 1,200,000 | New | C- 106 Mixed Use | ROGERS OBRIEN CONSTRUCTION | 2025-12-10 | 1 |
| 72 | 13603237 | 4408 LONG CHAMP DR | 1,100,000 | New | C- 318 Amusement, Social & Rec Bldgs + C- 329 Com Structures Other Tha | Capital Constructors Group | 2026-01-29 | 3 |
| 73 | 13664644 | 805 E RUNDBERG LN | 1,100,000 | Addition | C- 437 Addn, Alter, Convn-NonRes | Hayden Construction | 2026-08-25 | 1 |
| 74 | 13586574 | 13101 BURMAKANY DR | 1,000,000 | New | C- 318 Amusement, Social & Rec Bldgs + C- 329 Com Structures Other Tha |  | 2025-11-24 | 11 |
| 75 | 13501889 | 8301 JOHNNY MORRIS RD | 1,000,000 | New | C- 328 Commercial Other Nonresident Bldg + C- 329 Com Structures Other | Gordon Highlander | 2025-11-07 | 35 |
| 76 | 13630817 | 3600 PRESIDENTIAL BLVD | 1,000,000 | New | C- 328 Commercial Other Nonresident Bldg | Smash Design LLC | 2026-01-20 | 1 |
| 77 | 13603253 | 78 RAINEY ST | 1,000,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | MDG Construction LLC | 2026-03-05 | 1 |
| 78 | 13503359 | 1706 PAYTON GIN RD | 1,000,000 | New|Shell | C- 105 Five or More Family Bldgs + C- 321 Pkg Garage Bldg & Open Deck  | Roers Companies | 2026-03-31 | 4 |
| 79 | 13590912 | 811 CLAYTON LN | 1,000,000 | New | C- 324 Office, Bank & Professional Bldgs + C- 328 Commercial Other Non | Novo Construction **Main** | 2026-03-27 | 19 |
| 80 | 13590904 | 12705 CENTER LAKE DR | 1,000,000 | New | C- 326 Schools & Other Educational Bldgs | Wytex BTS, Inc. | 2026-04-03 | 1 |
| 81 | 13673874 | 13401 ESCARPMENT BLVD | 1,000,000 | New | C- 318 Amusement, Social & Rec Bldgs | Navcon Group, LLC***MAIN*** | 2026-05-14 | 1 |
| 82 | 13689401 | 1115 SAN JACINTO BLVD | 1,000,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Harvey-Cleary Builders ***MAIN*** | 2026-06-11 | 1 |
| 83 | 13680590 | 1000 W MARTIN LUTHER KING JR BLVD | 1,000,000 | New | C- 326 Schools & Other Educational Bldgs | Swinerton Builders Inc. | 2026-08-03 | 1 |
| 84 | 13597142 | 7333 BLUFF SPRINGS RD | 1,000,000 | New | C- 105 Five or More Family Bldgs + C- 329 Com Structures Other Than Bl | Dominion Construction, LLC | 2026-08-03 | 19 |
| 85 | 13721159 | 4408 LONG CHAMP DR | 1,000,000 | New | C- 318 Amusement, Social & Rec Bldgs + C- 329 Com Structures Other Tha | ROGERS OBRIEN CONSTRUCTION | 2026-09-15 | 13 |
| 86 | 13626657 | 8920 HILLOCK TER | 1,000,000 | New | C- 105 Five or More Family Bldgs + C- 321 Pkg Garage Bldg & Open Deck  | Clark Wilson Builders INC. | 2026-09-25 | 35 |
| 87 | 13507600 | 7706 COTA VISTA DR | 900,000 | New | C- 327 Stores & Customer Services | The Struthoff Co. Inc. | 2025-10-28 | 1 |
| 88 | 13679039 | 2411 E MARTIN LUTHER KING JR BLVD | 900,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Archive Properties LLC | 2026-06-08 | 1 |
| 89 | 13455567 | 3600 PRESIDENTIAL BLVD | 850,000 | New | C- 322 Service Station & Repair Garage | Warden Construction Corporation | 2026-01-29 | 1 |
| 90 | 13444193 | 6707 EMERALD FOREST DR | 850,000 | New | C- 328 Commercial Other Nonresident Bldg | Stephen Thomas Construction | 2026-06-10 | 1 |
| 91 | 13513893 | 7000 JOHNNY MORRIS RD | 750,000 | Shell | C- 328 Commercial Other Nonresident Bldg | Spark Root Construction | 2026-05-20 | 3 |
| 92 | 12865921 | 7121 ELROY RD | 729,180 | New | C- 321 Pkg Garage Bldg & Open Deck | Bonner Carrington Construction | 2026-02-10 | 1 |
| 93 | 13373560 | 7015 E WILLIAM CANNON DR | 650,000 | New | C- 327 Stores & Customer Services | Legacy Commercial Contractors LLC | 2026-01-26 | 1 |
| 94 | 13619072 | 8433 BURNET RD | 650,000 | Shell | C- 324 Office, Bank & Professional Bldgs | Structura, Inc. | 2026-05-08 | 1 |
| 95 | 13655817 | 620 W SLAUGHTER LN | 650,000 | New | C- 327 Stores & Customer Services + C- 329 Com Structures Other Than B | Wurzel Builders, Ltd.**MAIN** | 2026-09-11 | 2 |
| 96 | 13581283 | 7201 LEVANDER LOOP | 627,000 | New | C- 324 Office, Bank & Professional Bldgs | Zapalac/Reed (MAIN) Construction Company | 2026-02-02 | 1 |
| 97 | 13430467 | 95 CLARA ST | 620,400 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Franklin-Alan LLC ***MAIN*** | 2025-11-07 | 1 |
| 98 | 13336598 | 4503 LUCKSINGER LN | 500,000 | New | C- 320 Industrial Bldgs | K&K Welding LLC | 2026-10-01 | 1 |
| 99 | 13529935 | 1500 SAN JACINTO BLVD | 500,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Podular Construction | 2026-09-03 | 1 |
| 100 | 13611926 | 6406 N IH 35 SVRD SB | 500,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | B&C Construction | 2026-04-06 | 1 |
| 101 | 13600373 | 4416 BURNET RD | 450,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Icon Projects LLC | 2026-01-08 | 1 |
| 102 | 13687740 | 9809 CURLEW DR | 450,000 | New | C- 328 Commercial Other Nonresident Bldg | Synergy Commercial Construction | 2026-08-06 | 2 |
| 103 | 13063118 | 11901 DIONDA LN | 383,580 | New | C- 105 Five or More Family Bldgs | SHFC Pedcor Construction JV | 2026-03-19 | 1 |
| 104 | 13619726 | 6711 BURNET LN | 324,821 | Addition | C- 437 Addn, Alter, Convn-NonRes | Kb Contractors TX | 2026-05-01 | 1 |
| 105 | 13684145 | 1803 S 1ST ST | 306,000 | Addition and Remodel | C- 437 Addn, Alter, Convn-NonRes | Sharpebuild LLC | 2026-07-02 | 1 |
| 106 | 13691877 | 1404 SWEET BARK ST | 250,000 | New | C- 328 Commercial Other Nonresident Bldg | Adventures Outback LP DBA AO Services | 2026-08-17 | 1 |
