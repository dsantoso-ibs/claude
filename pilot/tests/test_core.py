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


def test_valuation_does_not_affect_filter():
    for v in (0, 1, 40_000, 249_999, 250_000, 80_000_000):
        assert evaluate(cand(valuation=v), FC) == (True, None)
    assert evaluate(cand(valuation=5_000_000, use_class="R- 101 Single Family Houses"), FC)[1] == "single_family_or_duplex"


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


def test_size_bands():
    from src.sizeband import band
    sc = cfgmod.load()["size_band"]
    assert [band(v, sc) for v in (None, 0, 1, 1000)] == ["unknown"] * 4
    assert band(1001, sc) == "under_250k" and band(249_999, sc) == "under_250k"
    assert band(250_000, sc) == "250k_to_5m" and band(5_000_000, sc) == "250k_to_5m"
    assert band(5_000_001, sc) == "over_5m"


def test_size_band_best_available_valuation():
    from src.sizeband import assign
    cfg = cfgmod.load()
    con = connect(":memory:")
    con.execute("INSERT INTO candidates(source,source_id,valuation,first_seen_at) VALUES('austin','P1',1,'t'),('austin','P2',300000,'t')")
    con.execute("INSERT INTO plan_review_candidates(permit_number,valuation,passed) VALUES('PR1',9000000,1),('PR2',1,1)")
    con.execute("INSERT INTO plan_review_permit_links VALUES(1,'P1',1.0,'address_exact'),(2,'P2',1.0,'address_exact')")
    con.execute("INSERT INTO site_plan_candidates(folderrsn,passed) VALUES('S1',1),('S2',1)")
    con.execute("INSERT INTO site_plan_permit_links VALUES(1,'P1',1.0,'address_exact')")
    out = assign(con, cfg)
    row = lambda t, k, v: con.execute(f"SELECT size_band, size_source FROM {t} WHERE {k}=?", (v,)).fetchone()[:]
    assert row("candidates", "source_id", "P1") == ("over_5m", "linked_plan_review")     # $1 placeholder -> PR valuation
    assert row("candidates", "source_id", "P2") == ("250k_to_5m", "own")
    assert row("plan_review_candidates", "permit_number", "PR2") == ("250k_to_5m", "linked_permit")
    assert row("site_plan_candidates", "folderrsn", "S1")[0] == "over_5m"               # via linked permit project
    assert row("site_plan_candidates", "folderrsn", "S2")[0] == "unknown"
    assert out["site_plans"]["unknown"] == 1


def test_plan_review_link_requires_same_work_class():
    from src.phase2 import link_cases
    lc = cfgmod.load()["linking"]
    pr = dict(id=1, address_norm="1 MAIN ST", lat=None, lon=None, applied_date="2024-01-01", name="x", work_class="New")
    permits = [dict(source_id="remodel", address_norm="1 MAIN ST", lat=None, lon=None, issued_date="2024-02-01", description="", contractor_name=None, work_class="Remodel"),
               dict(source_id="new", address_norm="1 MAIN ST", lat=None, lon=None, issued_date="2024-09-01", description="", contractor_name=None, work_class="New|Shell")]
    same = lambda c, p: c["work_class"] in set(p["work_class"].split("|"))
    assert [g[1] for g in link_cases([pr], permits, "applied_date", lc, compat=same)] == ["new"]


def test_project_type_mapping_and_precedence():
    from src.project_type import type_from_works
    w = cfgmod.load()["project_type"]["work_class_map"]
    assert type_from_works("New", w) == "new_build" and type_from_works("Shell", w) == "shell"
    assert type_from_works("Addition", w) == "addition" and type_from_works("Addition and Remodel", w) == "addition"
    assert type_from_works("Remodel", w) == "remodel"
    assert type_from_works("New|Shell", w) == "new_build" and type_from_works("Remodel|Addition", w) == "addition"
    assert type_from_works("Demolition", w) == "other"


def test_default_set_excludes_remodel_and_keeps_rows():
    from src.project_type import assign
    cfg = cfgmod.load(); con = connect(":memory:")
    for i, wc in enumerate(["New", "Remodel", "Addition and Remodel"], 1):
        con.execute("INSERT INTO candidates(source,source_id,work_class,first_seen_at) VALUES('austin',?,?,'t')", (f"P{i}", wc))
        con.execute("INSERT INTO filter_results VALUES(?,1,NULL)", (i,))
    assign(con, cfg)
    got = {r["source_id"]: (r["project_type"], r["in_default"]) for r in con.execute("SELECT * FROM candidates")}
    assert got == {"P1": ("new_build", 1), "P2": ("remodel", 0), "P3": ("addition", 1)}
    assert con.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 3        # nothing deleted


