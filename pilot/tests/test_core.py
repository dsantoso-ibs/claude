import sqlite3
from src import config as cfgmod
from src.filter import evaluate
from src.normalize import normalize_address, build_candidates
from src.schema import connect
from src.ingest import scrub

FC = cfgmod.load()["filters"]


def cand(**kw):
    base = dict(valuation=1_000_000, permit_type="BP", work_class="New", use_class="C- 105 Five or More Family Bldgs",
                status="Active", description="New multifamily")
    return {**base, **kw}


def test_address_normalization():
    assert normalize_address("512 Sabine Street, Unit 4") == "512 SABINE ST"
    assert normalize_address("1900 North Lamar Blvd. #200") == "1900 N LAMAR BLVD"
    assert normalize_address("100 Congress Avenue Suite 5A") == "100 CONGRESS AVE"
    assert normalize_address(None) == ""


def test_passes_multifamily_new():
    assert evaluate(cand(), FC) == (True, None)


def test_valuation_threshold():
    assert evaluate(cand(valuation=249_999), FC) == (False, "below_valuation")
    assert evaluate(cand(valuation=250_000), FC)[0]


def test_trade_only_excluded():
    assert evaluate(cand(permit_type="EP|PP"), FC) == (False, "trade_only")


def test_single_family_and_duplex_excluded():
    assert evaluate(cand(use_class="R- 101 Single Family Houses"), FC)[1] == "single_family_or_duplex"
    assert evaluate(cand(use_class="R- 103 Two Family Bldgs"), FC)[1] == "single_family_or_duplex"
    assert evaluate(cand(use_class="C- 101 Single Family Houses"), FC)[1] == "single_family_or_duplex"


def test_residential_remodel_excluded_commercial_remodel_kept():
    assert not evaluate(cand(work_class="Addition and Remodel", use_class="R- 434 Addition & Alterations"), FC)[0]
    assert evaluate(cand(work_class="Remodel", use_class="C-1000 Commercial Remodel"), FC)[0]


def test_non_construction_work_class():
    assert evaluate(cand(work_class="Interior Demo Non-Structural"), FC)[1] == "work_class_not_construction"


def test_status_excluded():
    assert evaluate(cand(status="VOID"), FC)[1] == "status_excluded"
    assert evaluate(cand(status="Active|VOID"), FC)[0]


def test_structures_only_and_solar():
    assert evaluate(cand(use_class="C- 329 Com Structures Other Than Bldg"), FC)[1] == "structures_only"
    assert evaluate(cand(use_class="C- 105 Five or More Family Bldgs|C- 329 Com Structures Other Than Bldg"), FC)[0]
    assert evaluate(cand(description="Installation of 368 kW rooftop PV system"), FC)[1] == "solar_or_ev_trade"


def test_scrub_drops_personal_fields():
    out = scrub({"applicant_full_name": "X", "applicant_org": "Ryan", "contractor_phone": "1"},
                cfgmod.load()["sources"]["austin"]["drop_fields"])
    assert out == {"applicant_org": "Ryan"}


def test_grouping_by_master_permit_and_idempotent():
    import json
    cfg = cfgmod.load(); scfg = cfg["sources"]["austin"]
    con = connect(":memory:")
    base = dict(permittype="BP", permit_class="C- 105 Five or More Family Bldgs", work_class="New",
                total_job_valuation="79500000", permit_location="512 Sabine St", issue_date="2026-07-01T00:00:00.000",
                status_current="Active", masterpermitnum="1")
    for n in ("A", "B", "C"):
        con.execute("INSERT INTO raw_permits VALUES('austin',?,?,?)", (n, "t", json.dumps({**base, "permit_number": n})))
    assert build_candidates(con, "austin", scfg) == 1
    assert build_candidates(con, "austin", scfg) == 1
    row = con.execute("SELECT permit_count, valuation FROM candidates").fetchone()
    assert (row["permit_count"], row["valuation"]) == (3, 79_500_000)
    assert con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 1
