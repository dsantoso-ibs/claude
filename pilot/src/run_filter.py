"""Build candidates from raw, apply filters, write reports/filter-summary.md + CSV of passed/excluded for hand check.
Usage: python -m src.run_filter [austin]"""
from __future__ import annotations
import csv
import random
import sys
from datetime import datetime, timezone

from src import config as cfgmod
from src.filter import apply
from src.normalize import build_candidates
from src.schema import connect


def main(source: str = "austin") -> None:
    cfg = cfgmod.load()
    con = connect(cfgmod.DB_PATH)
    n = build_candidates(con, source, cfg["sources"][source])
    counts = apply(con, source, cfg["filters"])
    rows = con.execute("SELECT c.*, f.passed, f.exclude_reason FROM candidates c JOIN filter_results f ON f.candidate_id=c.id "
                       "WHERE c.source=? ORDER BY c.valuation DESC", (source,)).fetchall()
    out = cfgmod.ROOT / "reports"
    cols = ["source_id", "passed", "exclude_reason", "valuation", "permit_type", "work_class", "use_class", "status",
            "address_norm", "contractor_name", "issued_date", "permit_count", "description", "name_removed"]
    with open(out / f"{source}-candidates.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    rnd = random.Random(7)
    passed = [r for r in rows if r["passed"]]
    excl = [r for r in rows if not r["passed"]]
    def table(rs):
        return "\n".join(f"| {r['source_id']} | {r['valuation']:,.0f} | {r['work_class']} | {r['use_class'][:60]} | {r['exclude_reason'] or ''} | {r['address_norm']} |" for r in rs)
    hdr = "| project | valuation | work class | use class | reason | address |\n|---|---|---|---|---|---|"
    md = [f"# Filter summary: {source}", f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}. {n} projects (raw permits grouped by project key).", "",
          f"**Passed: {counts.get('passed', 0)}** | Excluded: {len(rows) - counts.get('passed', 0)}", "",
          "| outcome / reason | projects |\n|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])] + [
          "", "## Hand-check sample: 20 passed", "", hdr, table(rnd.sample(passed, min(20, len(passed)))),
          "", "## Hand-check sample: 20 excluded", "", hdr,
          table(rnd.sample(excl, min(20, len(excl)))), ""]
    (out / "filter-summary.md").write_text("\n".join(md))
    print(counts)


if __name__ == "__main__":
    main(*(sys.argv[1:2] or ["austin"]))
