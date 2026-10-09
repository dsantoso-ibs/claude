"""size_band: descriptive project size from the best available valuation. Never used to include or exclude.

Bands: unknown | under_250k | 250k_to_5m | over_5m  (thresholds in config.yaml: size_band).
Best available valuation, in order:
  permit project    own max total_job_valuation (> placeholder) -> linked Plan Review application -> unknown
  plan review       own valuation (> placeholder)               -> linked permit project's own valuation -> unknown
  site plan         linked permit project's resolved size (score >= link_score) -> Plan Review application at the same
                    address applied on/after submission -> unknown
A reported valuation <= unknown_max_usd ($0/$1) is a placeholder and counts as unknown.
"""
from __future__ import annotations
from collections import Counter

BANDS = ["unknown", "under_250k", "250k_to_5m", "over_5m"]


def band(value: float | None, scfg: dict) -> str:
    if value is None or value <= scfg["unknown_max_usd"]:
        return "unknown"
    if value < scfg["band_250k"]:
        return "under_250k"
    return "250k_to_5m" if value <= scfg["band_5m"] else "over_5m"


def assign(con, cfg: dict) -> dict[str, dict[str, int]]:
    sc, lc = cfg["size_band"], cfg["linking"]
    ok = lambda v: v is not None and v > sc["unknown_max_usd"]
    permit_own = {r["source_id"]: r["valuation"] for r in con.execute("SELECT source_id, valuation FROM candidates WHERE source='austin'")}
    pr_own = {r["id"]: r["valuation"] for r in con.execute("SELECT id, valuation FROM plan_review_candidates")}
    pr_by_project: dict[str, list[float]] = {}
    for r in con.execute("SELECT pr_id, project_key, score FROM plan_review_permit_links WHERE score >= ?", (lc["link_score"],)):
        if ok(pr_own.get(r["pr_id"])):
            pr_by_project.setdefault(r["project_key"], []).append(pr_own[r["pr_id"]])
    # permit projects
    resolved: dict[str, tuple[float | None, str]] = {}
    for key, v in permit_own.items():
        if ok(v):
            resolved[key] = (v, "own")
        elif key in pr_by_project:
            resolved[key] = (max(pr_by_project[key]), "linked_plan_review")
        else:
            resolved[key] = (None, "none")
    out: dict[str, Counter] = {"permit_projects": Counter(), "plan_review": Counter(), "site_plans": Counter()}
    for key, (v, src) in resolved.items():
        b = band(v, sc); out["permit_projects"][b] += 1
        con.execute("UPDATE candidates SET size_band=?, size_usd=?, size_source=? WHERE source='austin' AND source_id=?", (b, v, src, key))
    # plan review
    prl: dict[int, list[float]] = {}
    for r in con.execute("SELECT pr_id, project_key FROM plan_review_permit_links WHERE score >= ?", (lc["link_score"],)):
        v = permit_own.get(r["project_key"])
        if ok(v):
            prl.setdefault(r["pr_id"], []).append(v)
    for pid, v in pr_own.items():
        if ok(v):
            val, src = v, "own"
        elif pid in prl:
            val, src = max(prl[pid]), "linked_permit"
        else:
            val, src = None, "none"
        b = band(val, sc); out["plan_review"][b] += 1
        con.execute("UPDATE plan_review_candidates SET size_band=?, size_usd=?, size_source=? WHERE id=?", (b, val, src, pid))
    # site plans: via linked permit project (resolved size), else a Plan Review application at the same address (applied on/after submission)
    pr_by_addr: dict[str, list[tuple[str, float]]] = {}
    for r in con.execute("SELECT address_norm, applied_date, valuation FROM plan_review_candidates WHERE address_norm != ''"):
        if ok(r["valuation"]) and r["applied_date"]:
            pr_by_addr.setdefault(r["address_norm"], []).append((r["applied_date"], r["valuation"]))
    spl: dict[int, list[float]] = {}
    for r in con.execute("SELECT case_id, project_key FROM site_plan_permit_links WHERE score >= ?", (lc["link_score"],)):
        v = resolved.get(r["project_key"], (None, ""))[0]
        if ok(v):
            spl.setdefault(r["case_id"], []).append(v)
    for r in con.execute("SELECT id, address_norm, submitted_date FROM site_plan_candidates").fetchall():
        v, src = (max(spl[r["id"]]), "linked_permit") if r["id"] in spl else (None, "none")
        if v is None and r["submitted_date"]:
            pv = [val for d, val in pr_by_addr.get(r["address_norm"], ()) if d >= r["submitted_date"]]
            if pv:
                v, src = max(pv), "linked_plan_review"
        b = band(v, sc); out["site_plans"][b] += 1
        con.execute("UPDATE site_plan_candidates SET size_band=?, size_usd=?, size_source=? WHERE id=?", (b, v, src, r["id"]))
    con.commit()
    return {k: {b: c[b] for b in BANDS} for k, c in out.items()}
