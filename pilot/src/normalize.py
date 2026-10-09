"""M2a: raw permits -> project-level candidates (grouped by project_key) + address normalization."""
from __future__ import annotations
import json
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
        con.execute(
            "INSERT INTO candidates(source, source_id, address_norm, lat, lon, valuation, permit_type, work_class, use_class,"
            " issued_date, description, contractor_name, status, permit_count, permit_numbers, first_seen_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(source, source_id) DO UPDATE SET address_norm=excluded.address_norm, lat=excluded.lat, lon=excluded.lon,"
            " valuation=excluded.valuation, permit_type=excluded.permit_type, work_class=excluded.work_class,"
            " use_class=excluded.use_class, issued_date=excluded.issued_date, description=excluded.description,"
            " contractor_name=excluded.contractor_name, status=excluded.status, permit_count=excluded.permit_count,"
            " permit_numbers=excluded.permit_numbers",
            (source, key, normalize_address(addr), _f(rep.get(fm["lat"])), _f(rep.get(fm["lon"])),
             max((_f(x.get(fm["valuation"])) or 0) for x in rows),
             "|".join(sorted({x.get(fm["permit_type"]) or "" for x in rows})),
             "|".join(sorted({x.get(fm["work_class"]) or "" for x in rows})),
             "|".join(sorted({x.get(fm["permit_class"]) or "" for x in rows})),
             min((x.get(fm["issued"]) or "")[:10] for x in rows), (rep.get(fm["description"]) or "")[:500],
             rep.get(fm["company"]) or rep.get(fm["company_alt"]),
             "|".join(sorted({x.get(fm["status"]) or "" for x in rows})), len(rows),
             "|".join(sorted(x[fm["permit_number"]] for x in rows)), now))
    con.commit()
    return len(groups)
