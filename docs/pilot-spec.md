# Build Addendum: Baucore Own-Sourcing Pilot (Austin, then LA)

Hand this file to Claude Code as project context (e.g. `CLAUDE.md` addendum or `docs/pilot-spec.md`). Source of decisions: `brainstorms/2026-10-09-baucore-new-project-discovery.md`.

## 1. Goal

Find out whether permit data from open city portals surfaces **new construction projects** that Baucore's paid feeds (ibau, Barbour ABI, myProjectSales) and existing Baucore data do not already contain, and whether we can find usable contacts for them.

This is a **measurement pilot**, not a product. Build the smallest thing that answers the question in Section 8.

## 2. Locked decisions (do not revisit)

- Own sourcing is **additive** to existing feeds.
- It lives **inside Baucore** (feeds Project Match and the customer pipeline). Not a standalone data product.
- Target users: **both** manufacturer reps and agencies. Capture all contact roles; relevance is decided downstream by Project Match, not here.
- Build order: **Austin first, then Los Angeles.** DACH comes later and is out of scope.
- Project filter: declared valuation **>= $250,000**; commercial, multi-family, industrial; **exclude single-family**; exclude trade-only permits (plumbing, electrical, mechanical, solar, roofing, driveway/sidewalk).
- Store **raw** permit records so filters can change without re-fetching.
- Pricing is cost-plus per region, so the pilot must **log cost and volume**.
- Builder: Donny + AI. No deadline. Keep scope small. Prefer APIs over scraping.

## 3. Non-goals

- No DACH, news crawling, or planning-document extraction.
- No Salesforce/Baucore write-back in this phase. Output is a local database plus reports.
- No UI. CLI and CSV/Markdown reports only.
- No owner or applicant personal data. Contractor and company names from public permit records only.

## 4. Architecture

Standalone Python sidecar (3.11+), SQLite, no framework. Suggested layout:

```
pilot/
  config.yaml            # filters, thresholds, source ids
  src/
    sources/socrata.py   # generic SODA client (Austin, LA)
    schema.py            # SQLite DDL + helpers
    ingest.py            # fetch -> raw table (idempotent)
    normalize.py         # raw -> normalized project candidate
    filter.py            # apply Section 5 rules, record reason per exclusion
    baseline.py          # load feed/Baucore export, match candidates
    enrich.py            # enrichment interface + cost logging (stub first)
    report.py            # Section 8 metrics -> reports/*.md and CSV
  tests/
  reports/
  data/pilot.sqlite
```

Use `httpx`, `pydantic`, `pytest`, `rapidfuzz` (address matching). Keep dependencies minimal.

## 5. Data sources and rules

**Austin:** Socrata dataset `3syk-w9eu` ("Issued Construction Permits") on `data.austintexas.gov`. Refreshed daily. Per research it carries contractor, address, valuation, geo, but **no owner/applicant**.

**Los Angeles (phase 2):** LADBS "Building Permits Issued from 2020 to Present", dataset `pi9x-tg5x` on `data.lacity.org`. There are also "Submitted" datasets, which are an earlier stage and worth testing.

**Do not assume field names.** First task is schema discovery: fetch the dataset metadata/columns (`/api/views/<id>.json`) and a sample of rows, then write the field mapping into `config.yaml`. Verify the permit-type, work-class, and valuation fields before writing filter code.

Use the Socrata SODA API with `$where`, `$limit`, `$offset`/`$order`. Support an app token via env var `SOCRATA_APP_TOKEN`. Page politely, with backoff on 429/5xx.

Filter rules (all configurable in `config.yaml`):

1. Valuation >= 250000.
2. Permit type/work class indicates new construction or major addition/alteration.
3. Occupancy/use is commercial, multi-family, or industrial. Exclude single-family and duplex.
4. Exclude trade-only permit types.
5. Every excluded record stores an `exclude_reason`. Report counts per reason.

## 6. Data model (SQLite)

