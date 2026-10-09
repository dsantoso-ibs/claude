"""Personal-name scrub for free-text descriptions (src/scrub_text.py, src/scrub_pipeline.py).

The 10 sample descriptions use SYNTHETIC names in realistic permit wording (no real people). Each must lose the person's name (and any phone/email),
keep the business entity names and the project wording, and be counted as a removal (the flag source).
The scrub is heuristic; these are the patterns it is expected to cover: contact lines, titles, "<Surname> Residence", phone/email, and
free-standing first+last names recognised by the NER model and the name lists.
"""
import json

import pytest

pytest.importorskip("spacy")
pytest.importorskip("faker")
try:
    import spacy
    spacy.load("en_core_web_sm")
except Exception:                                   # pragma: no cover
    pytest.skip("spaCy model en_core_web_sm not installed (python -m spacy download en_core_web_sm)", allow_module_level=True)

from src.scrub_text import Scrubber, NAME_TOKEN, CONTACT_TOKEN
from src.scrub_pipeline import scrub_payloads
from src.schema import connect
from src.normalize import build_candidates
from src import config as cfgmod

PROTECTED_ORGS = ["Kimley-Horn", "Corvus Construction", "Acme Holdings LLC", "Austin Independent School District"]
COMMON = ["restrooms", "relocate", "improvement", "retail", "finish", "tenant", "remodel", "kitchen"]

# (description, names that must disappear, text that must survive)
SAMPLES = [
    ("Tenant finish out for Acme Holdings LLC. Contact: John Whitaker 512-555-0147 for access.",
     ["John Whitaker", "Whitaker", "512-555-0147"], ["Tenant finish out", "Acme Holdings LLC", "for access"]),
    ("INTERIOR REMODEL OF OFFICE SUITE 210. ATTN: MARIA GONZALEZ, EMAIL maria.gonzalez@example.com",
     ["MARIA GONZALEZ", "GONZALEZ", "maria.gonzalez@example.com"], ["INTERIOR REMODEL OF OFFICE SUITE 210"]),
    ("New kitchen and bath remodel for Mr. Robert Delgado at the Delgado Residence.",
     ["Robert Delgado", "Delgado Residence"], ["kitchen and bath remodel", "Residence"]),
    ("Owner: Susan P. Lindqvist - add 2 restrooms per plan review comments.",
     ["Susan", "Lindqvist"], ["add 2 restrooms per plan review comments"]),
    ("Per conversation with Dr. Patel, relocate wall between suites 100 and 110.",
     ["Patel"], ["relocate wall between suites 100 and 110"]),
    ("Remodel of retail space for the Henderson Residence; contractor Corvus Construction.",
     ["Henderson"], ["Remodel of retail space", "Residence", "Corvus Construction"]),
    ("Submitted by Thomas O'Brien (Kimley-Horn) for site improvements at 512 Sabine St.",
     ["Thomas", "O'Brien"], ["Kimley-Horn", "site improvements", "512 Sabine St"]),
    ("c/o Jennifer Alvarez, 5th floor tenant improvement, call (512) 555 0199",
     ["Jennifer Alvarez", "Alvarez", "(512) 555 0199"], ["5th floor tenant improvement"]),
    ("Interior finish-out of existing retail space at 3500 E Parmer Ln, Suite 2152; owner Michael Chen requests early start.",
     ["Michael Chen", "Chen"], ["Interior finish-out of existing retail space", "3500 E Parmer Ln", "Suite 2152"]),
    ("Revised plans after meeting with David Thompson and Karen Mitchell; replace RTU on roof of Austin Independent School District admin building.",
     ["David Thompson", "Karen Mitchell", "Thompson", "Mitchell"], ["replace RTU on roof", "Austin Independent School District", "admin building"]),
]


@pytest.fixture(scope="module")
def scrubber():
    return Scrubber(PROTECTED_ORGS, common_words=COMMON)


@pytest.mark.parametrize("text,gone,kept", SAMPLES, ids=[f"sample{i + 1}" for i in range(len(SAMPLES))])
def test_personal_names_removed_and_business_and_project_wording_kept(scrubber, text, gone, kept):
    clean, removed = scrubber.scrub(text)
    assert removed >= 1, "a removal must be counted (it drives the name_removed flag)"
    assert NAME_TOKEN in clean or CONTACT_TOKEN in clean
    for g in gone:
        assert g not in clean, f"{g!r} still present in {clean!r}"
    for k in kept:
        assert k in clean, f"{k!r} was lost from {clean!r}"


