"""Independent check of the open pipeline: for a random sample of open-pipeline site plan cases, query the FULL Austin permit
dataset by address (no valuation floor) for any building permit issued after submission, and classify what it is.
Usage: python -m src.validate_pipeline [n]  -> reports/open-pipeline-validation.md"""
from __future__ import annotations
import random
import sys
from collections import Counter
from datetime import date

from src import config as cfgmod
from src.report_phase2 import open_pipeline
from src.schema import connect
from src.sources.socrata import SocrataClient

CONSTR = {"New", "Shell", "Addition", "Addition and Remodel"}


def main(n: int = 40) -> None:
    cfg = cfgmod.load(); con = connect(cfgmod.DB_PATH)
    scfg = cfg["sources"]["austin"]; client = SocrataClient(scfg["domain"])
    pipe = [p for p in open_pipeline(con, cfg) if p["address_norm"] and p["submitted_date"] < "2026-04-01"]
    sample = random.Random(5).sample(pipe, min(n, len(pipe)))
    rows, kinds = [], Counter()
    for p in sample:
        toks = p["address_norm"].split()
        pat = f"{toks[0]} {' '.join(toks[1:3])}%"
        try:
            hits = client.query(scfg["dataset_id"], select="permit_number,permit_location,issue_date,total_job_valuation,work_class",
                                where=f"permittype='BP' AND issue_date >= '{p['submitted_date']}' AND upper(permit_location) like '{pat}'", limit=10)
        except Exception as e:   # report, do not hide
            hits = []; rows.append((p, f"query error: {e}")); continue
        if not hits:
            kinds["no BP found (consistent with open)"] += 1; rows.append((p, "no BP")); continue
        con_hits = [h for h in hits if h.get("work_class") in CONSTR]
        if con_hits:
            kinds["BP new/shell/addition found (possible missed link)"] += 1
            h = con_hits[0]; rows.append((p, f"MISSED? {h['permit_number']} {h['work_class']} ${float(h.get('total_job_valuation') or 0):,.0f} {h['issue_date'][:10]}"))
        else:
            kinds["only demolition/remodel/repair BP (project moving, not the main permit)"] += 1
            h = hits[0]; rows.append((p, f"{h['work_class']} ${float(h.get('total_job_valuation') or 0):,.0f} {h['issue_date'][:10]}"))
    L = [f"# Open pipeline validation, {date.today()}", "",
         f"Random sample of {len(sample)} open-pipeline site plan cases (submitted before 2026-04, so a permit had time to appear) checked against the **full** Austin permit dataset by address, any valuation.", "",
         "| result | cases |\n|---|---|"] + [f"| {k} | {v} |" for k, v in kinds.most_common()] + [
         "", "| case | address | submitted | result |\n|---|---|---|---|"]
    for p, res in rows:
        L.append(f"| {(p['case_name'] or '')[:40]} | {p['address_norm']} | {p['submitted_date']} | {res} |")
    out = cfgmod.ROOT / "reports" / "open-pipeline-validation.md"
    out.write_text("\n".join(L) + "\n"); print(out); print(dict(kinds))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