- `raw_permits(source, source_id, fetched_at, payload_json, PRIMARY KEY(source, source_id))`
- `candidates(id, source, source_id, address_norm, lat, lon, valuation, permit_type, work_class, use_class, issued_date, description, contractor_name, status, first_seen_at)`
- `filter_results(candidate_id, passed BOOL, exclude_reason)`
- `baseline_projects(id, origin, name, address_norm, lat, lon, city, raw_json)` where `origin` is e.g. `ibau`, `barbour`, `myprojectsales`, `baucore`
- `matches(candidate_id, baseline_id, score, method)`
- `enrichments(candidate_id, provider, requested_at, cost_usd, result_json, found_owner BOOL, found_developer BOOL, found_architect BOOL, found_contact BOOL)`
- `runs(id, started_at, source, rows_fetched, rows_new, notes)`

Ingest must be **idempotent**: re-running never duplicates rows.

## 7. Milestones and acceptance criteria

**M0: Schema discovery (0.5 day).** Script prints Austin columns, 20 sample rows, distinct permit types / work classes / use values. Output saved to `reports/austin-schema.md`. *Done when* the filter field mapping is confirmed from real data.

**M1: Ingest (1 day).** Backfill the last 90 days, then a daily delta. *Done when* a second run adds 0 duplicate rows and `runs` shows counts.

**M2: Normalize + filter (1 day).** Address normalization (case, suffixes, unit stripping) and the Section 5 filter. *Done when* `reports/filter-summary.md` shows passed vs excluded counts by reason, and a hand check of 20 passed and 20 excluded records agrees with the rules.

**M3: Baseline match (1-2 days).** Load the Austin-area baseline export(s) into `baseline_projects`. Match candidates by normalized address plus geo proximity (e.g. within 100 m) plus fuzzy name. Store score and method; flag 0.6-0.85 scores for manual review. *Done when* every passed candidate is labelled `in_baseline` / `novel` / `review`, and 20 manual spot checks agree.

**M4: Enrichment hook with cost logging (1-2 days).** Define `Enricher` protocol: `enrich(candidate) -> EnrichmentResult(cost_usd, owner, developer, architect, contacts, raw)`. Implement stub, then adapters that call the existing Google enrichment and Selfi (ask Donny for the interfaces). Run only on **passed and novel** candidates. Respect a daily cost cap from config. *Done when* each enrichment row records provider, cost, and what was found.

**M5: Report (0.5 day).** `python -m src.report` writes `reports/pilot-YYYY-MM-DD.md` + CSV with the metrics below.

**M6: Los Angeles.** Repeat M0-M3 with the LA source to prove the pipeline handles a second schema without code changes beyond config/mapping.

## 8. Pilot success test and metrics

After 4 weeks of Austin data, the report must show:

1. Qualifying projects per week (passed filter).
2. **Novel share** = novel / (novel + in_baseline), with the `review` bucket shown separately.
3. Contact yield: of novel projects enriched, % where owner, developer, or architect was found; and % with any usable contact.
4. Enrichment cost per project and per week; projected monthly cost for the region.
5. Top exclusion reasons.

Decision rule (agreed): **continue** if novel share >= 30% AND contact yield >= 50% of novel projects. **Stop or rethink** if most qualifying projects are already in feeds or enrichment finds no contacts. The report prints this verdict with the numbers.

## 9. Guardrails

- Use only public, official open-data endpoints. No scraping of authenticated or ToS-restricted sites.
- Rate-limit and back off. Cache raw payloads.
- Secrets in env vars only (`SOCRATA_APP_TOKEN`, enrichment keys). Never commit them.
- No personal data about individuals; business names only. Log, don't store, anything that looks like a private owner name from enrichment unless Donny approves.
- Every threshold lives in `config.yaml`, not in code.
- Tests: unit tests for address normalization, filter rules, and matching, with fixtures from real sample rows.

## 10. Inputs needed from Donny before M3/M4

- The Austin-area baseline export(s): ibau, Barbour ABI, myProjectSales, and Baucore project list (CSV or API access).
- Interfaces/credentials for the existing Google enrichment and Selfi.
- Confirmation that a billing "region" means metro/county (assumed).

## 11. First prompt for Claude Code

> Read `docs/pilot-spec.md`. Start with M0 only: create the project skeleton and a script that fetches Austin dataset `3syk-w9eu` metadata and 20 sample rows, prints the columns and distinct values for permit type, work class and use, and writes `reports/austin-schema.md`. Do not write filter code until I have reviewed the schema report. Ask me if any field is ambiguous.
