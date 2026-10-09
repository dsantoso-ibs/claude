"""Phase 2 (M7.2-M7.3, M7.5): normalize + filter site plan / plan review cases, link them to issued-permit projects,
and produce manual-check sheets.

Usage: python -m src.phase2 build | link | sheets
"""
from __future__ import annotations
import csv
import json
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

from rapidfuzz import fuzz

from src import config as cfgmod
from src.baseline import haversine_m, score_pair
from src.filter import evaluate
from src.entities import clean_org
from src.normalize import normalize_address
from src.schema import connect


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def classify_use(land_use: str | None, rules: list) -> str:
    if not land_use or not land_use.strip():
        return "unknown_use"
    for rx, cls in rules:
        if re.search(rx, land_use):
            return cls
    return "unknown_use"


def site_plan_address(r: dict) -> str:
    parts = [r.get("street_number"), r.get("street_prefix"), r.get("street_name"), r.get("street_type"), r.get("street_direction")]
    return normalize_address(" ".join(p for p in parts if p))


def evaluate_site_plan(c: dict, fc: dict) -> tuple[bool, str | None]:
    if not c.get("submitted_date"):
        return False, "no_submission_date"
    if any((c["status"] or "").lower().startswith(x.lower()) for x in fc["exclude_statuses"]):
        return False, "status_excluded"
    if fc.get("exclude_name_regex") and re.search(fc["exclude_name_regex"], c.get("case_name") or ""):
        return False, "demolition_only"
    if (c["work"] or "") in fc["exclude_work"]:
        return False, "work_not_building_project"
    cls = c["use_class"]
    if cls == "excluded_infrastructure":
        return False, "infrastructure_or_boat_dock"
    if cls == "single_family":
        return False, "single_family_or_duplex"
    if cls == "unknown_use":
        return False, "unknown_use"
    if cls not in fc["include_classes"]:
        return False, "use_not_included"
    return True, None


def build_site_plans(con, cfg: dict) -> dict[str, int]:
    fc = cfg["site_plan_filters"]
    now = datetime.now(timezone.utc).isoformat()
    counts: dict[str, int] = defaultdict(int)
    for row in con.execute("SELECT payload_json FROM raw_site_plans").fetchall():
        r = json.loads(row["payload_json"])
        use = r.get("proposed_land_use")
        c = dict(case_number=r.get("permit_number"), case_name=r.get("case_name"), address_norm=site_plan_address(r),
                 lat=_f(r.get("latitude")), lon=_f(r.get("longitude")), proposed_use=use, use_class=classify_use(use, fc["use_rules"]),
                 work=r.get("work"), status=r.get("status"), submitted_date=(r.get("application_start_date") or "")[:10] or None,
                 approval_date=(r.get("approval_date") or "")[:10] or None, applicant_org=clean_org(r.get("applicant_organization_name")),
                 owner_entity=clean_org(r.get("owner_organization_name")), owner_is_individual=int(bool(r.get("_owner_is_individual"))),
                 description=(r.get("description_of_work") or "")[:500] or None,
                 address_raw=" ".join(str(r.get(k)) for k in ("street_number", "street_prefix", "street_name", "street_type", "street_direction") if r.get(k)) or None)
        sz = [f"{int(_f(r[k]))} {u}" for k, u in (("proposed_no_of_units", "units"), ("proposed_bldg_sq_footage", "sqft"),
                                                  ("gross_site_area_acres", "acres")) if _f(r.get(k)) and _f(r[k]) > 0]
        c["size_hint"] = "; ".join(sz) or None
        c["multifamily_hint"] = int(c["use_class"] == "multifamily" or bool(re.search(fc["multifamily_name_regex"], c["case_name"] or "")))
        passed, reason = evaluate_site_plan(c, fc)
        con.execute("INSERT INTO site_plan_candidates(folderrsn, case_number, case_name, address_norm, lat, lon, proposed_use, use_class, work,"
                    " status, submitted_date, approval_date, applicant_org, owner_entity, owner_is_individual, size_hint, multifamily_hint,"
                    " first_seen_at, passed, exclude_reason, description, address_raw, name_removed) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(folderrsn) DO UPDATE SET case_number=excluded.case_number, case_name=excluded.case_name,"
                    " address_norm=excluded.address_norm, lat=excluded.lat, lon=excluded.lon, proposed_use=excluded.proposed_use,"
                    " use_class=excluded.use_class, work=excluded.work, status=excluded.status, submitted_date=excluded.submitted_date,"
                    " approval_date=excluded.approval_date, applicant_org=excluded.applicant_org, owner_entity=excluded.owner_entity,"
                    " owner_is_individual=excluded.owner_is_individual, size_hint=excluded.size_hint,"
                    " multifamily_hint=excluded.multifamily_hint, passed=excluded.passed, exclude_reason=excluded.exclude_reason,"
                    " description=excluded.description, address_raw=excluded.address_raw, name_removed=excluded.name_removed",
                    (r["folderrsn"], c["case_number"], c["case_name"], c["address_norm"], c["lat"], c["lon"], use, c["use_class"], c["work"],
                     c["status"], c["submitted_date"], c["approval_date"], c["applicant_org"], c["owner_entity"], c["owner_is_individual"],
                     c["size_hint"], c["multifamily_hint"], now, int(passed), reason, c["description"], c["address_raw"], int(bool(r.get("_name_removed")))))
        counts["passed" if passed else reason] += 1
    con.commit()
    return dict(counts)


