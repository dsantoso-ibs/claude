"""M1: fetch -> raw_permits. Idempotent (upsert on source+source_id). Personal-data fields are dropped first.

Usage: python -m src.ingest [austin] [--days N]   (first run = backfill; later runs = delta w/ overlap)
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta, timezone

from src import config as cfgmod
from src.schema import connect
from src.sources.socrata import SocrataClient


def scrub(row: dict, drop_fields: list[str]) -> dict:
    return {k: v for k, v in row.items() if k not in drop_fields}


def ingest(con, client, source: str, scfg: dict, cfg: dict, *, days: int | None = None) -> dict:
    now = datetime.now(timezone.utc)
    last = con.execute("SELECT MAX(started_at) AS t FROM runs WHERE source=? AND notes LIKE 'ok%'", (source,)).fetchone()["t"]
    if days is None:
        if last:
            days = (now - datetime.fromisoformat(last)).days + cfg["ingest"]["delta_overlap_days"]
            mode = "delta"
        else:
            days, mode = cfg["ingest"]["backfill_days"], "backfill"
    else:
        mode = "manual"
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    df, vf = scfg["date_field"], scfg["field_map"]["valuation"]
    where = f"{df} >= '{since}' AND {vf} >= {scfg['ingest_min_valuation_usd']}"
    run_id = con.execute("INSERT INTO runs(started_at, source, rows_fetched, rows_new, notes) VALUES(?,?,0,0,?)",
                         (now.isoformat(), source, f"started {mode} since {since[:10]}")).lastrowid
    fetched = new = 0
    for row in client.iter_rows(scfg["dataset_id"], where=where, order=":id", page_size=cfg["socrata"]["page_size"]):
        sid = row[scfg["field_map"]["permit_number"]]
        fetched += 1
        exists = con.execute("SELECT 1 FROM raw_permits WHERE source=? AND source_id=?", (source, sid)).fetchone()
        con.execute("INSERT INTO raw_permits(source, source_id, fetched_at, payload_json) VALUES(?,?,?,?) "
                    "ON CONFLICT(source, source_id) DO UPDATE SET fetched_at=excluded.fetched_at, payload_json=excluded.payload_json",
                    (source, sid, now.isoformat(), json.dumps(scrub(row, scfg["drop_fields"]))))
        new += 0 if exists else 1
    con.execute("UPDATE runs SET rows_fetched=?, rows_new=?, notes=? WHERE id=?",
                (fetched, new, f"ok {mode} since {since[:10]}", run_id))
    con.commit()
    return {"mode": mode, "since": since[:10], "fetched": fetched, "new": new}


def main(argv: list[str]) -> None:
    source = next((a for a in argv if not a.startswith("--")), "austin")
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else None
    cfg = cfgmod.load()
    scfg = cfg["sources"][source]
    s = cfg["socrata"]
    client = SocrataClient(scfg["domain"], timeout=s["timeout_seconds"], max_retries=s["max_retries"],
                           backoff_base=s["backoff_base_seconds"])
    con = connect(cfgmod.DB_PATH)
    print(ingest(con, client, source, scfg, cfg, days=days))


if __name__ == "__main__":
    main(sys.argv[1:])
