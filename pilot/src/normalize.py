"""M2a: raw permits -> project-level candidates (grouped by project_key) + address normalization."""
from __future__ import annotations
import json

from src.entities import clean_org
import re
from collections import defaultdict
from datetime import datetime, timezone

_SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR", "ROAD": "RD", "LANE": "LN",
           "COURT": "CT", "PLACE": "PL", "PARKWAY": "PKWY", "HIGHWAY": "HWY", "CIRCLE": "CIR", "TRAIL": "TRL",
           "TERRACE": "TER", "SUITE": "STE", "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}
_UNIT = re.compile(r"\s*(?:#|\b(?:STE|SUITE|UNIT|APT|BLDG|BUILDING|FL|FLOOR|SPC|RM)\b)\s*[\w-]*.*$")


def normalize_address(addr: str | None) -> str:
    if not addr:
        return ""
    a = re.sub(r"[.,]", " ", addr.upper())
    a = _UNIT.sub("", a)
    a = re.sub(r"\s+", " ", a).strip()
    return " ".join(_SUFFIX.get(t, t) for t in a.split())


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def project_key(row: dict, fields: list[str]) -> str:
    for f in fields:
        if row.get(f):
            return str(row[f])
    raise ValueError("no project key")


def build_candidates(con, source: str, scfg: dict) -> int:
    fm = scfg["field_map"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in con.execute("SELECT payload_json FROM raw_permits WHERE source=?", (source,)):
        row = json.loads(r["payload_json"])
        groups[project_key(row, scfg["project_key_fields"])].append(row)
    now = datetime.now(timezone.utc).isoformat()
    for key, rows in groups.items():
        # representative = highest-valuation permit; prefer a BP so type/class reflect the building permit
        rows.sort(key=lambda x: (x.get(fm["permit_type"]) == "BP", _f(x.get(fm["valuation"])) or 0), reverse=True)
        rep = rows[0]
        addr = rep.get(fm["address"]) or rep.get(fm["address_fallback"])
        cols = ("address_norm", "lat", "lon", "valuation", "permit_type", "work_class", "use_class", "issued_date", "description", "contractor_name",
                "status", "permit_count", "permit_numbers", "applicant_org", "address_raw", "applied_date", "last_issued_date", "name_removed")
        vals = (normalize_address(addr), _f(rep.get(fm["lat"])), _f(rep.get(fm["lon"])), max((_f(x.get(fm["valuation"])) or 0) for x in rows),
                "|".join(sorted({x.get(fm["permit_type"]) or "" for x in rows})), "|".join(sorted({x.get(fm["work_class"]) or "" for x in rows})),
                "|".join(sorted({x.get(fm["permit_class"]) or "" for x in rows})), min((x.get(fm["issued"]) or "")[:10] for x in rows),
                (rep.get(fm["description"]) or "")[:500],
                clean_org(next((x.get(fm["company"]) for x in rows if clean_org(x.get(fm["company"]))), None)),      # contractor only (applicant is kept separately)
                "|".join(sorted({x.get(fm["status"]) or "" for x in rows})), len(rows), "|".join(sorted(x[fm["permit_number"]] for x in rows)),
                clean_org(next((x.get(fm["company_alt"]) for x in rows if clean_org(x.get(fm["company_alt"]))), None)), addr,
                min(((x.get("applieddate") or "")[:10] or "9999") for x in rows).replace("9999", "") or None,
                max((x.get(fm["issued"]) or "")[:10] for x in rows) or None,
                int(any(x.get("_name_removed") for x in rows)))
        con.execute(f"INSERT INTO candidates(source, source_id, first_seen_at, {', '.join(cols)}) VALUES(?,?,?,{','.join('?' * len(cols))}) "
                    f"ON CONFLICT(source, source_id) DO UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in cols)}", (source, key, now) + vals)
    con.commit()
    return len(groups)