def build_plan_reviews(con, cfg: dict) -> dict[str, int]:
    fc, pc = cfg["filters"], cfg["plan_review_filters"]
    now = datetime.now(timezone.utc).isoformat()
    counts: dict[str, int] = defaultdict(int)
    for row in con.execute("SELECT payload_json FROM raw_plan_reviews").fetchall():
        r = json.loads(row["payload_json"])
        loc = r.get("location") or {}
        cand = dict(valuation=_f(r.get("total_job_valuation")) or 0, permit_type="BP", work_class=r.get("work_class") or "",
                    use_class=r.get("sub_type") or "", status=r.get("status_current") or "",
                    description=f"{r.get('project_name') or ''} {r.get('folder_description') or ''}")
        passed, reason = evaluate(cand, fc)
        if passed and any(cand["status"].startswith(x) for x in pc["extra_exclude_statuses"]):
            passed, reason = False, "status_not_live"
        con.execute("INSERT INTO plan_review_candidates(permit_number, project_name, address_norm, lat, lon, valuation, work_class, use_class, status,"
                    " applied_date, issued_date, owner_entity, owner_is_individual, applicant_org, units, passed, exclude_reason, description, address_raw, name_removed)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(permit_number) DO UPDATE SET status=excluded.status,"
                    " valuation=excluded.valuation, issued_date=excluded.issued_date, passed=excluded.passed, exclude_reason=excluded.exclude_reason,"
                    " lat=excluded.lat, lon=excluded.lon, address_norm=excluded.address_norm, description=excluded.description, address_raw=excluded.address_raw,"
                    " applied_date=excluded.applied_date, owner_entity=excluded.owner_entity, applicant_org=excluded.applicant_org, name_removed=excluded.name_removed",
                    (r["permit_number"], r.get("project_name"), normalize_address(r.get("project_name")), _f(loc.get("latitude")),
                     _f(loc.get("longitude")), cand["valuation"], cand["work_class"], cand["use_class"], cand["status"],
                     (r.get("applied_date") or "")[:10] or None, (r.get("issued_date") or "")[:10] or None,
                     clean_org(r.get("owner_organization_name")), int(bool(r.get("_owner_is_individual"))), clean_org(r.get("applicant_organization_name")),
                     _f(r.get("number_of_units")), int(passed), reason,
                     (r.get("folder_description") or "")[:500] or None, r.get("project_name"), int(bool(r.get("_name_removed")))))
        counts["passed" if passed else reason] += 1
    con.commit()
    return dict(counts)


# ---------------------------------------------------------------- linking
def _cells(lat, lon, step=0.002):
    ci, cj = int(lat / step), int(lon / step)
    return [(ci + a, cj + b) for a in (-1, 0, 1) for b in (-1, 0, 1)]


