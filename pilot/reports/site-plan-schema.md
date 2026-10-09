# M7.0 reviewer summary: Site Plan Cases (`mavg-96ck`)
*Hand-written from the auto-profile below plus ad-hoc queries run 2026-10-09. The auto-generated detail follows.*

**Coverage and freshness.** 23,760 cases; `application_start_date` runs 1981 to **2026-10-08**, so it is current (metadata updated today). **1,015 cases started in the last 24 months, about 42 per month, 39 in the last 28 days.** The 24-month backfill is small (1 page of API calls).

**Submission date field:** `application_start_date` (98.3% filled; 411 rows null, those cannot be lead-timed). Other dates: `approval_date` (27.8%), `final_date` (21.3%), `status_date` (100%). `update_date` is the same value for every row (2026-10-09): it is an export stamp, not a record-change date, so it cannot drive a delta. Use `status_date` or `application_start_date` with an overlap window.

**Status values (24 months):** Approved and Released 331, Expired 227, Inactive 118, Awaiting Update 95, In Review 70, CC Approved 31, CC Pending 24, Withdrawn 21, Waiting on Legal 20, Intake Pending 17, Pending 13, CC Rejected 13, plus a long tail. Exclude candidates: Expired, Withdrawn, Denied, VOID, Aborted, Cancelled, Inactive, Intake Rejected, CC Rejected. Open-pipeline candidates: In Review, Pending, Intake*, Awaiting Update, Waiting on Legal/Fiscal, Scheduled for Hearing, CC Pending, CC Approved, Approved (not yet built).

**Proposed use (`proposed_land_use`, 24 months, clean categories):** Commercial 645, Public/Civic 101, Housing 93, Mixed Use (Residential/Commercial) 61, Boat Dock 58, Industrial 27, Horizontal Infrastructure 24, other 6. (Older rows hold free text: 2,110 distinct values overall.) **`Housing` does not separate single-family from multi-family**; names like "Treeline Apartments" and "Indian Hills Multifamily" sit beside "Riddell Homestead North". `work` is also useful: Consolidated 479, Bldg/Prkg/Clring 216, **Extension 104** (re-approvals of old plans, not new projects), Utility Line 57, **Boat Docks 52**, ETJ Released 21.

**Size fields exist but are empty for recent cases.** `proposed_no_of_units` last populated for an application dated 2022-06-30; `proposed_bldg_sq_footage` last 2020-11-16; `gross_site_area_acres` only 7 of 1,015 recent cases. **`size_hint` cannot be built from this dataset for current cases.** Sentinel values exist (acres min -9999; impervious cover min -435,670).

**No valuation field** (as the addendum expected).

**Owner / applicant (24 months, 1,015 cases):** owner organization 573 (56%), applicant organization 882 (87%), either 956 (94%). Owner organization is often public (City of Austin, Austin ISD, Round Rock ISD, West Travis County PUA) or an LLC/LP. 49 cases have only an individual owner name and no organization: these get `owner_entity = NULL`, `owner_is_individual = true`. The person-name, phone and address fields are not stored.

**`permit_number` is NOT a building-permit key.** It holds the site plan's own case number (`SP-2026-0317D`, `SP-2022-0146C(XT).CC`). Linking to building permits must use address plus geo (the spec's M7.3 approach). Lat/lon fill is 81.5% overall and 99% (1,006 of 1,015) for the last 24 months; `related_cases` (17.8%) may chain site plans to each other.

**Data-quality flags:** `approved_in_last_30_days` says "Yes" for 17,182 rows (wrong, ignore); fiscal year 2027 appears; `tia_required` is almost empty.

## Questions for Donny before filter code
1. **Housing:** keep all `Housing` as passing (and accept some single-family subdivisions), or require the case name to look multi-family (apartment/multifamily/residences) or a unit count? Recent unit counts are missing, so a name heuristic is the only option.
2. **Public/Civic (101) and Industrial (27):** keep? Public/Civic is mostly schools and City projects, which the spec's "commercial, multi-family, industrial" list does not name.
3. **Exclude `Boat Dock`, `Horizontal Infrastructure` and work = `Extension`, `Utility Line`, `ETJ Released`, `Telecommunications Tower`, `Alcoholic Beverage Waiver`, `Late Hours Permit`?** My recommendation is yes (they are not building projects).
4. **Without a size field,** accept ranking by linked-permit valuation only, with no floor on unlinked cases?

---

