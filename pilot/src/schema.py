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
CREATE TABLE IF NOT EXISTS enrichments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL, provider TEXT NOT NULL,
  requested_at TEXT NOT NULL, cost_usd REAL, result_json TEXT, found_owner INTEGER, found_developer INTEGER,
  found_architect INTEGER, found_contact INTEGER);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, source TEXT NOT NULL,
  rows_fetched INTEGER, rows_new INTEGER, notes TEXT);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(DDL)
    return con
