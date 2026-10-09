"""Unified search over permit projects, site plan cases and Plan Review applications.

Table project_index (one row per record) with the searchable attributes use_class, description, applicant_org, contractor_name, address
(plus type, subtype, size band and recency) and an FTS5 table over the text attributes. Nothing here includes or excludes records.

  python -m src.index                                   rebuild
  python -m src.index search "tenant finish out" [--type remodel] [--subtype tenant_finish_out] [--stage permit_issued] [--limit 20]
Results are ordered newest first (recency_days ascending).
"""
from __future__ import annotations
import re
import sys

from src import config as cfgmod
from src.schema import connect

COLS = ["stage", "ref_id", "passed", "in_default", "project_type", "remodel_subtype", "size_band", "use_class", "description", "applicant_org",
        "contractor_name", "address", "address_norm", "owner_entity", "status", "applied_date", "issued_date", "recency_date", "recency_days", "name_removed", "remodel_list"]


def rebuild(con) -> dict[str, int]:
    con.executescript("DROP TABLE IF EXISTS project_fts; DROP TABLE IF EXISTS project_index;"
                      "CREATE TABLE project_index(id INTEGER PRIMARY KEY, " + ", ".join(COLS) + ");")
    con.execute("""INSERT INTO project_index(stage, ref_id, passed, in_default, project_type, remodel_subtype, size_band, use_class, description, applicant_org,
                       contractor_name, address, address_norm, owner_entity, status, applied_date, issued_date, recency_date, recency_days, name_removed)
                   SELECT 'permit_issued', c.id, f.passed, c.in_default, c.project_type, c.remodel_subtype, c.size_band, c.use_class, c.description, c.applicant_org,
                       c.contractor_name, c.address_raw, c.address_norm, NULL, c.status, c.applied_date, c.last_issued_date, c.recency_date, c.recency_days, c.name_removed
                   FROM candidates c JOIN filter_results f ON f.candidate_id=c.id WHERE c.source='austin'""")
    con.execute("""INSERT INTO project_index(stage, ref_id, passed, in_default, project_type, remodel_subtype, size_band, use_class, description, applicant_org,
                       contractor_name, address, address_norm, owner_entity, status, applied_date, issued_date, recency_date, recency_days, name_removed)
                   SELECT 'site_plan', id, passed, in_default, project_type, remodel_subtype, size_band, use_class, COALESCE(description, case_name), applicant_org,
                       NULL, address_raw, address_norm, owner_entity, status, submitted_date, approval_date, recency_date, recency_days, name_removed FROM site_plan_candidates""")
    con.execute("""INSERT INTO project_index(stage, ref_id, passed, in_default, project_type, remodel_subtype, size_band, use_class, description, applicant_org,
                       contractor_name, address, address_norm, owner_entity, status, applied_date, issued_date, recency_date, recency_days, name_removed)
                   SELECT 'plan_review', id, passed, in_default, project_type, remodel_subtype, size_band, use_class, COALESCE(description, project_name), applicant_org,
                       NULL, address_raw, address_norm, owner_entity, status, applied_date, issued_date, recency_date, recency_days, name_removed FROM plan_review_candidates""")
    con.execute("UPDATE project_index SET remodel_list = CASE WHEN project_type != 'remodel' THEN NULL WHEN remodel_subtype = 'repair_or_other' THEN 'bucket' ELSE 'default' END")
    con.execute("CREATE VIRTUAL TABLE project_fts USING fts5(use_class, description, applicant_org, contractor_name, address, owner_entity, content='')")
    con.execute("INSERT INTO project_fts(rowid, use_class, description, applicant_org, contractor_name, address, owner_entity) "
                "SELECT id, use_class, description, applicant_org, contractor_name, address, owner_entity FROM project_index")
    con.commit()
    return {r[0]: r[1] for r in con.execute("SELECT stage, COUNT(*) FROM project_index GROUP BY stage")}


def search(con, text: str, *, ptype: str | None = None, subtype: str | None = None, stage: str | None = None, passed_only: bool = True, limit: int = 20,
           with_bucket: bool = False):
    """Newest first. The repair_or_other remodel bucket is hidden unless with_bucket=True or subtype='repair_or_other'."""
    q = " ".join(f'"{t}"' for t in re.findall(r"\w+", text)) or '""'
    sql = ("SELECT p.* FROM project_fts f JOIN project_index p ON p.id=f.rowid WHERE project_fts MATCH ?"
           + (" AND p.passed=1" if passed_only else "") + (" AND p.project_type=?" if ptype else "") + (" AND p.remodel_subtype=?" if subtype else "")
           + (" AND p.stage=?" if stage else "")
           + ("" if (with_bucket or subtype == "repair_or_other") else " AND COALESCE(p.remodel_list,'') != 'bucket'") + " ORDER BY p.recency_days ASC LIMIT ?")
    args = [q] + [a for a in (ptype, subtype, stage) if a] + [limit]
    return [dict(r) for r in con.execute(sql, args)]


def main(argv: list[str]) -> None:
    con = connect(cfgmod.DB_PATH)
    if argv and argv[0] == "search":
        flags = {"--with-bucket"}
        opt = {a[2:]: argv[i + 2] for i, a in enumerate(argv[1:]) if a.startswith("--") and a not in flags}
        words = [a for i, a in enumerate(argv[1:]) if not a.startswith("--") and not (i > 0 and argv[i].startswith("--") and argv[i] not in flags)]
        for r in search(con, " ".join(words), ptype=opt.get("type"), subtype=opt.get("subtype"), stage=opt.get("stage"), limit=int(opt.get("limit", 20)), with_bucket="with-bucket" in argv):
            print(f"{r['recency_days']:>5} d | {r['stage']:<13} | {r['project_type']}/{r['remodel_subtype'] or '-'} | {r['address'] or r['address_norm']} | "
                  f"{(r['applicant_org'] or '')[:24]} | {(r['contractor_name'] or '')[:24]} | {' '.join((r['description'] or '').split())[:70]}{' [name removed]' if r['name_removed'] else ''}")
    else:
        print(rebuild(con))


if __name__ == "__main__":
    main(sys.argv[1:])
