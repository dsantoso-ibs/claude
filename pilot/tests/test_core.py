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


def test_baseline_scoring():
    from src.baseline import score_pair
    c = dict(address_norm="512 SABINE ST", lat=30.2659, lon=-97.7363, description="Mixed use multi-family complex")
    assert score_pair(c, dict(address_norm="512 SABINE ST", lat=None, lon=None, name="x"))[0] == 1.0
    s, m = score_pair(c, dict(address_norm="9 OTHER RD", lat=30.2660, lon=-97.7363, name="Sabine multi-family complex"))
    assert m == "geo_name" and 0.6 <= s <= 1.0
    far = score_pair(c, dict(address_norm="9 OTHER RD", lat=30.40, lon=-97.70, name="Something"))
    assert far[0] < 0.6
    near_num = score_pair(c, dict(address_norm="512 SABINE STREET", lat=None, lon=None, name=""))
    assert near_num[0] >= 0.85


def test_verdict_rules():
    from src.report import verdict
    d = cfgmod.load()["decision"]
    assert verdict(0, 0, None, d)[0] == "NOT MEASURABLE"
    assert verdict(30, 10, None, d)[0].startswith("PROVISIONAL CONTINUE")
    assert verdict(2, 38, None, d)[0].startswith("STOP")
    assert verdict(10, 30, None, d)[0] == "INCONCLUSIVE"
    assert verdict(20, 20, 0.6, d)[0] == "CONTINUE"
    assert verdict(20, 20, 0.3, d)[0] == "STOP / RETHINK"


def test_manual_label_roundtrip_and_report_counts(tmp_path):
    from src.baseline import import_labels, match
    con = connect(":memory:")
    con.execute("INSERT INTO candidates(source,source_id,address_norm,valuation,permit_type,work_class,use_class,issued_date,status,permit_count,permit_numbers,first_seen_at)"
                " VALUES('austin','1','1 A ST',1e6,'BP','New','C- 105','2026-01-01','Active',1,'x','t')")
    con.execute("INSERT INTO filter_results VALUES(1,1,NULL)")
    f = tmp_path / "l.csv"
    f.write_text("candidate_id,address,in_baseline (y/n/unsure),found_in (ibau/barbour/mps/baucore),note\n1,1 A ST,n,,\n")
    assert import_labels(con, str(f))["novel"] == 1
    assert con.execute("SELECT label, method FROM candidate_labels").fetchone()[:] == ("novel", "manual")
    assert "error" in match(con, "austin", cfgmod.load()["baseline"])   # no baseline loaded -> no silent overwrite


def test_fuzzy_address_needs_same_street():
    from src.baseline import score_pair
    a = dict(address_norm="301 W 14TH ST", lat=None, lon=None, description="")
    assert score_pair(a, dict(address_norm="301 W 5TH ST", lat=None, lon=None, name=""))[0] < 0.85
    assert score_pair(a, dict(address_norm="301 W 14TH ST", lat=None, lon=None, name=""))[0] == 1.0


def test_link_requires_permit_after_case_and_blocks_by_address():
    from src.phase2 import link_cases
    lc = cfgmod.load()["linking"]
    case = dict(id=1, address_norm="1 MAIN ST", lat=None, lon=None, submitted_date="2024-01-01", name="x")
    permits = [dict(source_id="p1", address_norm="1 MAIN ST", lat=None, lon=None, issued_date="2025-01-01", description="", contractor_name=None),
               dict(source_id="p2", address_norm="1 MAIN ST", lat=None, lon=None, issued_date="2023-01-01", description="", contractor_name=None)]
    got = link_cases([case], permits, "submitted_date", lc)
    assert [g[1] for g in got] == ["p1"]            # earlier permit is not this case's permit


def test_use_classification():
    from src.phase2 import classify_use
    rules = cfgmod.load()["site_plan_filters"]["use_rules"]
    assert classify_use("Commercial Multi Family", rules) == "multifamily"
    assert classify_use("Boat Dock", rules) == "excluded_infrastructure"
    assert classify_use("Single Family", rules) == "single_family"
    assert classify_use("Warehouse", rules) == "industrial"
    assert classify_use("Unk", rules) == "unknown_use" and classify_use(None, rules) == "unknown_use"
    assert classify_use("Housing", rules) == "housing_unclear"


def test_entity_check():
    from src.entities import clean_entity
    assert clean_entity("Century Land Holdings II, LLC") == ("Century Land Holdings II, LLC", False)
    assert clean_entity("John Smith") == (None, True)
    assert clean_entity(None) == (None, False)


def test_site_plan_filter_rules():
    from src.phase2 import evaluate_site_plan
    fc = cfgmod.load()["site_plan_filters"]
    base = dict(submitted_date="2025-01-01", status="Approved and Released", work="Consolidated", use_class="commercial", case_name="Foo Center")
    assert evaluate_site_plan(base, fc) == (True, None)
    assert evaluate_site_plan({**base, "case_name": "Domain 4 Demo"}, fc)[1] == "demolition_only"
    assert evaluate_site_plan({**base, "status": "Expired"}, fc)[1] == "status_excluded"
    assert evaluate_site_plan({**base, "work": "Extension"}, fc)[1] == "work_not_building_project"
    assert evaluate_site_plan({**base, "use_class": "unknown_use"}, fc)[1] == "unknown_use"
    assert evaluate_site_plan({**base, "submitted_date": None}, fc)[1] == "no_submission_date"


def test_unreported_valuation_is_its_own_reason():
    assert evaluate(cand(valuation=1), FC) == (False, "valuation_unreported")
    assert evaluate(cand(valuation=0), FC) == (False, "valuation_unreported")
    assert evaluate(cand(valuation=40_000), FC) == (False, "below_valuation")
