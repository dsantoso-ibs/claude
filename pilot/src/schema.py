"""SQLite DDL + helpers. Section 6 of the spec, with one deliberate deviation:
candidates are PROJECT-level (grouped by project_key), not permit-level, because total_job_valuation
is copied onto every permit of a project."""
from __future__ import annotations
import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS raw_permits(
  source TEXT NOT NULL, source_id TEXT NOT NULL, fetched_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  PRIMARY KEY(source, source_id));
CREATE TABLE IF NOT EXISTS candidates(
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, source_id TEXT NOT NULL,  -- source_id = project_key
  address_norm TEXT, lat REAL, lon REAL, valuation REAL, permit_type TEXT, work_class TEXT, use_class TEXT,
  issued_date TEXT, description TEXT, contractor_name TEXT, status TEXT, permit_count INTEGER,
  permit_numbers TEXT, first_seen_at TEXT NOT NULL, UNIQUE(source, source_id));
CREATE TABLE IF NOT EXISTS filter_results(
  candidate_id INTEGER PRIMARY KEY REFERENCES candidates(id), passed INTEGER NOT NULL, exclude_reason TEXT);
CREATE TABLE IF NOT EXISTS baseline_projects(
  id INTEGER PRIMARY KEY AUTOINCREMENT, origin TEXT NOT NULL, name TEXT, address_norm TEXT,
  lat REAL, lon REAL, city TEXT, raw_json TEXT);
CREATE TABLE IF NOT EXISTS matches(
  candidate_id INTEGER NOT NULL, baseline_id INTEGER NOT NULL, score REAL, method TEXT,
  PRIMARY KEY(candidate_id, baseline_id));
CREATE TABLE IF NOT EXISTS candidate_labels(   -- in_baseline | novel | review; manual overrides auto
  candidate_id INTEGER PRIMARY KEY REFERENCES candidates(id), label TEXT NOT NULL, method TEXT NOT NULL,
  score REAL, note TEXT, labelled_at TEXT);
CREATE TABLE IF NOT EXISTS raw_site_plans(source TEXT NOT NULL, source_id TEXT NOT NULL, fetched_at TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(source, source_id));
CREATE TABLE IF NOT EXISTS raw_plan_reviews(source TEXT NOT NULL, source_id TEXT NOT NULL, fetched_at TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(source, source_id));
CREATE TABLE IF NOT EXISTS site_plan_candidates(
  id INTEGER PRIMARY KEY AUTOINCREMENT, folderrsn TEXT NOT NULL UNIQUE, case_number TEXT, case_name TEXT, address_norm TEXT,
  lat REAL, lon REAL, proposed_use TEXT, use_class TEXT, work TEXT, status TEXT, submitted_date TEXT, approval_date TEXT,
  applicant_org TEXT, owner_entity TEXT, owner_is_individual INTEGER, size_hint TEXT, multifamily_hint INTEGER, first_seen_at TEXT,
  passed INTEGER, exclude_reason TEXT);
CREATE TABLE IF NOT EXISTS site_plan_permit_links(
  case_id INTEGER NOT NULL, project_key TEXT NOT NULL, score REAL, method TEXT, PRIMARY KEY(case_id, project_key));
CREATE TABLE IF NOT EXISTS plan_review_candidates(
  id INTEGER PRIMARY KEY AUTOINCREMENT, permit_number TEXT NOT NULL UNIQUE, project_name TEXT, address_norm TEXT, lat REAL, lon REAL,
  valuation REAL, work_class TEXT, use_class TEXT, status TEXT, applied_date TEXT, issued_date TEXT, owner_entity TEXT,
  owner_is_individual INTEGER, applicant_org TEXT, units REAL, passed INTEGER, exclude_reason TEXT);
CREATE TABLE IF NOT EXISTS plan_review_permit_links(
  pr_id INTEGER NOT NULL, project_key TEXT NOT NULL, score REAL, method TEXT, PRIMARY KEY(pr_id, project_key));
CREATE TABLE IF NOT EXISTS site_plan_labels(case_id INTEGER PRIMARY KEY, label TEXT NOT NULL, method TEXT NOT NULL, note TEXT, labelled_at TEXT);
CREATE TABLE IF NOT EXISTS enrichments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL, provider TEXT NOT NULL,
  requested_at TEXT NOT NULL, cost_usd REAL, result_json TEXT, found_owner INTEGER, found_developer INTEGER,
  found_architect INTEGER, found_contact INTEGER);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, source TEXT NOT NULL,
  rows_fetched INTEGER, rows_new INTEGER, notes TEXT);
"""


SIZE_COLS = {"candidates": "valuation", "site_plan_candidates": "exclude_reason", "plan_review_candidates": "exclude_reason"}


def _migrate(con: sqlite3.Connection) -> None:
    """Add the size_band columns to databases created before they existed."""
    for table in SIZE_COLS:
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        for col, typ in (("size_band", "TEXT"), ("size_usd", "REAL"), ("size_source", "TEXT")):
            if col not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(DDL)
    _migrate(con)
    return con