def test_site_plan_type_from_link_then_hints():
    from src.project_type import assign
    cfg = cfgmod.load(); con = connect(":memory:")
    con.execute("INSERT INTO candidates(source,source_id,work_class,issued_date,first_seen_at) VALUES('austin','P1','Remodel','2025-01-01','t')")
    con.execute("INSERT INTO filter_results VALUES(1,1,NULL)")
    con.execute("INSERT INTO site_plan_candidates(folderrsn,case_name,work,passed) VALUES('A','x','Consolidated',1),('B','Tenant Improvement Suite','Consolidated',1),('C','y','Consolidated',1)")
    con.execute("INSERT INTO site_plan_permit_links VALUES(1,'P1',1.0,'address_exact')")
    assign(con, cfg)
    got = {r["folderrsn"]: (r["project_type"], r["type_source"], r["in_default"]) for r in con.execute("SELECT * FROM site_plan_candidates")}
    assert got["A"] == ("remodel", "linked_permit", 0)
    assert got["B"] == ("remodel", "name_or_work_hint", 0)
    assert got["C"] == ("unknown", "none", 1)         # unlinked, no hint: stays in the default set, counted separately


def test_label_sample_is_stratified_and_never_remodel():
    import random
    from src.label_sheets import stratified
    pool = [dict(id=i, size_band=b, project_type="new_build") for i, b in enumerate(["unknown"] * 50 + ["under_250k"] * 5 + ["250k_to_5m"] * 1 + ["over_5m"] * 0)]
    got = stratified(pool, 10, cfgmod.load()["label_sample"]["band_quota"], random.Random(1))
    assert len(got) == 10 and len({r["id"] for r in got}) == 10
    bands = [r["size_band"] for r in got]
    assert bands.count("250k_to_5m") == 1 and bands.count("under_250k") >= 2   # known sizes preferred when quota can't be met


def test_enrichment_hard_cap_and_privacy():
    from src.enrich import run, EnrichmentResult
    cfg = cfgmod.load(); cfg["enrichment"].update(enabled=True, daily_cost_cap_usd=0.05, stages=["plan_review_open"])
    con = connect(":memory:")
    for i in range(1, 6):
        con.execute("INSERT INTO plan_review_candidates(permit_number,project_name,address_norm,work_class,project_type,in_default,passed,applied_date,size_band)"
                    " VALUES(?,?,?,?,?,1,1,'2099-01-01','unknown')", (f"PR{i}", f"p{i}", f"{i} A ST", "New", "new_build"))
    class Paid:
        name = "paid"
        def est_cost(self, t): return 0.02
        def enrich(self, t): return EnrichmentResult(cost_usd=0.02, owner="Acme Holdings LLC", developer="John Smith")
    out = run(con, cfg, dry_run=False, enricher=Paid())
    assert out["enriched"] == 2 and out["spent_today_usd"] == 0.04 and out["stopped_by_cap"] == 3     # 3rd call would hit 0.06 > 0.05
    row = con.execute("SELECT found_owner, found_developer, result_json FROM enrichments").fetchone()
    assert row[0] == 1 and row[1] == 0 and "John Smith" not in row[2]                                  # individual dropped, never stored
    assert out["dropped_individual_names"] == 2
    again = run(con, cfg, dry_run=False, enricher=Paid())                                              # same day: cap already nearly spent
    assert again["enriched"] == 0


def test_enrichment_refuses_stub_and_dry_run_writes_nothing():
    import pytest
    from src.enrich import run
    cfg = cfgmod.load(); con = connect(":memory:")
    assert run(con, cfg, dry_run=True)["mode"] == "dry-run"
    with pytest.raises(PermissionError):
        run(con, cfg, dry_run=False)                       # enabled is false
    cfg["enrichment"]["enabled"] = True
    with pytest.raises(PermissionError):
        run(con, cfg, dry_run=False)                       # stub refused
    assert con.execute("SELECT COUNT(*) FROM enrichments").fetchone()[0] == 0


REMODEL_CASES = [
    ("Install monument sign for tenant", False, "non_project_signage"), ("Signage and ACM Paneling on Gas Canopy", False, "non_project_signage"),
    ("Interior demolition of suite", False, "non_project_demolition_only"), ("Selective demo", False, "non_project_demolition_only"),
    ("Re-roof existing office", False, "non_project_repair"), ("Foundation Repair", False, "non_project_repair"),
    ("TENANT IMPROVEMENT WITH LOCKER ROOMS and exit sign", True, None), ("Infill cased opening and add exit sign create two suites", True, None),
    ("Interior tenant improvement existing space. Demo and new interior walls", True, None), ("Demolition of walls and finishes. Construction of new walls", True, None),
    ("Interior remodel and repair of damaged wall", True, None), ("Tenant improvement; repair damaged ceiling", True, None),
    ("INSTALLATION OF PV MODULES ON EXISTING COMMERCIAL ROOF.", False, "solar_or_ev_trade"), ("Certificate of Occupancy", True, None),
]


