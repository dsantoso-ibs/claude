"""Manual novelty-label sheets: 30 projects from the DEFAULT set only (new_build/shell/addition), stratified by stage then size_band.

Stages: site_plan_open (default open site plan cases), plan_review_open (default open Plan Review applications), permit_issued (default
permit projects issued in the last 12 months). Remodels are never sampled (so no unknown-size remodels either).
Outputs: reports/manual-labels-austin.csv (permit_issued) and reports/manual-labels-site-plans.csv (the two open stages).
Import answers: python -m src.baseline import-labels <austin csv>   |   python -m src.phase2 import-labels <site-plans csv>
"""
from __future__ import annotations
import csv
import random
from collections import defaultdict

from src import config as cfgmod

BANDS = ["unknown", "under_250k", "250k_to_5m", "over_5m"]
ANSWER = ["in_baseline (y/n/unsure)", "found_in (ibau/barbour/mps/baucore)", "note"]


def stratified(pool: list[dict], n: int, quota: dict, rnd: random.Random) -> list[dict]:
    """n items spread over size bands by quota; shortfalls filled from remaining bands, known sizes first."""
    by = defaultdict(list)
    for r in pool:
        by[r.get("size_band") or "unknown"].append(r)
    for b in by:
        rnd.shuffle(by[b])
    picked: list[dict] = []
    for b in BANDS:
        picked += [by[b].pop() for _ in range(min(quota.get(b, 0), len(by[b])))]
    for b in ("over_5m", "250k_to_5m", "under_250k", "unknown"):      # fill the shortfall
        while len(picked) < n and by[b]:
            picked.append(by[b].pop())
    return picked[:n]


def make_sheets(con, cfg: dict) -> dict:
    from src.report_phase2 import open_pipeline, pr_open_pipeline
    ls = cfg["label_sample"]; rnd = random.Random(ls["seed"]); out = cfgmod.ROOT / "reports"
    win = "date('now','-%d day')" % cfg["ingest"]["phase1_window_days"]
    permits = [dict(r) for r in con.execute(
        f"SELECT c.* FROM candidates c JOIN filter_results f ON f.candidate_id=c.id WHERE c.source='austin' AND f.passed=1 AND c.in_default=1 AND c.issued_date>={win}")]
    pools = {"site_plan_open": open_pipeline(con, cfg), "plan_review_open": pr_open_pipeline(con, cfg), "permit_issued": permits}
    for name, pool in pools.items():                                  # guard: default set only, never remodels
        assert all(r["project_type"] != "remodel" and r.get("in_default") for r in pool), name
    chosen = {st: stratified(pools[st], ls["per_stage"][st], ls["band_quota"], rnd) for st in pools}
    summary = {st: {b: sum(1 for r in rows if (r.get("size_band") or "unknown") == b) for b in BANDS} for st, rows in chosen.items()}
    summary["pool_sizes"] = {st: len(p) for st, p in pools.items()}

    with open(out / "manual-labels-austin.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["candidate_id", "stage", "size_band", "project_type", "address", "size_usd", "use_class", "work_class", "contractor", "issued", "description"] + ANSWER)
        for r in chosen["permit_issued"]:
            w.writerow([r["id"], "permit_issued", r["size_band"] or "unknown", r["project_type"], r["address_norm"], f"{r['size_usd']:.0f}" if r["size_usd"] else "",
                        r["use_class"][:60], r["work_class"], r["contractor_name"] or "", r["issued_date"], (r["description"] or "")[:140], "", "", ""])
    with open(out / "manual-labels-site-plans.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["stage", "ref_id", "case_or_permit", "name", "address", "size_band", "size_usd", "project_type", "use", "owner_entity", "applicant_org", "status", "date"] + ANSWER)
        for r in chosen["site_plan_open"]:
            w.writerow(["site_plan_open", r["id"], r["case_number"] or "", r["case_name"] or "", r["address_norm"], r["size_band"] or "unknown",
                        f"{r['size_usd']:.0f}" if r["size_usd"] else "", r["project_type"], r["proposed_use"], r["owner_entity"] or "", r["applicant_org"] or "",
                        r["status"], r["submitted_date"], "", "", ""])
        for r in chosen["plan_review_open"]:
            w.writerow(["plan_review_open", r["id"], r["permit_number"], r["project_name"] or "", r["address_norm"], r["size_band"] or "unknown",
                        f"{r['size_usd']:.0f}" if r["size_usd"] else "", r["project_type"], r["use_class"][:40], r["owner_entity"] or "", r["applicant_org"] or "",
                        r["status"], r["applied_date"], "", "", ""])
    return summary
