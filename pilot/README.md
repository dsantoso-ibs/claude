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
