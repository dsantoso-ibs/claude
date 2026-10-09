"""M7.4: phase 2 metrics. Usage: python -m src.report_phase2 -> reports/phase2-YYYY-MM-DD.md + open pipeline CSVs."""
from __future__ import annotations
import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from src import config as cfgmod
from src.report import wilson
from src.schema import connect


def _d(s):
    return date.fromisoformat(s[:10])


def quart(xs: list[int]) -> tuple[float, float, float]:
    xs = sorted(xs)
    def q(p):
        k = (len(xs) - 1) * p; f = int(k); c = min(f + 1, len(xs) - 1)
        return xs[f] + (xs[c] - xs[f]) * (k - f)
    return q(.25), q(.5), q(.75)


def qualifying_permits(con) -> dict[str, dict]:
    return {r["source_id"]: dict(r) for r in con.execute(
        "SELECT c.source_id, c.address_norm, c.issued_date, c.valuation, c.contractor_name FROM candidates c "
        "JOIN filter_results f ON f.candidate_id=c.id WHERE c.source='austin' AND f.passed=1")}


def linked_best(con, cfg: dict, table: str = "site_plan_permit_links", idcol: str = "case_id", datecol=None) -> dict[int, dict]:
    """Per case: earliest-issued qualifying permit project linked at score >= link_score (the first building)."""
    perm = qualifying_permits(con)
    out: dict[int, dict] = {}
    for r in con.execute(f"SELECT {idcol} AS cid, project_key, score, method FROM {table} WHERE score >= ?", (cfg["linking"]["link_score"],)):
        p = perm.get(r["project_key"])
        if not p:
            continue
        cur = out.get(r["cid"])
        if cur is None or p["issued_date"] < cur["issued_date"]:
            out[r["cid"]] = dict(project_key=r["project_key"], score=r["score"], method=r["method"], issued_date=p["issued_date"])
    return out


def _any_link(con, table: str, idcol: str, review: float) -> set[int]:
    return {r[0] for r in con.execute(f"SELECT DISTINCT {idcol} FROM {table} WHERE score >= ?", (review,))}


def open_pipeline(con, cfg: dict, remodel: bool = False) -> list[dict]:
    fc = cfg["site_plan_filters"]
    cutoff = (date.today() - timedelta(days=int(fc["open_pipeline_max_age_months"] * 30.5))).isoformat()
    linked = _any_link(con, "site_plan_permit_links", "case_id", cfg["linking"]["review_score"])
    rows = []
    sel = "project_type='remodel'" if remodel else "in_default=1"
    for r in con.execute(f"SELECT * FROM site_plan_candidates WHERE passed=1 AND {sel} AND submitted_date>=? ORDER BY submitted_date DESC", (cutoff,)):
        r = dict(r)
        if r["id"] in linked or not any((r["status"] or "").startswith(x) for x in fc["open_statuses"]):
            continue
        rows.append(r)
    return rows


def pr_open_pipeline(con, cfg: dict, remodel: bool = False) -> list[dict]:
    cutoff = (date.today() - timedelta(days=int(cfg["site_plan_filters"]["open_pipeline_max_age_months"] * 30.5))).isoformat()
    linked = _any_link(con, "plan_review_permit_links", "pr_id", cfg["linking"]["review_score"])
    sel = "project_type='remodel'" if remodel else "in_default=1"
    return [dict(r) for r in con.execute(f"SELECT * FROM plan_review_candidates WHERE passed=1 AND {sel} AND issued_date IS NULL AND applied_date>=? ORDER BY applied_date DESC", (cutoff,))
            if r["id"] not in linked]


BANDS = ("unknown", "under_250k", "250k_to_5m", "over_5m")


def band_counts(rows: list[dict]) -> dict[str, int]:
    c = Counter((r.get("size_band") or "unknown") for r in rows)
    return {b: c.get(b, 0) for b in BANDS}


def band_table(sets: list[tuple[str, list[dict]]]) -> list[str]:
    out = ["| set | total | unknown | under_250k | 250k_to_5m | over_5m |", "|---|---|---|---|---|---|"]
    for name, rows in sets:
        b = band_counts(rows)
        out.append(f"| {name} | {len(rows)} | " + " | ".join(str(b[k]) for k in BANDS) + " |")
    return out


