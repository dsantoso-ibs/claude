"""M2b: apply Section 5 rules at project level; every exclusion stores a reason. All thresholds from config.
No valuation rule: valuation only feeds the descriptive size_band field (src/sizeband.py)."""
from __future__ import annotations
import re


def _code(cls: str) -> str | None:
    m = re.match(r"^\s*[CR]\s*-\s*(\d+)", cls)
    return m.group(1) if m else None


def class_allowed(cls: str, fc: dict) -> str | None:
    """Return None if the permit class is an acceptable use, else the exclusion reason."""
    if any(k.lower() in cls.lower() for k in fc["exclude_class_keywords"]):
        return "excluded_class_keyword"
    if _code(cls) in fc["exclude_class_codes"]:
        return "single_family_or_duplex"
    if not re.search(fc["include_class_regex"], cls.strip(), re.I):
        return "not_commercial_or_multifamily"
    return None


def evaluate(cand: dict, fc: dict) -> tuple[bool, str | None]:
    """cand fields use '|'-joined sets for permit_type/work_class/use_class/status (project-level)."""
    types = set(cand["permit_type"].split("|"))
    if not types & set(fc["include_permit_types"]):
        return False, "trade_only"
    statuses = [s for s in cand["status"].split("|") if s]
    if statuses and all(any(s.lower().startswith(x.lower()) for x in fc["exclude_statuses"]) for s in statuses):
        return False, "status_excluded"
    works = set(cand["work_class"].split("|"))
    if not works & set(fc["include_work_classes"]):
        return False, "work_class_not_construction"
    classes = [c for c in cand["use_class"].split("|") if c]
    reasons = [class_allowed(c, fc) for c in classes]
    if all(reasons) or not classes:
        # report the most informative reason (single-family beats generic)
        return False, "single_family_or_duplex" if "single_family_or_duplex" in reasons else (reasons[0] or "no_use_class")
    ok_classes = [c for c, r in zip(classes, reasons) if r is None]
    if fc.get("exclude_description_regex") and re.search(fc["exclude_description_regex"], cand.get("description") or ""):
        return False, "solar_or_ev_trade"
    if all(_code(c) in fc.get("weak_class_codes", []) for c in ok_classes):
        return False, "structures_only"
    # remodel/addition-only projects need a commercial (C-) class
    if works <= set(fc["remodel_work_classes"]) | {""} and fc["require_commercial_for_remodel"] \
            and not any(c.strip().upper().startswith("C") for c in ok_classes):
        return False, "residential_remodel"
    return True, None


def apply(con, source: str, fc: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in con.execute("SELECT * FROM candidates WHERE source=?", (source,)).fetchall():
        passed, reason = evaluate(dict(r), fc)
        con.execute("INSERT INTO filter_results(candidate_id, passed, exclude_reason) VALUES(?,?,?) "
                    "ON CONFLICT(candidate_id) DO UPDATE SET passed=excluded.passed, exclude_reason=excluded.exclude_reason",
                    (r["id"], int(passed), reason))
        k = "passed" if passed else reason
        counts[k] = counts.get(k, 0) + 1
    con.commit()
    return counts
