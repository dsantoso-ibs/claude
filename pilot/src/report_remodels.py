"""Remodel report: subtype volume per week, applicant/contractor coverage, non-project exclusions, newest-first CSV.
Usage: python -m src.report_remodels -> reports/remodels-YYYY-MM-DD.md + reports/remodels-12m.csv   (remodels are never enriched)"""
from __future__ import annotations
import csv
from collections import Counter
from datetime import date, timedelta

from src import config as cfgmod
from src.index import rebuild
from src.recency import refresh
from src.schema import connect

SUBTYPES = ["tenant_finish_out", "interior_remodel", "repair_or_other"]
# stage -> (label, date column used for volume, does the source carry a contractor?)
STAGES = [("permit_issued", "permit issued (first issue date)", "issued_date", True),
          ("plan_review", "Plan Review applied", "applied_date", False),
          ("site_plan", "site plan submitted", "applied_date", False)]


def main() -> None:
    cfg = cfgmod.load(); con = connect(cfgmod.DB_PATH); today = date.today()
    refresh(con, today); rebuild(con)
    d28, d365 = (today - timedelta(days=28)).isoformat(), (today - timedelta(days=365)).isoformat()
    rows = [dict(r) for r in con.execute("SELECT * FROM project_index WHERE project_type='remodel'")]
    kept = [r for r in rows if r["passed"]]
    # the volume date: permits use the FIRST issue date (matches the earlier windows); others use the applied/submitted date
    first_issue = {r["id"]: r["issued_date"] for r in con.execute("SELECT id, issued_date FROM candidates")}
    for r in kept:
        r["vol_date"] = (first_issue.get(r["ref_id"]) if r["stage"] == "permit_issued" else r["applied_date"]) or ""
    L = [f"# Remodel projects, {today}", "",
         "Remodel = Remodel is the only construction work class. Reported separately from the headline (new build, shell, addition). Everything is kept in the "
         "database; building use is not used to rank or exclude (use class is a searchable attribute). **Remodels are never enriched.**", "",
         "Only repair, signage and demolition-only are excluded as non-projects (keyword rules in `config.yaml` under `filters.remodel`; approximate). Status and "
         "the solar/EV trade rule still apply. `repair_or_other` is the catch-all subtype for remodels that are neither a tenant finish-out nor an interior remodel "
         "(terse descriptions, telecom/equipment work, certificates, etc.); repair-like rows caught as non-projects are excluded.", ""]
    # ---- 1 outcome counts
    L += ["## 1. Outcomes (permit projects, Plan Review, site plans)", "", "| stage | remodels kept | tenant_finish_out | interior_remodel | repair_or_other | non-project repair | signage | demolition-only | other exclusions (status, solar/EV) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for stage, label, dc, _ in STAGES:
        sr = [r for r in rows if r["stage"] == stage]
        kp = [r for r in sr if r["passed"]]
        ex = Counter(x[0] for x in con.execute("SELECT 'x' FROM project_index WHERE 0")) if False else None
        reason = {"permit_issued": ("SELECT f.exclude_reason r FROM candidates c JOIN filter_results f ON f.candidate_id=c.id WHERE c.project_type='remodel' AND f.passed=0 AND c.source='austin'"),
                  "plan_review": "SELECT exclude_reason r FROM plan_review_candidates WHERE project_type='remodel' AND passed=0",
                  "site_plan": "SELECT exclude_reason r FROM site_plan_candidates WHERE project_type='remodel' AND passed=0"}[stage]
        rc = Counter(x["r"] for x in con.execute(reason))
        other = sum(v for k, v in rc.items() if not k.startswith("non_project"))
        c = Counter(r["remodel_subtype"] for r in kp)
        L.append(f"| {label} | {len(kp):,} | {c['tenant_finish_out']:,} | {c['interior_remodel']:,} | {c['repair_or_other']:,} | {rc['non_project_repair']:,} | {rc['non_project_signage']:,} | {rc['non_project_demolition_only']:,} | {other:,} |")
    # ---- 2 weekly volume
    L += ["", "## 2. Weekly volume by subtype (kept remodels)", "",
          "Permit stage uses the first issue date; Plan Review and site plans use the applied/submitted date. Last 28 days = 4 weeks; 12 months = 52 weeks.", "",
          "| stage | subtype | last 28 days (count) | per week | last 12 months (count) | per week |", "|---|---|---|---|---|---|"]
    for stage, label, dc, _ in STAGES:
        for st in SUBTYPES + ["all remodels"]:
            sel = [r for r in kept if r["stage"] == stage and (st == "all remodels" or r["remodel_subtype"] == st)]
            n28 = sum(1 for r in sel if r["vol_date"] >= d28); n365 = sum(1 for r in sel if r["vol_date"] >= d365)
            b = "**" if st == "all remodels" else ""
            L.append(f"| {label} | {b}{st}{b} | {n28} | {n28 / 4:.1f} | {n365:,} | {n365 / 52:.1f} |")
    # ---- 3 coverage
    L += ["", "## 3. Applicant and contractor coverage (kept remodels, last 12 months)", "",
          "Permit records carry both; Plan Review and site plans carry the applicant organization only (no contractor field). Business names only: person names were dropped before storage and permit-system tags such as `(MAIN)` are stripped. "
          "On permit records the applicant organization is the contractor's company in every record that has both, so for permits the two columns are one signal, not two.", "",
          "| stage | subtype | records | applicant org | contractor | applicant or contractor |", "|---|---|---|---|---|---|"]
    for stage, label, dc, has_c in STAGES:
        for st in SUBTYPES + ["all remodels"]:
            sel = [r for r in kept if r["stage"] == stage and r["vol_date"] >= d365 and (st == "all remodels" or r["remodel_subtype"] == st)]
            n = len(sel) or 1
            a = sum(1 for r in sel if r["applicant_org"]); c = sum(1 for r in sel if r["contractor_name"]); e = sum(1 for r in sel if r["applicant_org"] or r["contractor_name"])
            b = "**" if st == "all remodels" else ""
            L.append(f"| {label} | {b}{st}{b} | {len(sel):,} | {a / n:.0%} | " + (f"{c / n:.0%}" if has_c else "n/a") + f" | {e / n:.0%} |")
    # ---- 4 recency
    rec = sorted(r["recency_days"] for r in kept if r["recency_days"] is not None)
    L += ["", "## 4. Recency, search and the list", "",
          f"`recency_days` = days since the permit/application was applied for or issued, whichever is later (0 = today); median across kept remodels {rec[len(rec) // 2]} days, newest {rec[0]}.",
          "`reports/remodels-12m.csv`: every kept remodel from the last 12 months across all three stages, **newest first**, with use class, description, applicant, contractor and address on every row. "
          "Search all records (any type): `python -m src.index search \"tenant finish out\" --type remodel --subtype tenant_finish_out --limit 20` (results newest first); "
          "searchable fields: use class, description, applicant, contractor, address, owner.", ""]
    out = [r for r in kept if r["vol_date"] >= d365 or (r["stage"] != "permit_issued" and (r["recency_days"] or 9999) <= 365)]
    out.sort(key=lambda r: (r["recency_days"] if r["recency_days"] is not None else 99999))
    cols = ["recency_days", "recency_date", "stage", "remodel_subtype", "size_band", "use_class", "description", "applicant_org", "contractor_name", "address", "address_norm", "status", "applied_date", "issued_date"]
    with open(cfgmod.ROOT / "reports" / "remodels-12m.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(cols); [w.writerow([r[k] if r[k] is not None else "" for k in cols]) for r in out]
    L.append(f"CSV rows: {len(out):,}.")
    p = cfgmod.ROOT / "reports" / f"remodels-{today}.md"
    p.write_text("\n".join(L) + "\n"); print(p)


if __name__ == "__main__":
    main()