def _fmt_q(xs):
    a, b, c = quart(xs)
    return f"p25 {a:.0f} d | **median {b:.0f} d** | p75 {c:.0f} d | max {max(xs)} d; {sum(x > 1095 for x in xs)} over 3 years (n={len(xs)})"


def main() -> None:
    cfg = cfgmod.load(); con = connect(cfgmod.DB_PATH); today = date.today()
    lc = cfg["linking"]
    L = [f"# Phase 2 report: Austin Site Plan Cases and Plan Review Cases, {today}", ""]
    # ---------------- site plans
    allc = [dict(r) for r in con.execute("SELECT * FROM site_plan_candidates")]
    passed = [c for c in allc if c["in_default"]]                       # headline = default set
    remodels = [c for c in allc if c["passed"] and c["project_type"] == "remodel"]
    reasons = Counter("passed: default set" if c["in_default"] else "passed: remodel (reported separately)" if c["passed"] else c["exclude_reason"] for c in allc)
    best = {k: v for k, v in linked_best(con, cfg).items() if k in {c["id"] for c in passed}}   # default set only
    anyl = _any_link(con, "site_plan_permit_links", "case_id", lc["review_score"])
    review_only = {c["id"] for c in passed if c["id"] in anyl and c["id"] not in best}
    s28, s365 = today - timedelta(days=28), today - timedelta(days=365)
    n28 = sum(_d(c["submitted_date"]) >= s28 for c in passed); n365 = sum(_d(c["submitted_date"]) >= s365 for c in passed)
    L += ["## A. Site Plan Cases", "",
          f"Loaded {len(allc):,} cases (application start from {min(c['submitted_date'] for c in allc if c['submitted_date'])}). "
          f"**Default set (new build, shell, addition, plus {sum(1 for c in passed if c['project_type'] == 'unknown')} of unknown type with no linked permit/application): {len(passed):,}**; "
          f"remodels reported separately: {len(remodels):,}; excluded by the filter: {sum(1 for c in allc if not c['passed']):,}.", "",
          "| outcome / exclusion reason | cases |\n|---|---|"] + [f"| {k} | {v} |" for k, v in reasons.most_common()] + [
          "", "### 1. Passed cases per week", "",
          f"- Last 28 days: **{n28}** cases = {n28 / 4:.1f}/week. Last 12 months: **{n365}** = {n365 / 52:.1f}/week.",
          f"- Passed by use class: " + ", ".join(f"{k} {v}" for k, v in Counter(c['use_class'] for c in passed).most_common())
          + f". Likely multi-family within `housing_unclear`/commercial by case name: {sum(1 for c in passed if c['multifamily_hint'] and c['use_class'] != 'multifamily')}.", ""]
    # ---- 2 linked share by cohort
    coh = defaultdict(lambda: [0, 0, 0, 0, 0])   # passed, linked, review, approved, approved linked
    approved = ("Approved", "Closed", "CC Approved")
    for c in passed:
        y = c["submitted_date"][:4]; k = coh[y]; k[0] += 1
        k[1] += c["id"] in best; k[2] += c["id"] in review_only
        if (c["status"] or "").startswith(approved):
            k[3] += 1; k[4] += c["id"] in best
    L += ["### 2. Share of passed cases linked to an issued permit project", "",
          f"Linked = same address/geo match to a *qualifying* permit project (score >= {lc['link_score']}, permit issued on/after case submission). "
          f"Review bucket = best score {lc['review_score']}-{lc['link_score']}.", "",
          "| submitted | passed | linked | review | % linked | approved/closed cases | % of those linked |\n|---|---|---|---|---|---|---|"]
    for y in sorted(coh):
        p, l, rv, a, al = coh[y]
        L.append(f"| {y} | {p} | {l} | {rv} | {l / p:.0%} | {a} | {al / a:.0%} |" if a else f"| {y} | {p} | {l} | {rv} | {l / p:.0%} | 0 | n/a |")
    tp, tl = len(passed), len(best)
    ta = sum(v[3] for v in coh.values()); tal = sum(v[4] for v in coh.values())
    L += ["", f"**Overall: {tl} of {tp} passed cases linked ({tl / tp:.0%}); {len(review_only)} more in review.** "
          f"Among approved/closed cases: {tal} of {ta} ({tal / ta:.0%}). Older cohorts have had longer to reach a permit; recent cohorts are right-censored.", ""]
    # ---- 3 lead time
    leads = {cid: (_d(b["issued_date"]) - _d(next(c for c in passed if c["id"] == cid)["submitted_date"])).days for cid, b in best.items()}
    byid = {c["id"]: c for c in passed}
    L += ["### 3. Lead time: permit issued minus site plan submitted (linked cases only)", ""]
    if leads:
        prov = len(leads) < lc["min_cases_for_non_provisional"]
        L += [f"- All linked cases: {_fmt_q(list(leads.values()))}" + ("  **PROVISIONAL (fewer than 30 linked)**" if prov else ""),
              f"- Per distinct permit project (earliest case): {_fmt_q(list({b['project_key']: 0 for b in best.values()}.keys() and [min(leads[cid] for cid, b in best.items() if b['project_key'] == pk) for pk in {b['project_key'] for b in best.values()}]))}"]
        for grp, test in (("multi-family (class or name hint)", lambda c: c["use_class"] == "multifamily" or c["multifamily_hint"]),
                          ("commercial", lambda c: c["use_class"] == "commercial" and not c["multifamily_hint"]),
                          ("industrial / public-civic / housing", lambda c: c["use_class"] in ("industrial", "public_civic", "housing_unclear") and not c["multifamily_hint"])):
            xs = [v for cid, v in leads.items() if test(byid[cid])]
            if len(xs) >= 5:
                L.append(f"- {grp}: {_fmt_q(xs)}")
        bl = [f"{b}: median {quart(xs)[1]:.0f} d (n={len(xs)})" for b in BANDS
              for xs in [[v for cid, v in leads.items() if (byid[cid].get("size_band") or "unknown") == b]] if len(xs) >= 5]
        L += ["- By size band: " + "; ".join(bl)]
        L += ["", "By submission year (shows right-censoring: recent years only contain the fast cases):", "", "| submitted | linked | median lead (days) |\n|---|---|---|"]
        for y in sorted({byid[cid]["submitted_date"][:4] for cid in leads}):
            xs = [v for cid, v in leads.items() if byid[cid]["submitted_date"][:4] == y]
            L.append(f"| {y} | {len(xs)} | {quart(xs)[1]:.0f} |")
        L += ["", "Caution: only cases that already reached a permit can be lead-timed, so these numbers understate the true lead for the whole cohort, "
              "and the cases seen are not a random sample. A negative-lead pair is impossible by construction (permit must be issued after submission)."]
    else:
        L.append("No linked cases.")
    # ---- 4 open pipeline
    pipe = open_pipeline(con, cfg)
    cols = ["case_number", "case_name", "address_norm", "proposed_use", "use_class", "owner_entity", "applicant_org", "status", "submitted_date", "size_hint"]
    with open(cfgmod.ROOT / "reports" / "open-pipeline-site-plans.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(cols); [w.writerow([c[k] or "" for k in cols]) for c in pipe]
    age = [(today - _d(c["submitted_date"])).days for c in pipe]
    L += ["", "### 4. Open pipeline (stage 2 product): passed, open status, submitted within 24 months, no permit link", "",
          f"**{len(pipe)} cases** (full list: `reports/open-pipeline-site-plans.csv`). By use class: " + ", ".join(f"{k} {v}" for k, v in Counter(c['use_class'] for c in pipe).most_common()) + ".",
          "By status: " + ", ".join(f"{k} {v}" for k, v in Counter(c['status'] for c in pipe).most_common(8)) + ".",
          f"Age since submission: median {sorted(age)[len(age) // 2]} days." if age else "",
          "", "Most recent 15:", "", "| case | name | address | use | owner entity | applicant | status | submitted |\n|---|---|---|---|---|---|---|---|"]
    for c in pipe[:15]:
        L.append(f"| {c['case_number']} | {c['case_name'] or ''} | {c['address_norm']} | {c['proposed_use']} | {c['owner_entity'] or ''} | {c['applicant_org'] or ''} | {c['status']} | {c['submitted_date']} |")
    # ---- 5 coverage
    def cov(rows, f):
        return sum(1 for c in rows if c[f])
    L += ["", "### 5. Owner / applicant coverage (business entities only)", "",
          "| set | cases | owner entity | applicant org | either | owner was an individual (dropped) |\n|---|---|---|---|---|---|"]
    for name, rows in (("all passed", passed), ("open pipeline", pipe), ("passed, last 12 months", [c for c in passed if _d(c["submitted_date"]) >= s365])):
        n = len(rows) or 1
        either = sum(1 for c in rows if c["owner_entity"] or c["applicant_org"])
        L.append(f"| {name} | {len(rows)} | {cov(rows, 'owner_entity') / n:.0%} | {cov(rows, 'applicant_org') / n:.0%} | {either / n:.0%} | {sum(c['owner_is_individual'] for c in rows)} |")
    L += ["", "### 5b. Size band (best available valuation, via linked permit project; descriptive only)", ""] + band_table(
        [("passed", passed), ("passed, last 12 months", [c for c in passed if _d(c["submitted_date"]) >= s365]), ("open pipeline", pipe)])
    # ---- M7.5 labels
    lab = Counter(r["label"] for r in con.execute("SELECT label FROM pipeline_labels"))
    novel, inb = lab.get("novel", 0), lab.get("in_baseline", 0)
    L += ["", "### 6. Novelty of open pipeline (M7.5 manual check)", ""]
    if novel + inb:
        lo, hi = wilson(novel, novel + inb)
        L.append(f"Novel {novel}, in baseline {inb}, unsure {lab.get('review', 0)}: novel share {novel / (novel + inb):.0%} (95% CI {lo:.0%}-{hi:.0%}).")
    else:
        L.append("Not measured: `reports/manual-labels-site-plans.csv` (30 stratified open-pipeline cases) has not been labelled (30 default-set projects across the two sheets).")
    # ---------------- plan review
    pr_all = [dict(r) for r in con.execute("SELECT * FROM plan_review_candidates")]
    pr = [c for c in pr_all if c["in_default"]]
    pr_remodel = [c for c in pr_all if c["passed"] and c["project_type"] == "remodel"]
    prl = linked_best(con, cfg, "plan_review_permit_links", "pr_id")
    pby = {c["id"]: c for c in pr}
    prl = {i: b for i, b in prl.items() if i in pby}                      # default set only
    plead = [(_d(b["issued_date"]) - _d(pby[i]["applied_date"])).days for i, b in prl.items() if i in pby and pby[i]["applied_date"]]
    own = [(_d(c["issued_date"]) - _d(c["applied_date"])).days for c in pr if c["issued_date"] and c["applied_date"]]
    ppipe = pr_open_pipeline(con, cfg)
    with open(cfgmod.ROOT / "reports" / "open-pipeline-plan-review.csv", "w", newline="") as fh:
        w = csv.writer(fh); pc = ["permit_number", "project_name", "valuation", "work_class", "use_class", "status", "applied_date", "owner_entity", "applicant_org", "units"]
        w.writerow(pc); [w.writerow([c[k] if c[k] is not None else "" for k in pc]) for c in ppipe]
    p28 = sum(_d(c["applied_date"]) >= s28 for c in pr if c["applied_date"]); p365 = sum(_d(c["applied_date"]) >= s365 for c in pr if c["applied_date"])
    L += ["", "## B. Plan Review Cases (building-permit applications with valuation)", "",
          f"Loaded {len(pr_all):,} commercial/multi-family-class applications (applied since {min(c['applied_date'] for c in pr_all if c['applied_date'])}). "
          f"**Default set {len(pr):,}** (new build, shell, addition; remodels reported separately: {len(pr_remodel):,}; construction work class, commercial/multi-family use, live status; no valuation rule). Exclusions: " + ", ".join(f"{k} {v}" for k, v in Counter(c['exclude_reason'] for c in pr_all if not c['passed']).most_common()) + ".", "",
          f"- Default set per week: last 28 days {p28} ({p28 / 4:.1f}/wk); last 12 months {p365} ({p365 / 52:.1f}/wk).",
          f"- Linked to a qualifying issued permit project: {len(prl)} of {len(pr)} ({len(prl) / len(pr):.0%}).",
          f"- Lead time, permit project issued minus Plan Review applied: " + (_fmt_q(plead) if plead else "no links") + (" **PROVISIONAL**" if len(plead) < lc["min_cases_for_non_provisional"] else ""),
          "- By size band (lead time, linked only): " + "; ".join(
              f"{b}: median {quart(xs)[1]:.0f} d (n={len(xs)})" for b in BANDS
              for xs in [[(_d(bb["issued_date"]) - _d(pby[i]["applied_date"])).days for i, bb in prl.items() if i in pby and pby[i]["applied_date"]
                          and (pby[i].get("size_band") or "unknown") == b]] if len(xs) >= 5),
          f"- Plan Review's own applied to issued (all passed that have an issue date): {_fmt_q(own) if own else 'n/a'}.",
          f"- **Open pipeline: {len(ppipe)} applications** not yet issued and with no permit link (`reports/open-pipeline-plan-review.csv`); total declared valuation ${sum(c['valuation'] for c in ppipe) / 1e6:,.0f}M; "
          f"owner entity named on {sum(1 for c in ppipe if c['owner_entity'])} ({(sum(1 for c in ppipe if c['owner_entity']) / len(ppipe) if ppipe else 0):.0%}), applicant org on {sum(1 for c in ppipe if c['applicant_org'])}.",
          "", "Largest 10 open applications:", "", "| permit | project | valuation | work | use class | status | applied | owner | applicant |\n|---|---|---|---|---|---|---|---|---|"]
    for c in sorted(ppipe, key=lambda c: -c["valuation"])[:10]:
        L.append(f"| {c['permit_number']} | {c['project_name']} | {c['valuation']:,.0f} | {c['work_class']} | {c['use_class'][:30]} | {c['status']} | {c['applied_date']} | {c['owner_entity'] or ''} | {c['applicant_org'] or ''} |")
    # ---------------- C. remodels, separate from the headline
    win = (today - timedelta(days=cfg["ingest"]["phase1_window_days"])).isoformat()
    perm_rm = [dict(r) for r in con.execute("SELECT c.size_band, c.issued_date FROM candidates c JOIN filter_results f ON f.candidate_id=c.id "
                                            "WHERE c.source='austin' AND f.passed=1 AND c.project_type='remodel'")]
    sp_rm_open, pr_rm_open = open_pipeline(con, cfg, remodel=True), pr_open_pipeline(con, cfg, remodel=True)
    for name, rows, cols_, getter in (("site-plans", sp_rm_open, cols, lambda c, k: c[k] or ""),
                                      ("plan-review", pr_rm_open, ["permit_number", "project_name", "valuation", "work_class", "use_class", "status", "applied_date", "owner_entity", "applicant_org", "size_band"],
                                       lambda c, k: c[k] if c[k] is not None else "")):
        with open(cfgmod.ROOT / "reports" / f"open-pipeline-{name}-remodel.csv", "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(cols_); [w.writerow([getter(c, k) for k in cols_]) for c in rows]
    L += ["", "## C. Remodels (reported separately; NOT in the headline numbers above)", "",
          "Remodel = a permit/application whose work class is `Remodel` only. They are fully kept in the database and CSVs; the default set is new build, shell and addition.", ""] + band_table([
              ("permit projects, passed, last 12 months", [r for r in perm_rm if r["issued_date"] >= win]),
              ("permit projects, passed, 5 years", perm_rm),
              ("site plan cases, passed", [c for c in allc if c["passed"] and c["project_type"] == "remodel"]),
              ("Plan Review, passed, last 12 months", [c for c in pr_remodel if c["applied_date"] and _d(c["applied_date"]) >= s365]),
              ("Plan Review, passed, 5 years", pr_remodel),
              ("site plan open pipeline (remodel)", sp_rm_open),
              ("Plan Review open pipeline (remodel)", pr_rm_open)]) + [
          "", "Files: `reports/open-pipeline-site-plans-remodel.csv`, `reports/open-pipeline-plan-review-remodel.csv`.", ""]
    L += ["", "Size bands, Plan Review:", ""] + band_table([("passed", pr), ("passed, last 12 months", [c for c in pr if c["applied_date"] and _d(c["applied_date"]) >= s365]), ("open pipeline", ppipe)])
    out = cfgmod.ROOT / "reports" / f"phase2-{today}.md"
    out.write_text("\n".join(L) + "\n")
    print(out)


if __name__ == "__main__":
    main()
