# Phase 2 Addendum: Austin Site Plan Cases and Lead Time

Add to `docs/pilot-spec.md`. Builds on the existing pilot (`pilot/`, M0-M2 done). Decisions come from `brainstorms/2026-10-09-baucore-new-project-discovery.md`.

## 1. Why

The issued-permit data is stage 4 (contractor already chosen). We need stages 1-3, where a customer can still influence the product decision. Austin's **Site Plan Cases** dataset covers applications submitted for review, which is before the permit is issued and includes an **owner**. Linking each case to its later permit lets us measure **how many weeks earlier we see a project**. That number is the real test of stage 2 value.

## 2. Scope

In scope:
- New source: Austin **Site Plan Cases**, Socrata dataset `mavg-96ck` on `data.austintexas.gov`.
- Link site plan cases to issued permit projects already in `pilot.sqlite`.
- Lead-time and pipeline metrics.
- Schema discovery for **Plan Review Cases** (`n8ck-xkda`) only, no ingest yet.
- Research task on TDLR TABS access (Section 7), no scraping.

Out of scope: LA, DACH, enrichment (still disabled), Baucore write-back, building any TABS scraper.

## 3. Known facts and unknowns

Known (from catalog descriptions): Site Plan Cases contains applications submitted for review, with case status, case number, proposed use, applicant, owner, and location.

**Unknown, discover before coding:** exact column names, the submission/filing date field, whether there is any size field (units, square footage, acreage), whether status values distinguish approved/expired/withdrawn, and how far back and how current the data is. There is **no valuation field mentioned**, so the $250k filter cannot apply directly.

## 4. Milestones

**M7.0 Schema discovery.** Same approach as M0 for `mavg-96ck`: columns, 20 sample rows, distinct values for status, proposed use, and any type or size field; min and max of every date field; row count; last-modified. Write `reports/site-plan-schema.md`. Also produce a short `reports/plan-review-schema.md` for `n8ck-xkda`. **Stop and show Donny both reports before writing filter code.**

**M7.1 Ingest.** Idempotent ingest into `raw_site_plans(source, source_id, fetched_at, payload_json)`. Backfill 24 months if available, then daily delta. Apply the personal data rule in Section 5 **before** storing.

**M7.2 Normalize + filter.** Table `site_plan_candidates(id, case_number, address_norm, lat, lon, proposed_use, use_class, status, submitted_date, applicant_org, owner_entity, size_hint, first_seen_at)`.
Filter rules (config-driven, each exclusion stores a reason):
1. Proposed use is commercial, multi-family, or industrial. Exclude single-family and duplex.
2. Exclude statuses that mean withdrawn, void, denied, expired (confirm real values in M7.0).
3. No valuation floor. Instead keep a `size_hint` (units, sq ft, or acreage if present) and show **valuation from the linked permit** when a match exists.
Report counts per exclusion reason.

**M7.3 Link to permits.** Link each passed site plan case to a permit project in `candidates` using normalized address plus geo proximity (e.g. within 100 m), with fuzzy match on owner or applicant vs. contractor names as a supporting signal only. Store `site_plan_permit_links(case_id, project_key, score, method)`. Scores between 0.6 and 0.85 go to a `review` bucket. Do not force matches.

**M7.4 Metrics.** Extend the report with:
1. Passed site plan cases per week (last 28 days and last 12 months).
2. Share of cases linked to an issued permit.
3. **Lead time** = permit issued date minus site plan submitted date: median, 25th and 75th percentiles, in days. Only for linked cases.
4. **Open pipeline**: passed cases with no linked permit yet, listed with owner entity, applicant, proposed use, address, submitted date. This is the stage 2 product.
5. Owner/applicant coverage: % of passed cases with a usable business entity name.

**M7.5 Manual novelty check (extend existing sheet).** Generate a second CSV of 30 random open-pipeline cases (stratified: 10 multi-family, 10 commercial, 10 industrial/other if available) for Donny to label `in_baseline` y/n/unsure with `found_in`. Use the same Wilson interval reporting as before.

## 5. Personal data rule (same as phase 1)

Keep business entities only (applicant organization, owner entity such as LLC, LP, INC, trust, university, school district). If an owner or applicant looks like an individual, drop the name before storage and set `owner_entity = NULL` with a flag `owner_is_individual = true`. Never store phone numbers or personal addresses.

## 6. Acceptance criteria

- M7.0 reports exist and Donny has approved the field mapping.
- A second ingest run adds 0 duplicate rows.
- A hand check of 20 passed and 20 excluded cases agrees with the rules (done by someone other than the person who tuned the filter, if possible).
- Linking is spot checked on 20 linked pairs and 10 unlinked cases.
- The report prints lead-time quartiles, open pipeline size, and the owner coverage number. If fewer than 30 cases are linked, the report says the lead time is **provisional**.

## 7. Research task: TDLR TABS (no scraping)

Investigate and report only:
1. Is there a bulk download or API for Texas Architectural Barriers project registrations (check data.texas.gov and the TDLR site)?
2. If only the TABS search pages exist: what do the site's terms of use and `robots.txt` say about automated access? Can projects be filtered by county, registration date, or estimated cost?
3. What fields are available per project (owner, design firm, estimated cost, start date, scope, square footage, type of work, county) and how fresh are the records?
4. Which filing counts per week would we expect for Travis, Williamson, and Hays counties (sample by hand)?

Write `reports/tabs-access.md`. **Do not build a scraper** until Donny approves based on that report.

## 8. Also check

Run a one-off query for the latest date in Austin's Zoning Cases dataset (`edir-dcnf`) and Neighborhood Planning Cases (`ck7t-hvbr`). The catalog shows 2024 modification dates, so they may be stale. Report the result in `reports/zoning-freshness.md`.

## 9. First prompt for Claude Code

> Read `docs/pilot-spec.md` and `docs/phase2-site-plan-lead-time.md`. Do M7.0 only: write schema discovery for Austin Site Plan Cases (`mavg-96ck`) and Plan Review Cases (`n8ck-xkda`) into `reports/`. Include the date ranges, status values, and any size fields. Do not write ingest or filter code yet. Then stop and ask me about any ambiguous field.
