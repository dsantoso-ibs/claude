"""Generic schema discovery (phase 2). Auto-profiles every column of a Socrata dataset.
Personal fields (person names, phones, street addresses, staff) are profiled for fill rate only, never sampled/listed.

Usage: python -m src.discover_generic <source key in config.yaml>   -> reports/<report_name>-schema.md
"""
from __future__ import annotations
import re
import sys
from datetime import datetime, timezone

from src import config as cfgmod
from src.discover import md_table
from src.sources.socrata import SocrataClient

PERSONAL = re.compile(r"(fullname|full_name|phone|_address$|^applicant_address|case_manager)", re.I)
MAX_LIST = 60


def main(source: str) -> None:
    cfg = cfgmod.load()["sources"][source]
    client = SocrataClient(cfg["domain"])
    ds = cfg["dataset_id"]
    meta = client.metadata(ds)
    cols = [c for c in meta["columns"] if not c["fieldName"].startswith(":@")]
    total = int(client.query(ds, select="count(*) as n")[0]["n"])
    L = [f"# Schema report: {source} (`{ds}` on {cfg['domain']})", "",
         f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}. Dataset: **{meta['name']}**, {total:,} rows. "
         f"Metadata last updated: {datetime.fromtimestamp(meta.get('rowsUpdatedAt', 0), timezone.utc):%Y-%m-%d %H:%M UTC}. "
         f"Personal fields (names, phones, street addresses, staff) are profiled for fill rate only.", ""]
    desc = re.sub(r"<[^>]+>", "", meta.get("description") or "").strip()
    L += ["## Dataset description", "", desc[:1500], ""]

    prof = []   # name, type, nonnull, distinct
    for c in cols:
        f, t = c["fieldName"], c["dataTypeName"]
        if t in ("location", "point", "url", "checkbox") and f not in ("issued_in_last_30_days",):
            nn = int(client.query(ds, select="count(*) as n", where=f"{f} IS NOT NULL")[0]["n"])
            prof.append((f, t, nn, None))
            continue
        r = client.query(ds, select=f"count({f}) as nn, count(distinct {f}) as d")[0]
        prof.append((f, t, int(r["nn"]), int(r["d"])))
    L += ["## Columns, fill rate, cardinality", "", md_table(
        ["field", "type", "non-null", "fill", "distinct"],
        [[f, t, f"{nn:,}", f"{nn / total:.1%}", d if d is not None else ""] for f, t, nn, d in prof]), ""]

    L += ["## Date fields: min / max", ""]
    rows = []
    for f, t, nn, d in prof:
        if t == "calendar_date" and nn:
            r = client.query(ds, select=f"min({f}) as mn, max({f}) as mx")[0]
            rows.append([f, r["mn"][:10], r["mx"][:10], f"{nn:,}"])
    L += [md_table(["field", "min", "max", "non-null"], rows), ""]

    L += ["## Numeric fields", ""]
    rows = []
    for f, t, nn, d in prof:
        if t == "number" and nn and not PERSONAL.search(f):
            r = client.query(ds, select=f"min({f}) as mn, max({f}) as mx, avg({f}) as av, sum(case({f} > 0, 1, true, 0)) as pos")[0]
            rows.append([f, r["mn"], r["mx"], f"{float(r['av']):,.1f}", r["pos"]])
    L += [md_table(["field", "min", "max", "avg", "rows > 0"], rows), ""]

    L += ["## Distinct values (text/checkbox fields with <= 200 distinct, top 60 by count)", ""]
    for f, t, nn, d in prof:
        if t in ("text", "checkbox") and d is not None and 0 < d <= 200 and not PERSONAL.search(f):
            vals = client.query(ds, select=f"{f}, count(*) as n", group=f, order="n DESC", limit=MAX_LIST)
            L += [f"### `{f}` ({d} distinct)", "", md_table(["value", "rows"], [[v.get(f, "(null)"), v["n"]] for v in vals]), ""]

    L += ["## High-cardinality text fields: top 15 values (non-personal)", ""]
    for f, t, nn, d in prof:
        if t == "text" and d and d > 200 and not PERSONAL.search(f) and f in cfg.get("peek_fields", ["proposed_land_use", "work", "project_name",
                                                                                                    "owner_organization_name", "applicant_organization_name", "case_name"]):
            vals = client.query(ds, select=f"{f}, count(*) as n", group=f, order="n DESC", limit=15)
            L += [f"### `{f}` ({d:,} distinct)", "", md_table(["value", "rows"], [[v.get(f, "(null)"), v["n"]] for v in vals]), ""]

    datef = next((f for f in ("application_start_date", "applied_date", "issue_date") if f in {p[0] for p in prof}), None)
    show = [f for f, t, nn, d in prof if not PERSONAL.search(f) and t in ("text", "number", "calendar_date")
            and f in ("case_type", "sub_type", "work", "work_class", "status", "status_current", "permit_number", "case_name", "project_name",
                      "proposed_land_use", "application_start_date", "applied_date", "approval_date", "issued_date", "proposed_no_of_units",
                      "number_of_units", "proposed_bldg_sq_footage", "gross_site_area_acres", "total_job_valuation",
                      "owner_organization_name", "applicant_organization_name", "street_name", "city")]
    if datef:
        sample = client.query(ds, order=f"{datef} DESC", limit=20)
        L += [f"## Sample: 20 most recent by `{datef}` (non-personal fields only)", "",
              md_table(show, [[str(r.get(f, ""))[:45] for f in show] for r in sample]), ""]
    out = cfgmod.ROOT / "reports" / f"{cfg['report_name']}-schema.md"
    out.write_text("\n".join(L))
    print("wrote", out, len(L), "blocks")


if __name__ == "__main__":
    main(sys.argv[1])
