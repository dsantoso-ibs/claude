# Baucore own-sourcing pilot (Austin)
Spec: `../docs/pilot-spec.md`. Python 3.11+, `pip install -r requirements.txt`. Set `SOCRATA_APP_TOKEN` if you have one.

```
python -m src.discover austin          # M0 schema report
python -m src.ingest austin            # M1 backfill (365d), then daily delta
python -m src.run_filter austin        # M2 project candidates + filter summary
python -m src.baseline sample austin   # M3 (no baseline): 40-project manual spot-check sheet
python -m src.baseline import-labels reports/manual-labels-austin.csv
python -m src.baseline load export.csv ibau --name Name --address Address --lat Lat --lon Lon   # when a feed export exists
python -m src.baseline match austin    # auto labels (manual labels are never overwritten)
python -m src.report austin            # M5 report + verdict
```
Enrichment (M4) is deferred (`enrichment.enabled: false`). Candidates are project-level (grouped by masterpermitnum).

## Phase 2 (site plans / plan review) - spec: ../docs/phase2-site-plan-lead-time.md
```
python -m src.discover_generic site_plans|plan_review   # M7.0 schema reports
python -m src.phase2_ingest                              # M7.1 idempotent ingest (60-month backfill, then delta)
python -m src.ingest austin --days 1830                  # permits over the same window (needed for linking)
python -m src.run_filter austin
python -m src.phase2 build && python -m src.phase2 link  # M7.2 normalize/filter, M7.3 link
python -m src.report_phase2                              # M7.4 metrics + open pipeline CSVs
python -m src.validate_pipeline                          # independent open-pipeline check vs full permit dataset
python -m src.phase2 sheets                              # M7.5 label sheet + hand-check sheets
python -m src.phase2 import-labels reports/manual-labels-site-plans.csv
```
Analysis: `reports/phase2-analysis.md`.

Valuation is **not** a filter any more; it only feeds `size_band` (see `reports/threshold-removal-impact.md`).

Default set = new_build, shell, addition (`project_type`); remodels are reported separately (`reports/project-type-impact.md`).
Label sheets (30 projects, default set only): `python -m src.phase2 sheets`. Enrichment dry run: `python -m src.enrich` (a real run needs a configured provider, `enrichment.enabled: true` and a confirmed cap).

Remodels: `remodel_subtype` (tenant_finish_out, interior_remodel, repair_or_other); only repair, signage and demolition-only are excluded as non-projects. Every record carries
use_class, description, applicant, contractor (permits), address and `recency_days`. Report: `python -m src.report_remodels` -> `reports/remodels-YYYY-MM-DD.md` + `reports/remodels-12m.csv`.
Search (newest first): `python -m src.index search "tenant finish out" --type remodel --subtype tenant_finish_out`. Remodels are never enriched.

## Description scrub (personal names, phones, emails)
Free-text fields are scrubbed **before storage**: permit `description`; site plan `description_of_work` and `case_name`; Plan Review `folder_description` and
`project_name`. Personal names become `[NAME]`, phone numbers and emails `[CONTACT]`; business names and project wording are kept. Every record where something was
removed carries `name_removed = 1` (candidate tables, search index, all CSVs; the raw payload has `_name_removed`). Code: `src/scrub_text.py`, `src/scrub_pipeline.py`.
Setup: `pip install -r requirements.txt && python -m spacy download en_core_web_sm`.
- Layers: contact patterns; explicit cues (`Contact:`, `Attn:`, `Owner:`, `Applicant:`, `c/o`, `per/with/by <Name>`); titles (`Mr.`, `Dr.`); `<Surname> Residence`;
  initial + surname; and NER (spaCy) for free-standing first+last names. NER spans are kept as project wording or a business when they look like a place, brand, known
  business name, or contain words that appear in lowercase elsewhere in the corpus (people's names do not).
- **Limits (it is heuristic, not a guarantee):** an uncommon name with no cue and no name-list hit (e.g. "Yuki Tanaka" in running text) is not removed; a cue-less
  unusual surname alone is not removed; a brand or place that looks like "First Last" may be removed.
  Review `name_removed` rows and spot-check; tune `BRANDS`/`BASE_COMMON` in `src/scrub_text.py`.
- One-off re-scrub of already-stored payloads (idempotent): `python -m src.scrub_pipeline rescrub`, then rebuild (`run_filter`, `phase2 build`, `phase2 link`).
- Check every CSV/report: `python -m src.leak_check` (add `--fix` to scrub Markdown tables in place).
