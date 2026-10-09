"""project_type (new_build | shell | addition | remodel) and the default set.

Default set = passed the filter AND project_type in project_type.default_types (new_build, shell, addition). Remodels are kept in the
database and reported separately; nothing is deleted. Rows that fail the filter keep their type for information but are never default.
Site plans (no building work class): linked permit project -> Plan Review at the same address -> name/work hints -> 'unknown'.
"""
from __future__ import annotations
import re
from collections import Counter

from src.remodel import subtype as remodel_subtype

ORDER = ["new_build", "shell", "addition", "remodel"]


def type_from_works(works: str | None, wmap: dict) -> str:
    types = {wmap.get(w) for w in (works or "").split("|") if w}
    types.discard(None)
    for t in ORDER:
        if t in types:
            return t
    return "other"          # demolition, repair, etc. (already excluded by the work-class rule)


def assign(con, cfg: dict) -> dict[str, dict[str, int]]:
    pc, lc = cfg["project_type"], cfg["linking"]
    wmap, default = pc["work_class_map"], set(pc["default_types"])
    out: dict[str, Counter] = {"permit_projects": Counter(), "plan_review": Counter(), "site_plans": Counter()}
    ptype: dict[str, str] = {}
    rc = cfg["filters"]["remodel"]
    for r in con.execute("SELECT c.id, c.source_id, c.work_class, c.description, c.use_class, f.passed FROM candidates c JOIN filter_results f ON f.candidate_id=c.id"):
        t = type_from_works(r["work_class"], wmap); ptype[r["source_id"]] = t
        d = int(bool(r["passed"]) and t in default)
        st = remodel_subtype(r["description"], (r["use_class"] or "").split("|"), rc) if t == "remodel" else None
        con.execute("UPDATE candidates SET project_type=?, in_default=?, remodel_subtype=? WHERE id=?", (t, d, st, r["id"]))
        if r["passed"]:
            out["permit_projects"][t if d else "remodel (separate)" if t == "remodel" else "other"] += 1
    for r in con.execute("SELECT id, work_class, description, project_name, use_class, passed FROM plan_review_candidates"):
        t = type_from_works(r["work_class"], wmap); d = int(bool(r["passed"]) and t in default)
        st = remodel_subtype(f"{r['description'] or ''} {r['project_name'] or ''}", [r["use_class"] or ""], rc) if t == "remodel" else None
        con.execute("UPDATE plan_review_candidates SET project_type=?, in_default=?, remodel_subtype=? WHERE id=?", (t, d, st, r["id"]))
        if r["passed"]:
            out["plan_review"][t if d else "remodel (separate)" if t == "remodel" else "other"] += 1
    # site plans
    perm_issue = {r["source_id"]: r["issued_date"] for r in con.execute("SELECT source_id, issued_date FROM candidates WHERE source='austin'")}
    linked: dict[int, list[tuple[str, str]]] = {}
    for r in con.execute("SELECT case_id, project_key FROM site_plan_permit_links WHERE score >= ?", (lc["link_score"],)):
        if r["project_key"] in ptype and ptype[r["project_key"]] != "other":
            linked.setdefault(r["case_id"], []).append((perm_issue.get(r["project_key"]) or "9999", ptype[r["project_key"]]))
    pr_by_addr: dict[str, list[tuple[str, str]]] = {}
    for r in con.execute("SELECT address_norm, applied_date, project_type FROM plan_review_candidates WHERE address_norm != '' AND applied_date IS NOT NULL"):
        if r["project_type"] in ORDER:
            pr_by_addr.setdefault(r["address_norm"], []).append((r["applied_date"], r["project_type"]))
    for r in con.execute("SELECT id, address_norm, case_name, description, work, submitted_date, passed FROM site_plan_candidates").fetchall():
        t, src = "unknown", "none"
        if r["id"] in linked:
            t, src = min(linked[r["id"]])[1], "linked_permit"          # the first linked permit project
        else:
            pr = [x for x in pr_by_addr.get(r["address_norm"], ()) if r["submitted_date"] and x[0] >= r["submitted_date"]]
            if pr:
                t, src = min(pr)[1], "linked_plan_review"
            elif re.search(pc["site_plan_remodel_name_regex"], r["case_name"] or "") or (r["work"] or "") in pc["site_plan_remodel_work"]:
                t, src = "remodel", "name_or_work_hint"
        d = int(bool(r["passed"]) and (t in default or (t == "unknown" and pc["site_plan_unknown_in_default"])))
        st = remodel_subtype(f"{r['case_name'] or ''} {r['description'] or ''}", [], rc) if t == "remodel" else None
        con.execute("UPDATE site_plan_candidates SET project_type=?, type_source=?, in_default=?, remodel_subtype=? WHERE id=?", (t, src, d, st, r["id"]))
        if r["passed"]:
            out["site_plans"][t if d else "remodel (separate)" if t == "remodel" else "other"] += 1
    con.commit()
    return {k: dict(v) for k, v in out.items()}
