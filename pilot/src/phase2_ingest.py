"""M7.1: idempotent ingest of Site Plan Cases / Plan Review Cases into raw tables.
Person fields are dropped, and organization fields that look like individuals are nulled, BEFORE storage.

Usage: python -m src.phase2_ingest [site_plans|plan_review ...] [--months N]
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta, timezone

from src import config as cfgmod
from src.entities import clean_entity
from src.schema import connect
from src.sources.socrata import SocrataClient

TABLES = {"site_plans": "raw_site_plans", "plan_review": "raw_plan_reviews"}
ORG_FIELDS = {"site_plans": ["owner_organization_name", "applicant_organization_name"],
              "plan_review": ["owner_organization_name", "applicant_organization_name", "other_organization_name"]}


def scrub(source: str, row: dict, scfg: dict) -> dict:
    out = {k: v for k, v in row.items() if k not in scfg["drop_fields"]}
    had_person = any(row.get(f) for f in scfg["drop_fields"] if "full" in f)
    for f in ORG_FIELDS[source]:
        if f in out:
            out[f], ind = clean_entity(out[f])
            if ind and f.startswith("owner"):
                out["_owner_is_individual"] = True
    if "owner_organization_name" in out and not out.get("owner_organization_name") and \
            (row.get("owner_fullname") or row.get("owner_full_name")):
        out["_owner_is_individual"] = True   # only a person was recorded; name not stored
    return {k: v for k, v in out.items() if v is not None}


def ingest(con, client, source: str, cfg: dict, *, months: int | None = None) -> dict:
    scfg = cfg["sources"][source]
    table = TABLES[source]
    now = datetime.now(timezone.utc)
    last = con.execute("SELECT MAX(started_at) AS t FROM runs WHERE source=? AND notes LIKE 'ok%'", (source,)).fetchone()["t"]
    if months is None and last:
        days = (now - datetime.fromisoformat(last)).days + scfg["delta_overlap_days"]; mode = "delta"
    else:
        days = int((months or scfg["backfill_months"]) * 30.5); mode = "backfill" if months is None else "manual"
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    where = f"{scfg['date_field']} >= '{since}'"
    if scfg.get("ingest_where"):
        where += f" AND ({scfg['ingest_where']})"
    run_id = con.execute("INSERT INTO runs(started_at, source, rows_fetched, rows_new, notes) VALUES(?,?,0,0,?)",
                         (now.isoformat(), source, f"started {mode}")).lastrowid
    fetched = new = scrubbed = 0
    from src.scrub_pipeline import build_scrubber, chunks, scrub_payloads
    scrubber = build_scrubber(con)
    for batch in chunks(r for r in client.iter_rows(scfg["dataset_id"], where=where, order=":id", page_size=cfg["socrata"]["page_size"]) if r.get(scfg["id_field"])):
        payloads = [scrub(source, r, scfg) for r in batch]
        scrubbed += scrub_payloads(payloads, table, scrubber)                   # personal names in free text are removed BEFORE storage
        for row, payload in zip(batch, payloads):
            sid = row.get(scfg["id_field"])
            fetched += 1
            exists = con.execute(f"SELECT 1 FROM {table} WHERE source=? AND source_id=?", (source, sid)).fetchone()
            con.execute(f"INSERT INTO {table}(source, source_id, fetched_at, payload_json) VALUES(?,?,?,?) "
                        "ON CONFLICT(source, source_id) DO UPDATE SET fetched_at=excluded.fetched_at, payload_json=excluded.payload_json",
                        (source, str(sid), now.isoformat(), json.dumps(payload)))
            new += 0 if exists else 1
    con.execute("UPDATE runs SET rows_fetched=?, rows_new=?, notes=? WHERE id=?", (fetched, new, f"ok {mode} since {since[:10]}", run_id))
    con.commit()
    return {"source": source, "mode": mode, "since": since[:10], "fetched": fetched, "new": new, "rows_with_name_removed": scrubbed}


def main(argv: list[str]) -> None:
    months = int(argv[argv.index("--months") + 1]) if "--months" in argv else None
    sources = [a for a in argv if a in TABLES] or list(TABLES)
    cfg = cfgmod.load(); s = cfg["socrata"]
    con = connect(cfgmod.DB_PATH)
    for src in sources:
        client = SocrataClient(cfg["sources"][src]["domain"], timeout=s["timeout_seconds"], max_retries=s["max_retries"],
                               backoff_base=s["backoff_base_seconds"])
        print(ingest(con, client, src, cfg, months=months))


if __name__ == "__main__":
    main(sys.argv[1:])
