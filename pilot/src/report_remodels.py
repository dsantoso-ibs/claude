"""Remodel report: default remodel list (tenant_finish_out + interior_remodel) vs the separate repair_or_other bucket; subtype volume per week,
applicant/contractor coverage, non-project exclusions, description-scrub flags, newest-first CSVs.
Usage: python -m src.report_remodels -> reports/remodels-YYYY-MM-DD.md, reports/remodels-12m.csv (default list),
reports/remodels-repair-or-other-12m.csv (bucket).   Remodels are never enriched."""
from __future__ import annotations
import csv
from collections import Counter
from datetime import date, timedelta

from src import config as cfgmod
from src.index import rebuild
from src.recency import refresh
from src.schema import connect

# stage -> (label, does the source carry a contractor?)
STAGES = [("permit_issued", "permit issued (first issue date)", True), ("plan_review", "Plan Review applied", False), ("site_plan", "site plan submitted", False)]
CSV_COLS = ["recency_days", "recency_date", "stage", "remodel_subtype", "size_band", "use_class", "description", "name_removed", "applicant_org", "contractor_name",
            "address", "address_norm", "status", "applied_date", "issued_date"]


def _table_volume(L, kept, subtypes, label_all, d28, d365):
    L += ["| stage | subtype | last 28 days (count) | per week | last 12 months (count) | per week |", "|---|---|---|---|---|---|"]
    for stage, label, _ in STAGES:
        for st in subtypes + [label_all]:
            sel = [r for r in kept if r["stage"] == stage and (st == label_all or r["remodel_subtype"] == st)]
            n28 = sum(1 for r in sel if r["vol_date"] >= d28); n365 = sum(1 for r in sel if r["vol_date"] >= d365)
            b = "**" if st == label_all else ""
            L.append(f"| {label} | {b}{st}{b} | {n28} | {n28 / 4:.1f} | {n365:,} | {n365 / 52:.1f} |")


def _table_coverage(L, kept, subtypes, label_all, d365):
    L += ["| stage | subtype | records | applicant org | contractor | applicant or contractor |", "|---|---|---|---|---|---|"]
    for stage, label, has_c in STAGES:
        for st in subtypes + [label_all]:
            sel = [r for r in kept if r["stage"] == stage and r["vol_date"] >= d365 and (st == label_all or r["remodel_subtype"] == st)]
            n = len(sel) or 1
            a = sum(1 for r in sel if r["applicant_org"]); c = sum(1 for r in sel if r["contractor_name"]); e = sum(1 for r in sel if r["applicant_org"] or r["contractor_name"])
            b = "**" if st == label_all else ""
            L.append(f"| {label} | {b}{st}{b} | {len(sel):,} | {a / n:.0%} | " + (f"{c / n:.0%}" if has_c else "n/a") + f" | {e / n:.0%} |")