def test_exactly_ten_samples():
    assert len(SAMPLES) == 10


@pytest.mark.parametrize("text", [
    "Roof Replacement and Transfer Switch for Dish Wireless antennas; Shade Structure and Pool Deck.",
    "Install James Hardie siding and Tamko Titan shingles at the existing building.",
    "New 232 unit multi family building at 512 Sabine Parkway with turn lane on Lamar Boulevard.",
    "Interior Remodel of Retail Space, Kitchen Remodel and ADA Compliant restrooms for Kimley-Horn project.",
    "Pkg B garage and Pkg C shell, Phase 2, Building 4.",
    "Tenant improvement for Corvus Construction in Suite 140; sprinkler and fire alarm.",
    "",
])
def test_project_wording_brands_addresses_and_businesses_are_not_touched(scrubber, text):
    clean, removed = scrubber.scrub(text)
    assert clean == text and removed == 0


def test_scrub_is_idempotent(scrubber):
    for text, _, _ in SAMPLES:
        once, _ = scrubber.scrub(text)
        twice, again = scrubber.scrub(once)
        assert twice == once and again == 0


def test_none_and_blank_are_passed_through(scrubber):
    assert scrubber.scrub(None) == (None, 0)
    assert scrubber.scrub("   ") == ("   ", 0)


def test_payload_scrub_flags_only_changed_rows_and_other_fields_untouched(scrubber):
    payloads = [{"description": SAMPLES[0][0], "permit_number": "1", "contractor_company_name": "Acme Holdings LLC"},
                {"description": "Interior remodel of retail space", "permit_number": "2"}]
    changed = scrub_payloads(payloads, "raw_permits", scrubber)
    assert changed == 1
    assert payloads[0]["_name_removed"] is True and "_name_removed" not in payloads[1]
    assert "John Whitaker" not in json.dumps(payloads[0])
    assert payloads[0]["contractor_company_name"] == "Acme Holdings LLC" and payloads[1]["description"] == "Interior remodel of retail space"


def test_flag_reaches_the_candidate_and_text_is_scrubbed_in_it():
    cfg = cfgmod.load(); scfg = cfg["sources"]["austin"]
    con = connect(":memory:")
    base = dict(permittype="BP", permit_class="C-1000 Commercial Remodel", work_class="Remodel", total_job_valuation="0", permit_location="1 Main St",
                issue_date="2026-01-02T00:00:00.000", status_current="Active", masterpermitnum="9")
    a = {**base, "permit_number": "A", "description": "Tenant finish out. Contact: [NAME] [CONTACT]", "_name_removed": True}
    b = {**base, "permit_number": "B", "description": "Interior remodel", "masterpermitnum": "10"}
    for p in (a, b):
        con.execute("INSERT INTO raw_permits VALUES('austin',?,?,?)", (p["permit_number"], "t", json.dumps(p)))
    build_candidates(con, "austin", scfg)
    got = {r["source_id"]: (r["name_removed"], r["description"]) for r in con.execute("SELECT source_id, name_removed, description FROM candidates")}
    assert got["9"][0] == 1 and "[NAME]" in got["9"][1]
    assert got["10"][0] == 0


@pytest.mark.parametrize("text", [
    "1901 N. Lamar", "E. Cesar Chavez", "W. Martin Luther King Jr. Boulevard & Nueces Street", "1723 E. Oltorf", "4811 S. Congress Concept SP",
    "AISD - Burnet MS Modernization- EXPIRED", "RRISD Grisham Ms Artificial Turf Field", "West Travis Co PUA Circle Dr Intermediate Pump Station & Ground Storage Tank",
    "The Norwood House Project: House", "Ryder N. Austin", "1111 N. Weston Boat Dock",
])
def test_street_directions_school_and_drive_abbreviations_and_house_projects_are_not_names(text):
    sc = Scrubber(streets=["cesar chavez", "martin luther king"])
    assert sc.scrub(text, ner=False) == (text, 0)
    assert sc.scrub(text) == (text, 0)


def test_initial_surname_still_removed_for_a_non_directional_initial_and_after_a_cue():
    sc = Scrubber()
    assert sc.scrub("Remodel per J. Rodriguez comments")[0] == "Remodel per [NAME] comments"
    assert "Whitaker" not in sc.scrub("Contact: W. Whitaker for access")[0]
