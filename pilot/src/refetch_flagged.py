"""Targeted repair: re-fetch the ORIGINAL text of every currently flagged row (`_name_removed`) from the source, re-apply the person-field drop and
the current scrubber, and store the result. Use after changing the scrubber rules (a full re-fetch is not needed: only flagged rows can be over-scrubbed).
   python -m src.refetch_flagged"""
from __future__ import annotations
import json

from src import config as cfgmod
from src.ingest import scrub as scrub_permit
from src.phase2_ingest import scrub as scrub_phase2
from src.schema import connect
from src.scrub_pipeline import FIELDS, build_scrubber, scrub_payloads
from src.sources.socrata import SocrataClient

SOURCES = {"raw_permits": ("austin", "permit_number"), "raw_site_plans": ("site_plans", "folderrsn"), "raw_plan_reviews": ("plan_review", "permit_number")}


def main() -> dict:
    cfg = cfgmod.load(); con = connect(cfgmod.DB_PATH); sc = build_scrubber(con); out = {}
    for table, (source, idf) in SOURCES.items():
        scfg = cfg["sources"][source]; client = SocrataClient(scfg["domain"])
        ids = [r["source_id"] for r in con.execute(f"SELECT source_id FROM {table} WHERE payload_json LIKE '%\"_name_removed\": true%'")]
        changed = still = 0
        for i in range(0, len(ids), 60):
            chunk = ids[i:i + 60]
            where = f"{idf} in (" + ",".join("'" + s.replace("'", "''") + "'" for s in chunk) + ")"
            rows = client.query(scfg["dataset_id"], where=where, limit=200)
            payloads = [scrub_permit(r, scfg["drop_fields"]) if source == "austin" else scrub_phase2(source, r, scfg) for r in rows]
            scrub_payloads(payloads, table, sc)
            for r, p in zip(rows, payloads):
                sid = str(r[idf])
                old = con.execute(f"SELECT payload_json FROM {table} WHERE source=? AND source_id=?", (source, sid)).fetchone()
                if old and old[0] != json.dumps(p):
                    con.execute(f"UPDATE {table} SET payload_json=? WHERE source=? AND source_id=?", (json.dumps(p), source, sid)); changed += 1
                still += bool(p.get("_name_removed"))
        out[table] = {"refetched": len(ids), "payloads_changed": changed, "still_flagged": still}
    con.commit()
    return out


if __name__ == "__main__":
    print(main())
