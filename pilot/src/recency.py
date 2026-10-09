"""recency_date / recency_days on every candidate so lists sort newest first.
recency_date = the latest of 'applied for' and 'issued' (permits: applied and last issue date; site plans: submitted and approval date;
Plan Review: applied and issued). recency_days = days from recency_date to today (0 = today). Recomputed on every build and report run."""
from __future__ import annotations
from datetime import date

SQL = {
    "candidates": "MAX(COALESCE(applied_date,''), COALESCE(last_issued_date,''), COALESCE(issued_date,''))",
    "site_plan_candidates": "MAX(COALESCE(submitted_date,''), COALESCE(approval_date,''))",
    "plan_review_candidates": "MAX(COALESCE(applied_date,''), COALESCE(issued_date,''))",
}


def refresh(con, today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    out = {}
    for table, expr in SQL.items():
        con.execute(f"UPDATE {table} SET recency_date = NULLIF({expr}, '')")
        con.execute(f"UPDATE {table} SET recency_days = CAST(julianday(?) - julianday(recency_date) AS INTEGER) WHERE recency_date IS NOT NULL", (today.isoformat(),))
        out[table] = con.execute(f"SELECT COUNT(*) FROM {table} WHERE recency_date IS NOT NULL").fetchone()[0]
    con.commit()
    return out