def main() -> None:
    cfg = cfgmod.load(); con = connect(cfgmod.DB_PATH); today = date.today()
    refresh(con, today); rebuild(con)
    default_sub = cfg["filters"]["remodel"]["default_list_subtypes"]
    d28, d365 = (today - timedelta(days=28)).isoformat(), (today - timedelta(days=365)).isoformat()
    rows = [dict(r) for r in con.execute("SELECT * FROM project_index WHERE project_type='remodel'")]
    kept = [r for r in rows if r["passed"]]
    first_issue = {r["id"]: r["issued_date"] for r in con.execute("SELECT id, issued_date FROM candidates")}
    for r in kept:   # volume date: permits use the first issue date (matches the earlier windows); the others use the applied/submitted date
        r["vol_date"] = (first_issue.get(r["ref_id"]) if r["stage"] == "permit_issued" else r["applied_date"]) or ""
    default_list = [r for r in kept if r["remodel_subtype"] in default_sub]
    bucket = [r for r in kept if r["remodel_subtype"] not in default_sub]
    L = [f"# Remodel projects, {today}", "",
         "Remodel = Remodel is the only construction work class. Reported separately from the headline (new build, shell, addition). Everything is kept in the "
         "database; building use is not used to rank or exclude (use class is a searchable attribute). **Remodels are never enriched.**", "",
         f"**Default remodel list = {', '.join(default_sub)}.** `repair_or_other` (the catch-all for remodels that are neither a tenant finish-out nor an interior remodel: "
         "terse descriptions, telecom/equipment work, certificates and the like) is **hidden from that list and reported as a separate bucket** (section B).", "",
         "Only repair, signage and demolition-only are excluded as non-projects (keyword rules in `config.yaml` under `filters.remodel`; approximate). Status and the "
         "solar/EV trade rule still apply.", "",
         "Descriptions are scrubbed of personal names, phone numbers and emails before storage (`[NAME]`, `[CONTACT]`); `name_removed` = 1 flags every row where that "
         "happened. The scrub is heuristic: see README for its limits.", ""]
    # ---- A. default remodel list
    L += ["## A. Default remodel list (tenant_finish_out + interior_remodel)", "", "### A1. Outcomes", "",
          "| stage | kept: default list | tenant_finish_out | interior_remodel | kept: repair_or_other (bucket, section B) | non-project repair | signage | demolition-only | other exclusions (status, solar/EV) |",
          "|---|---|---|---|---|---|---|---|---|"]
    reason_sql = {"permit_issued": "SELECT f.exclude_reason r FROM candidates c JOIN filter_results f ON f.candidate_id=c.id WHERE c.project_type='remodel' AND f.passed=0 AND c.source='austin'",
                  "plan_review": "SELECT exclude_reason r FROM plan_review_candidates WHERE project_type='remodel' AND passed=0",
                  "site_plan": "SELECT exclude_reason r FROM site_plan_candidates WHERE project_type='remodel' AND passed=0"}
    for stage, label, _ in STAGES:
        kp = [r for r in kept if r["stage"] == stage]
        c = Counter(r["remodel_subtype"] for r in kp)
        rc = Counter(x["r"] for x in con.execute(reason_sql[stage]))
        other = sum(v for k, v in rc.items() if not k.startswith("non_project"))
        L.append(f"| {label} | {sum(1 for r in kp if r['remodel_subtype'] in default_sub):,} | {c['tenant_finish_out']:,} | {c['interior_remodel']:,} | {c['repair_or_other']:,} | "
                 f"{rc['non_project_repair']:,} | {rc['non_project_signage']:,} | {rc['non_project_demolition_only']:,} | {other:,} |")
    L += ["", "### A2. Weekly volume by subtype", "",
          "Permit stage uses the first issue date; Plan Review and site plans use the applied/submitted date. Last 28 days = 4 weeks; 12 months = 52 weeks.", ""]
    _table_volume(L, default_list, default_sub, "all (default list)", d28, d365)
    L += ["", "### A3. Applicant and contractor coverage (last 12 months)", "",
          "Permit records carry both; Plan Review and site plans carry the applicant organization only (no contractor field). Business names only: person names are dropped "
          "and permit-system tags such as `(MAIN)` are stripped. On permit records the applicant organization is the contractor's company in every record that has both, "
          "so for permits the two columns are one signal, not two.", ""]
    _table_coverage(L, default_list, default_sub, "all (default list)", d365)
    # ---- B. bucket
    L += ["", "## B. Separate bucket: repair_or_other (NOT in the default remodel list)", "",
          "Volume and coverage use the same definitions as section A.", "", "### B1. Weekly volume", ""]
    _table_volume(L, bucket, ["repair_or_other"], "repair_or_other (all)", d28, d365)
    L += ["", "### B2. Applicant and contractor coverage (last 12 months)", ""]
    _table_coverage(L, bucket, ["repair_or_other"], "repair_or_other (all)", d365)
    # ---- C. scrub flags
    L += ["", "## C. Description scrub flags (kept remodels)", "", "| stage | default list: rows | name removed | share | repair_or_other bucket: rows | name removed | share |", "|---|---|---|---|---|---|---|"]
    for stage, label, _ in STAGES:
        a = [r for r in default_list if r["stage"] == stage]; b = [r for r in bucket if r["stage"] == stage]
        fa, fb = sum(1 for r in a if r["name_removed"]), sum(1 for r in b if r["name_removed"])
        L.append(f"| {label} | {len(a):,} | {fa} | {fa / max(len(a), 1):.1%} | {len(b):,} | {fb} | {fb / max(len(b), 1):.1%} |")
    # ---- D. recency / search / files
    rec = sorted(r["recency_days"] for r in default_list if r["recency_days"] is not None)
    L += ["", "## D. Recency, search and the lists", "",
          f"`recency_days` = days since the permit/application was applied for or issued, whichever is later (0 = today); default list median {rec[len(rec) // 2]} days, newest {rec[0]}.",
          "Files (every kept remodel from the last 12 months, **newest first**, with use class, description, applicant, contractor, address and `name_removed` on every row): "
          "`reports/remodels-12m.csv` (default list) and `reports/remodels-repair-or-other-12m.csv` (bucket).",
          "Search (newest first; the bucket is hidden unless `--with-bucket` or `--subtype repair_or_other`): "
          "`python -m src.index search \"tenant finish out\" --type remodel --limit 20`.", ""]

    def recent(rs):
        out = [r for r in rs if r["vol_date"] >= d365 or (r["stage"] != "permit_issued" and (r["recency_days"] or 9999) <= 365)]
        return sorted(out, key=lambda r: (r["recency_days"] if r["recency_days"] is not None else 99999))
    for fname, rs in (("remodels-12m.csv", recent(default_list)), ("remodels-repair-or-other-12m.csv", recent(bucket))):
        with open(cfgmod.ROOT / "reports" / fname, "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(CSV_COLS); [w.writerow([r[k] if r[k] is not None else "" for k in CSV_COLS]) for r in rs]
        L.append(f"`{fname}`: {len(rs):,} rows.")
    p = cfgmod.ROOT / "reports" / f"remodels-{today}.md"
    p.write_text("\n".join(L) + "\n"); print(p)


if __name__ == "__main__":
    main()
