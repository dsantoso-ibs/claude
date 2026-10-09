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
