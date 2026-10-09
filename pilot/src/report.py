"""M5: pilot report. Usage: python -m src.report [austin]  -> reports/pilot-YYYY-MM-DD.md + CSV."""
from __future__ import annotations
import csv
import math
import sys
from datetime import date, datetime, timedelta, timezone

from src import config as cfgmod
from src.schema import connect


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d, (c + m) / d


def verdict(novel: int, in_base: int, contact_yield: float | None, dcfg: dict) -> tuple[str, str]:
    n = novel + in_base
    if n == 0:
        return "NOT MEASURABLE", "No baseline labels yet. Load a baseline export or complete the manual spot-check."
    share = novel / n
    lo, hi = wilson(novel, n)
    if contact_yield is None:
        if hi < dcfg["min_novel_share"]:
            return "STOP / RETHINK (novel share)", f"Novel share {share:.0%} (95% CI {lo:.0%}-{hi:.0%}) is below {dcfg['min_novel_share']:.0%} even at the upper bound. Contact yield not measured."
        if lo >= dcfg["min_novel_share"]:
            return "PROVISIONAL CONTINUE (contact yield unmeasured)", f"Novel share {share:.0%} (95% CI {lo:.0%}-{hi:.0%}) clears {dcfg['min_novel_share']:.0%}. The 50% contact-yield test needs enrichment, which is disabled."
        return "INCONCLUSIVE", f"Novel share {share:.0%} (95% CI {lo:.0%}-{hi:.0%}) straddles the {dcfg['min_novel_share']:.0%} threshold; label more projects. Contact yield not measured."
    ok = share >= dcfg["min_novel_share"] and contact_yield >= dcfg["min_contact_yield"]
    return ("CONTINUE" if ok else "STOP / RETHINK"), f"Novel share {share:.0%} (CI {lo:.0%}-{hi:.0%}), contact yield {contact_yield:.0%}."


def main(source: str = "austin") -> None:
    cfg = cfgmod.load(); con = connect(cfgmod.DB_PATH)
    q = lambda s, *a: con.execute(s, a).fetchall()
    today = date.today()
    win = (today - timedelta(days=cfg["ingest"]["phase1_window_days"])).isoformat()
    passed = q("SELECT c.* FROM candidates c JOIN filter_results f ON f.candidate_id=c.id WHERE c.source=? AND f.passed=1 AND c.in_default=1 AND c.issued_date>=?", source, win)
    remodel = q("SELECT c.size_band b FROM candidates c JOIN filter_results f ON f.candidate_id=c.id WHERE c.source=? AND f.passed=1 AND c.in_default=0 "
                "AND c.project_type='remodel' AND c.issued_date>=?", source, win)
    all_n = q("SELECT COUNT(*) n FROM candidates WHERE source=? AND issued_date>=?", source, win)[0]["n"]
    span = (today - date.fromisoformat(min(r["issued_date"] for r in passed))).days or 1
    last28 = [r for r in passed if r["issued_date"] >= (today - timedelta(days=28)).isoformat()]
    labels = {r["label"]: r["n"] for r in q("SELECT l.label, COUNT(*) n FROM candidate_labels l JOIN candidates c ON c.id=l.candidate_id "
                                           "WHERE c.source=? GROUP BY l.label", source)}
    novel, inb, review = labels.get("novel", 0), labels.get("in_baseline", 0), labels.get("review", 0)
    methods = {r["method"].split(":")[0]: r["n"] for r in q("SELECT l.method, COUNT(*) n FROM candidate_labels l GROUP BY l.method")}
    enr = q("SELECT COUNT(*) n, COALESCE(SUM(cost_usd),0) cost, SUM(found_owner OR found_developer OR found_architect) f, SUM(found_contact) fc FROM enrichments")[0]
    cy = (enr["f"] or 0) / enr["n"] if enr["n"] else None
    gc = sum(1 for r in passed if r["contractor_name"])
    v, why = verdict(novel, inb, cy, cfg["decision"])
    reasons = q("SELECT COALESCE(f.exclude_reason,'passed') r, COUNT(*) n FROM filter_results f JOIN candidates c ON c.id=f.candidate_id WHERE c.issued_date>=? GROUP BY r ORDER BY n DESC", win)
    lo, hi = wilson(novel, novel + inb)
    bands = {r["size_band"] or "unknown": r["n"] for r in q("SELECT c.size_band, COUNT(*) n FROM candidates c JOIN filter_results f ON f.candidate_id=c.id "
                                                         "WHERE c.source=? AND f.passed=1 AND c.in_default=1 AND c.issued_date>=? GROUP BY 1", source, win)}
    band_line = ", ".join(f"{b} {bands.get(b, 0)}" for b in ("unknown", "under_250k", "250k_to_5m", "over_5m"))
    L = [f"# Pilot report: {source}, {today}", "", f"Region: **{cfg['region']['name']}** ({', '.join(cfg['region']['counties'])}). "
         "Austin permit data covers City of Austin jurisdiction only; county/metro share is not separately measured.", "",
         f"## Verdict: {v}", "", why, "", "## Metrics", "",
         f"1. **Qualifying projects (default set):** {len(passed)} passed of {all_n} projects ({span} days of data); "
         f"{len(passed) / span * 7:.1f}/week overall, {len(last28) / 4:.1f}/week over the last 28 days ({len(last28)} projects).",
         f"   Default set = new_build, shell, addition. Size bands (best available valuation; no valuation filter): {band_line}.",
         f"   **Remodels, reported separately and not in the headline:** {len(remodel)} projects (size band: " + ", ".join(
             f"{b} {sum(1 for r in remodel if (r['b'] or 'unknown') == b)}" for b in ("unknown", "under_250k", "250k_to_5m", "over_5m")) + ").",
         f"2. **Novel share:** " + (f"{novel / (novel + inb):.0%} = {novel} novel / ({novel} novel + {inb} in baseline), 95% CI {lo:.0%}-{hi:.0%}; "
                                    f"{review} in `review` shown separately. Label sources: {methods}." if novel + inb else "not measurable (no labels)."),
         f"3. **Contact yield:** " + (f"{cy:.0%} of {enr['n']} enriched projects had owner/developer/architect." if cy is not None else
          f"not measured (enrichment disabled). Proxy only: a contractor/applicant business is named on {gc}/{len(passed)} passed projects "
          f"({gc / len(passed):.0%}). This is a GC, not an owner/developer/architect, and does not count toward the 50% test."),
         f"4. **Enrichment cost:** ${enr['cost']:.2f} total over {enr['n']} projects" + (" (enrichment disabled; cost-plus pricing cannot yet be projected)." if not enr["n"] else "."),
         "5. **Exclusion reasons:**", "", "| reason | projects |\n|---|---|"] + [f"| {r['r']} | {r['n']} |" for r in reasons]
    out = cfgmod.ROOT / "reports" / f"pilot-{today}.md"
    out.write_text("\n".join(L) + "\n")
    with open(cfgmod.ROOT / "reports" / f"pilot-{today}.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["source_id", "address", "valuation", "contractor", "issued", "label", "label_method"])
        lab = {r["candidate_id"]: r for r in q("SELECT * FROM candidate_labels")}
        for r in passed:
            l = lab.get(r["id"])
            w.writerow([r["source_id"], r["address_norm"], r["valuation"], r["contractor_name"], r["issued_date"],
                        l["label"] if l else "unlabelled", l["method"] if l else ""])
    print(out); print(v, "-", why)


if __name__ == "__main__":
    main(*(sys.argv[1:2] or ["austin"]))