def test_remodel_only_repair_signage_demolition_are_non_projects():
    fc = cfgmod.load()["filters"]
    base = dict(permit_type="BP", work_class="Remodel", use_class="C-1000 Commercial Remodel", status="Active")
    for desc, ok, reason in REMODEL_CASES:
        assert evaluate({**base, "description": desc}, fc) == (ok, reason), desc


def test_remodel_not_excluded_by_structures_only_or_class_keywords_and_use_is_not_ranked():
    fc = cfgmod.load()["filters"]
    base = dict(permit_type="BP", work_class="Remodel", status="Active", description="Interior finish out")
    for cls in ("C- 329 Com Structures Other Than Bldg", "C-1001 Commercial Finish Out", "C- 326 Schools & Other Educational Bldgs",
                "C- 324 Office, Bank & Professional Bldgs", "C- 105 Five or More Family Bldgs"):
        assert evaluate({**base, "use_class": cls}, fc) == (True, None), cls
    # a new build with only C-329 is still excluded (rule unchanged outside remodels)
    assert evaluate({**base, "work_class": "New", "use_class": "C- 329 Com Structures Other Than Bldg"}, fc)[1] == "structures_only"


def test_remodel_subtype():
    from src.remodel import subtype
    rc = cfgmod.load()["filters"]["remodel"]
    assert subtype("Interior Finish-Out for an Office/Warehouse (Suite 101)", ["C-1001 Commercial Finish Out"], rc) == "tenant_finish_out"
    assert subtype("Tenant improvement of existing retail space", ["C-1000 Commercial Remodel"], rc) == "tenant_finish_out"
    assert subtype("Interior remodel of 2nd floor", ["C-1000 Commercial Remodel"], rc) == "interior_remodel"
    assert subtype("Add/Remove equipment to existing tower", ["C-1000 Commercial Remodel"], rc) == "repair_or_other"
    assert subtype(None, [], rc) == "repair_or_other"


def test_recency_and_search_index():
    from datetime import date
    from src.recency import refresh
    from src.index import rebuild, search
    con = connect(":memory:")
    con.execute("INSERT INTO candidates(source,source_id,applied_date,last_issued_date,issued_date,description,applicant_org,contractor_name,address_raw,address_norm,use_class,first_seen_at,project_type,remodel_subtype)"
                " VALUES('austin','A','2026-01-01','2026-03-01','2026-03-01','tenant finish out for bakery','Acme Design','Beta Builders','1 Main Street','1 MAIN ST','C-1001','t','remodel','tenant_finish_out'),"
                "('austin','B','2026-09-01','2026-09-20','2026-09-20','tenant finish out clinic','Zed','Yoyo Co','2 Oak Ave','2 OAK AVE','C-1001','t','remodel','tenant_finish_out')")
    con.execute("INSERT INTO filter_results VALUES(1,1,NULL),(2,1,NULL)")
    refresh(con, date(2026, 10, 1))
    assert con.execute("SELECT recency_date, recency_days FROM candidates WHERE source_id='B'").fetchone()[:] == ("2026-09-20", 11)
    assert con.execute("SELECT recency_days FROM candidates WHERE source_id='A'").fetchone()[0] == 214
    rebuild(con)
    got = search(con, "tenant finish out")
    assert [r["address"] for r in got] == ["2 Oak Ave", "1 Main Street"]            # newest first
    assert [r["address"] for r in search(con, "Beta Builders")] == ["1 Main Street"]   # contractor is searchable
    assert [r["address"] for r in search(con, "Zed")] == ["2 Oak Ave"]                 # applicant is searchable


def test_enrichment_never_targets_remodels():
    from src.enrich import targets
    cfg = cfgmod.load(); con = connect(":memory:")
    con.execute("INSERT INTO plan_review_candidates(permit_number,project_name,address_norm,work_class,project_type,in_default,passed,applied_date,size_band)"
                " VALUES('PR1','a','1 A ST','Remodel','remodel',0,1,'2099-01-01','unknown'),('PR2','b','2 A ST','New','new_build',1,1,'2099-01-01','unknown')")
    got = targets(con, cfg, "x")
    assert [t["ref_id"] for t in got] == [2]


def test_clean_org_strips_permit_system_tags():
    from src.entities import clean_org
    assert clean_org("Kimley-Horn (MAIN)") == "Kimley-Horn" and clean_org("Joeris General Contractors***MAIN***") == "Joeris General Contractors"
    assert clean_org("MAIN**") is None and clean_org("**MAIN") is None and clean_org(None) is None
    assert clean_org("Mainstreet Builders") == "Mainstreet Builders"          # a word starting with MAIN is not the tag
