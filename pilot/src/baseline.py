"""M3: baseline loading + matching, and the manual spot-check workflow used when no feed export is available.

CLI:
  python -m src.baseline load <csv> <origin> [--name COL --address COL --lat COL --lon COL --city COL]
  python -m src.baseline match [austin]
  python -m src.baseline sample [austin]          -> reports/manual-labels-austin.csv (fill in_baseline y/n/unsure)
  python -m src.baseline import-labels <csv>
"""
from __future__ import annotations
import csv
import json
import math
import random
import sys
from datetime import datetime, timezone

from rapidfuzz import fuzz

from src import config as cfgmod
from src.normalize import normalize_address
from src.schema import connect


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def score_pair(c: dict, b: dict, radius_m: float = 100) -> tuple[float, str]:
    """Best of: exact normalized address (1.0), fuzzy address, geo proximity (+ name similarity)."""
    best, method = 0.0, "none"
    if c["address_norm"] and b["address_norm"]:
        if c["address_norm"] == b["address_norm"]:
            return 1.0, "address_exact"
        r = fuzz.ratio(c["address_norm"], b["address_norm"]) / 100
        # same street number is required for a fuzzy address to count as strong
        same_num = c["address_norm"].split()[:1] == b["address_norm"].split()[:1]
        best, method = (r if same_num else r * 0.7), "address_fuzzy"
    if None not in (c["lat"], c["lon"], b["lat"], b["lon"]) and haversine_m(c["lat"], c["lon"], b["lat"], b["lon"]) <= radius_m:
        name = fuzz.token_set_ratio(c.get("description") or "", b.get("name") or "") / 100
        g = 0.6 + 0.4 * name   # within radius = review-level; name similarity pushes toward in_baseline
        if g > best:
            best, method = g, "geo_name"
    return best, method


def load_csv(con, path: str, origin: str, cols: dict[str, str]) -> int:
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            def g(k):
                return row.get(cols[k]) if cols.get(k) else None
            def num(v):
                try: return float(v)
                except (TypeError, ValueError): return None
            con.execute("INSERT INTO baseline_projects(origin, name, address_norm, lat, lon, city, raw_json) VALUES(?,?,?,?,?,?,?)",
                        (origin, g("name"), normalize_address(g("address")), num(g("lat")), num(g("lon")), g("city"), json.dumps(row)))
            n += 1
    con.commit()
    return n


def match(con, source: str, bcfg: dict) -> dict[str, int]:
    bases = [dict(r) for r in con.execute("SELECT * FROM baseline_projects")]
    counts = {"in_baseline": 0, "review": 0, "novel": 0, "kept_manual": 0}
    if not bases:
        return {"error": "no baseline loaded; use the manual sample workflow"}
    now = datetime.now(timezone.utc).isoformat()
    cands = con.execute("SELECT c.* FROM candidates c JOIN filter_results f ON f.candidate_id=c.id "
                        "WHERE c.source=? AND f.passed=1", (source,)).fetchall()
    for c in cands:
        c = dict(c)
        con.execute("DELETE FROM matches WHERE candidate_id=?", (c["id"],))
        top = (0.0, "none", None)
        for b in bases:
            s, m = score_pair(c, b, bcfg["match_geo_radius_m"])
            if s >= bcfg["review_score"]:
                con.execute("INSERT OR REPLACE INTO matches VALUES(?,?,?,?)", (c["id"], b["id"], s, m))
            if s > top[0]:
                top = (s, m, b["id"])
        label = "in_baseline" if top[0] >= bcfg["in_baseline_score"] else "review" if top[0] >= bcfg["review_score"] else "novel"
        existing = con.execute("SELECT method FROM candidate_labels WHERE candidate_id=?", (c["id"],)).fetchone()
        if existing and existing["method"] == "manual":
            counts["kept_manual"] += 1
            continue
        con.execute("INSERT INTO candidate_labels VALUES(?,?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET "
                    "label=excluded.label, method=excluded.method, score=excluded.score, labelled_at=excluded.labelled_at",
                    (c["id"], label, f"auto:{top[1]}", top[0], None, now))
        counts[label] += 1
    con.commit()
    return counts


def export_sample(con, source: str, bcfg: dict, out) -> int:
    rows = con.execute("SELECT c.* FROM candidates c JOIN filter_results f ON f.candidate_id=c.id "
                       "WHERE c.source=? AND f.passed=1 ORDER BY c.source_id", (source,)).fetchall()
    sample = random.Random(bcfg["manual_sample_seed"]).sample(rows, min(bcfg["manual_sample_size"], len(rows)))
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["candidate_id", "address", "valuation", "use_class", "contractor", "issued", "description",
                    "in_baseline (y/n/unsure)", "found_in (ibau/barbour/mps/baucore)", "note"])
        for r in sample:
            w.writerow([r["id"], r["address_norm"], f"{r['valuation']:.0f}", r["use_class"][:60], r["contractor_name"],
                        r["issued_date"], (r["description"] or "")[:140], "", "", ""])
    return len(sample)


def import_labels(con, path: str) -> dict[str, int]:
    m = {"y": "in_baseline", "n": "novel", "unsure": "review"}
    counts = {"in_baseline": 0, "novel": 0, "review": 0, "skipped": 0}
    now = datetime.now(timezone.utc).isoformat()
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ans = (row["in_baseline (y/n/unsure)"] or "").strip().lower()
            if ans not in m:
                counts["skipped"] += 1
                continue
            con.execute("INSERT INTO candidate_labels VALUES(?,?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET "
                        "label=excluded.label, method='manual', note=excluded.note, labelled_at=excluded.labelled_at",
                        (int(row["candidate_id"]), m[ans], "manual", None, row.get("found_in (ibau/barbour/mps/baucore)") or row.get("note"), now))
            counts[m[ans]] += 1
    con.commit()
    return counts


def main(argv: list[str]) -> None:
    cfg = cfgmod.load(); con = connect(cfgmod.DB_PATH)
    cmd, rest = argv[0], argv[1:]
    if cmd == "load":
        opt = {a[2:]: rest[i + 1] for i, a in enumerate(rest) if a.startswith("--")}
        cols = {k: opt.get(k) for k in ("name", "address", "lat", "lon", "city")}
        print(load_csv(con, rest[0], rest[1], cols), "baseline rows loaded")
    elif cmd == "match":
        print(match(con, rest[0] if rest else "austin", cfg["baseline"]))
    elif cmd == "sample":
        out = cfgmod.ROOT / "reports" / f"manual-labels-{rest[0] if rest else 'austin'}.csv"
        print(export_sample(con, rest[0] if rest else "austin", cfg["baseline"], out), "rows ->", out)
    elif cmd == "import-labels":
        print(import_labels(con, rest[0]))


if __name__ == "__main__":
    main(sys.argv[1:])
