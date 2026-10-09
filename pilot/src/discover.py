"""M0: schema discovery. Writes reports/<name>-schema.md. No filter logic here.

Usage: python -m src.discover [austin|los_angeles]
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.sources.socrata import SocrataClient

ROOT = Path(__file__).resolve().parent.parent
# Candidate fields to profile for distinct values (only those present are used).
PROFILE_FIELDS = ["permittype", "permit_type_desc", "permit_class_mapped", "permit_class",
                  "work_class", "status_current", "issue_method", "jurisdiction", "contractor_trade"]
VALUATION_FIELDS = ["total_job_valuation", "total_valuation_remodel", "building_valuation"]
KEY_FIELDS = ["permit_number", "permit_location", "original_address1", "latitude", "longitude",
              "issue_date", "description", "contractor_company_name", "contractor_full_name",
              "applicant_full_name", "applicant_org", "housing_units", "total_new_add_sqft",
              "project_id", "masterpermitnum"]


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in r) + " |" for r in rows]
    return "\n".join(out)


def main(source: str = "austin") -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())["sources"][source]
    dom, ds = cfg["domain"], cfg["dataset_id"]
    client = SocrataClient(dom)
    meta = client.metadata(ds)
    cols = [c for c in meta["columns"] if not c["fieldName"].startswith(":@")]
    names = {c["fieldName"] for c in cols}
    total = int(client.query(ds, select="count(*) as n")[0]["n"])
    sample = client.query(ds, order="issue_date DESC", limit=20) if "issue_date" in names \
        else client.query(ds, limit=20)

    L: list[str] = [f"# Schema report: {source} (`{ds}` on {dom})", "",
                    f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}. Dataset: **{meta['name']}**, "
                    f"{total:,} rows. Spec assumption to verify: no owner/applicant fields.", "",
                    "## Columns", "",
                    md_table(["field", "type", "description"],
                             [[c["fieldName"], c["dataTypeName"], (c.get("description") or "")[:120]] for c in cols])]

    L += ["", "## Fill rate of key fields", ""]
    rows = []
    for f in [f for f in KEY_FIELDS if f in names]:
        n = int(client.query(ds, select="count(*) as n", where=f"{f} IS NOT NULL")[0]["n"])
        rows.append([f, f"{n:,}", f"{n / total:.1%}"])
    L.append(md_table(["field", "non-null", "fill"], rows))

    L += ["", "## Valuation distribution", ""]
    rows = []
    for f in [f for f in VALUATION_FIELDS if f in names]:
        r = client.query(ds, select=f"count(*) as n, sum(case({f} >= 250000, 1, true, 0)) as ge250k, "
                                    f"min({f}) as mn, max({f}) as mx, avg({f}) as av")[0]
        rows.append([f, r.get("n"), r.get("ge250k"), r.get("mn"), r.get("mx"), f"{float(r.get('av', 0)):,.0f}"])
    L.append(md_table(["field", "rows", ">= $250k", "min", "max", "avg"], rows))

    for f in [f for f in PROFILE_FIELDS if f in names]:
        vals = client.query(ds, select=f"{f}, count(*) as n", group=f, order="n DESC", limit=60)
        L += ["", f"## Distinct values: `{f}` ({len(vals)} shown, top 60 by count)", "",
              md_table(["value", "rows"], [[v.get(f, "(null)"), v["n"]] for v in vals])]

    L += ["", "## Sample (20 most recent issued)", ""]
    show = [f for f in ["permit_number", "permit_type_desc", "permit_class", "work_class", "issue_date",
                        "total_job_valuation", "permit_location", "contractor_company_name",
                        "applicant_org", "description"] if f in names]
    L.append(md_table(show, [[(str(r.get(f, ""))[:70]) for f in show] for r in sample]))

    L += ["", "## Open questions for review", "",
          "- Which valuation field is authoritative for the >= $250k rule?",
          "- Which field(s) separate new construction vs. addition/alteration vs. trade-only?",
          "- Which field gives occupancy/use (commercial / multi-family / industrial / single-family)?",
          "- Applicant/owner fields exist; spec says store no personal data. Confirm treatment (business names only?).",
          ""]
    out = ROOT / "reports" / f"{source}-schema.md"
    out.write_text("\n".join(L))
    print(f"wrote {out}")


if __name__ == "__main__":
    main(*(sys.argv[1:2] or ["austin"]))