def link_cases(cases: list[dict], permits: list[dict], date_field: str, lcfg: dict, *, compat=None) -> list[tuple]:
    """Returns (case_id, project_key, score, method). A pair needs permit issued >= case date; blocking by geo cell and street token."""
    by_cell, by_street = defaultdict(list), defaultdict(list)
    for p in permits:
        if p["lat"] is not None and p["lon"] is not None:
            by_cell[(int(p["lat"] / 0.002), int(p["lon"] / 0.002))].append(p)
        toks = (p["address_norm"] or "").split()
        if len(toks) >= 2:
            by_street[(toks[0], toks[1])].append(p)
    out = []
    for c in cases:
        cand: dict[str, dict] = {}
        if c["lat"] is not None and c["lon"] is not None:
            for cell in _cells(c["lat"], c["lon"]):
                for p in by_cell.get(cell, ()):
                    cand[p["source_id"]] = p
        toks = (c["address_norm"] or "").split()
        if len(toks) >= 2:
            for p in by_street.get((toks[0], toks[1]), ()):
                cand[p["source_id"]] = p
        for p in cand.values():
            if not p["issued_date"] or not c[date_field] or p["issued_date"] < c[date_field]:
                continue
            if compat and not compat(c, p):
                continue
            s, m = score_pair({"address_norm": c["address_norm"], "lat": c["lat"], "lon": c["lon"], "description": c.get("name") or ""},
                              {"address_norm": p["address_norm"], "lat": p["lat"], "lon": p["lon"], "name": p.get("description") or ""},
                              lcfg["geo_radius_m"])
            if s >= lcfg["review_score"]:
                org = c.get("org") or ""
                if org and p.get("contractor_name") and fuzz.token_set_ratio(org, p["contractor_name"]) >= lcfg["supporting_name_ratio"]:
                    s = min(1.0, s + lcfg["supporting_name_bonus"]); m += "+org"
                out.append((c["id"], p["source_id"], round(s, 3), m))
    return out


def link_all(con, cfg: dict) -> dict[str, int]:
    lcfg = cfg["linking"]
    permits = [dict(r) for r in con.execute(
        "SELECT c.source_id, c.address_norm, c.lat, c.lon, c.issued_date, c.description, c.contractor_name, c.work_class, f.passed "
        "FROM candidates c JOIN filter_results f ON f.candidate_id=c.id WHERE c.source='austin'")]
    sp_permits = [p for p in permits if set((p["work_class"] or "").split("|")) & set(lcfg["site_plan_permit_work_classes"])]
    sp = [dict(r, name=r["case_name"], org=r["owner_entity"] or r["applicant_org"], submitted=r["submitted_date"])
          for r in con.execute("SELECT * FROM site_plan_candidates WHERE passed=1")]
    con.execute("DELETE FROM site_plan_permit_links")
    links = link_cases(sp, sp_permits, "submitted_date", lcfg)
    con.executemany("INSERT OR REPLACE INTO site_plan_permit_links VALUES(?,?,?,?)", links)
    pr = [dict(r, name=r["project_name"], org=r["owner_entity"] or r["applicant_org"])
          for r in con.execute("SELECT * FROM plan_review_candidates WHERE passed=1")]
    con.execute("DELETE FROM plan_review_permit_links")
    # an application links only to a permit with the same work class (a New application is not satisfied by a tenant remodel permit)
    same_work = lambda c, p: (c.get("work_class") or "") in set((p.get("work_class") or "").split("|"))
    plinks = link_cases(pr, permits, "applied_date", lcfg, compat=same_work)
    con.executemany("INSERT OR REPLACE INTO plan_review_permit_links VALUES(?,?,?,?)", plinks)
    con.commit()
    return {"site_plan_links": len(links), "plan_review_links": len(plinks)}


