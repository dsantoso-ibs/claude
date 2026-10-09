"""Applies the personal-name scrub (src/scrub_text.py) to the free-text fields of the three sources, before storage.

Fields scrubbed (everything else in a payload is either structured or already business-only):
  permits (raw_permits)            description
  site plans (raw_site_plans)      description_of_work, case_name
  Plan Review (raw_plan_reviews)   folder_description, project_name
A payload whose text changed gets `_name_removed: true` (sticky: re-scrubbing never clears it). Rows are never dropped.

  python -m src.scrub_pipeline rescrub     one-off / idempotent: re-scrub payloads already stored
"""
from __future__ import annotations
import json
import re
import sys
from typing import Iterable, Iterator

from src import config as cfgmod
from src.scrub_text import Scrubber, fit_common_words
from src.schema import connect

FIELDS = {"raw_permits": ["description"], "raw_site_plans": ["description_of_work", "case_name"], "raw_plan_reviews": ["folder_description", "project_name"]}
SOURCE_TABLE = {"austin": "raw_permits", "site_plans": "raw_site_plans", "plan_review": "raw_plan_reviews"}
ORG_KEYS = ("owner_organization_name", "applicant_organization_name", "applicant_org", "contractor_company_name", "other_organization_name")


def build_scrubber(con) -> Scrubber:
    """Protected business names and the project-word vocabulary come from the data already loaded (empty on a first run: base lists only)."""
    orgs, texts = set(), []
    for table, fields in FIELDS.items():
        for (p,) in con.execute(f"SELECT payload_json FROM {table}"):
            d = json.loads(p)
            orgs.update(d[k] for k in ORG_KEYS if d.get(k))
            texts.extend(d[f] for f in fields if d.get(f))
    return Scrubber(orgs, common_words=fit_common_words(texts))


_DEFAULT: Scrubber | None = None


def scrub_cell(text: str | None) -> str:
    """Scrub one free-text value with the default scrubber (no protected organizations). Used by the schema-discovery scripts for sample rows."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Scrubber()
    return _DEFAULT.scrub(text)[0] or ""


def scrub_payloads(payloads: list[dict], table: str, scrubber: Scrubber) -> int:
    """In place. Returns the number of payloads whose text changed."""
    fields = FIELDS[table]
    slots = [(i, f) for i, d in enumerate(payloads) for f in fields if d.get(f)]
    results = scrubber.scrub_many([payloads[i][f] for i, f in slots])
    changed = set()
    for (i, f), (clean, n) in zip(slots, results):
        if n:
            payloads[i][f] = clean
            changed.add(i)
    for i in changed:
        payloads[i]["_name_removed"] = True
    return len(changed)


def chunks(it: Iterable[dict], n: int = 400) -> Iterator[list[dict]]:
    buf: list[dict] = []
    for x in it:
        buf.append(x)
        if len(buf) >= n:
            yield buf; buf = []
    if buf:
        yield buf


def rescrub(con) -> dict[str, int]:
    sc = build_scrubber(con)
    out = {}
    for table in FIELDS:
        rows = con.execute(f"SELECT source, source_id, payload_json FROM {table}").fetchall()
        changed = 0
        for batch in chunks(rows, 800):
            payloads = [json.loads(r["payload_json"]) for r in batch]
            before = [r["payload_json"] for r in batch]
            scrub_payloads(payloads, table, sc)
            for r, p, was in zip(batch, payloads, before):
                if json.dumps(p) != was:
                    changed += 1
                    con.execute(f"UPDATE {table} SET payload_json=? WHERE source=? AND source_id=?", (json.dumps(p), r["source"], r["source_id"]))
        out[table] = changed
    con.commit()
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["rescrub"]:
        print(rescrub(connect(cfgmod.DB_PATH)))