# ---------------------------------------------------------------- sheets
def make_sheets(con, cfg: dict) -> dict[str, int]:
    out = cfgmod.ROOT / "reports"
    rnd = random.Random(cfg["label_sample"]["seed"])
    lc = cfg["linking"]
    from src.report_phase2 import linked_best
    from src.label_sheets import make_sheets as label_sheets
    labels = label_sheets(con, cfg)
    # hand-check sheets: 20 passed + 20 excluded, 20 linked pairs + 10 unlinked
    cases = [dict(r) for r in con.execute("SELECT * FROM site_plan_candidates")]
    passed = [c for c in cases if c["in_default"]]; excl = [c for c in cases if not c["passed"]]
    with open(out / "handcheck-site-plans.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["set", "case_number", "case_name", "proposed_use", "use_class", "work", "status", "submitted", "exclude_reason", "name_removed", "agree (y/n)", "note"])
        for name, pool in (("passed", passed), ("excluded", excl)):
            for c in rnd.sample(pool, min(20, len(pool))):
                w.writerow([name, c["case_number"], c["case_name"], c["proposed_use"], c["use_class"], c["work"], c["status"],
                            c["submitted_date"], c["exclude_reason"] or "", c["name_removed"] or 0, "", ""])
    best = linked_best(con, cfg)
    linked_ids = set(best)
    pm = {r["source_id"]: dict(r) for r in con.execute("SELECT source_id, address_norm, valuation, issued_date, description FROM candidates WHERE source='austin'")}
    with open(out / "handcheck-site-plan-links.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["set", "case_number", "case_name", "case_address", "submitted", "permit_project", "permit_address",
                                        "permit_issued", "permit_valuation", "score", "method", "correct (y/n)", "note"])
        byid = {c["id"]: c for c in cases}
        for cid in rnd.sample(sorted(linked_ids), min(20, len(linked_ids))):
            b = best[cid]; c = byid[cid]; p = pm[b["project_key"]]
            w.writerow(["linked", c["case_number"], c["case_name"], c["address_norm"], c["submitted_date"], b["project_key"], p["address_norm"],
                        p["issued_date"], p["valuation"], b["score"], b["method"], "", ""])
        unl = [c for c in passed if c["id"] not in linked_ids]
        for c in rnd.sample(unl, min(10, len(unl))):
            w.writerow(["unlinked", c["case_number"], c["case_name"], c["address_norm"], c["submitted_date"], "", "", "", "", "", "", "", ""])
    return labels


def import_site_plan_labels(con, path: str) -> dict[str, int]:
    """Open-pipeline sheet (stages site_plan_open / plan_review_open) -> pipeline_labels."""
    m = {"y": "in_baseline", "n": "novel", "unsure": "review"}
    counts = {"in_baseline": 0, "novel": 0, "review": 0, "skipped": 0}
    now = datetime.now(timezone.utc).isoformat()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            a = (row["in_baseline (y/n/unsure)"] or "").strip().lower()
            if a not in m or row.get("stage") not in ("site_plan_open", "plan_review_open"):
                counts["skipped"] += 1; continue
            con.execute("INSERT INTO pipeline_labels VALUES(?,?,?,?,?,?) ON CONFLICT(stage, ref_id) DO UPDATE SET label=excluded.label, note=excluded.note, labelled_at=excluded.labelled_at",
                        (row["stage"], int(row["ref_id"]), m[a], "manual", row.get("found_in (ibau/barbour/mps/baucore)") or row.get("note"), now))
            counts[m[a]] += 1
    con.commit()
    return counts


def main(argv: list[str]) -> None:
    cfg = cfgmod.load(); con = connect(cfgmod.DB_PATH)
    cmd = argv[0] if argv else "build"
    if cmd == "build":
        print("site plans:", build_site_plans(con, cfg)); print("plan review:", build_plan_reviews(con, cfg))
    elif cmd == "link":
        print(link_all(con, cfg))
        from src.sizeband import assign
        print(assign(con, cfg))
        from src.project_type import assign as assign_types
        print(assign_types(con, cfg))
        from src.recency import refresh
        from src.index import rebuild
        print(refresh(con)); print(rebuild(con))
    elif cmd == "sheets":
        print(make_sheets(con, cfg))
    elif cmd == "import-labels":
        print(import_site_plan_labels(con, argv[1]))


if __name__ == "__main__":
    main(sys.argv[1:])
