# Schema report: austin (`3syk-w9eu` on data.austintexas.gov)

Generated 2026-10-09 09:51 UTC. Dataset: **Issued Construction Permits**, 2,379,364 rows. Spec assumption to verify: no owner/applicant fields.

## Columns

| field | type | description |
|---|---|---|
| permittype | text | Raw values indicating type of permit in abbreviated format |
| permit_type_desc | text | Description of the Permit Type |
| permit_number | text | Permit number |
| permit_class_mapped | text | Indicates if the permit is intended for Residential or Commercial.  This mapping is derived from the PermitClass field ( |
| permit_class | text | Sub Type of the permit |
| work_class | text | Work type of the permit |
| condominium | text | Is this property a condominium? |
| permit_location | text | Property street address as a means to help identify project. |
| description | text | Detailed description of work permitted |
| tcad_id | text | TCAD_ID aligns with the Geographic ID field on the TravisCAD.org website when performing a property search. |
| legal_description | text | Legal Description of the property associated with the permit. |
| applieddate | calendar_date | Date on which the permit was applied.  This relates to the original Plan Review application submission where applicable. |
| issue_date | calendar_date | Date on which the permit was issued |
| day_issued | text | Day of the week the permit was issued |
| calendar_year_issued | number | Calendar Year corresponding to when the Permit was issued |
| fiscal_year_issued | number | Fiscal Year corresponding to when the permit was issued |
| issued_in_last_30_days | text | Yes/No value to indicate if the permit was issued in the last 30 days.  This field is evaluated using the last date that |
| issue_method | text | Permit issuance method.  "Permit Center" represents any permit which a permit center technician manually issued (e.g., w |
| status_current | text | Current status of permit |
| statusdate | calendar_date | Indicates the last time the status or ExpiresDate of a permit was updated in the AMANDA database. |
| expiresdate | calendar_date | Date on which the permit will/would have expire(d) |
| completed_date | calendar_date | Date on which the permit was completed |
| total_existing_bldg_sqft | number | Existing square footage of property before project |
| remodel_repair_sqft | number | Square footage of project affected by work being done. |
| total_new_add_sqft | number | Additional square footage gained from work being done. |
| total_valuation_remodel | number | Total dollar valuation for remodeling aspects of the job |
| total_job_valuation | number | Total dollar valuation for entire job for each building permit (e.g. will include Building, Electrical, Mechanical, and  |
| number_of_floors | number | How many floors property has |
| housing_units | number | Number of household units for a given building |
| building_valuation | number | Valuation of building where project is occurring |
| building_valuation_remodel | number | Valuation of remodel for project |
| electrical_valuation | number |  |
| electrical_valuation_remodel | number | Valuation of electrical remodel work |
| mechanical_valuation | number |  |
| mechanical_valuation_remodel | number | Valuation of mechanical remodel work |
| plumbing_valuation | number |  |
| plumbing_valuation_remodel | number | Valuation of plumbing remodel work |
| medgas_valuation | number |  |
| medgas_valuation_remodel | number | Valuation of medgas remodel work |
| original_address1 | text | Property address associated with the permit |
| original_city | text | City of the property associated with the permit |
| original_state | text | State of the property assoicated with the permit |
| original_zip | number | Zip code of the property associated with the permit |
| council_district | number | Council District associated with the permit property location |
| jurisdiction | text | Jurisdiction of permit property |
| link | url | Web link that show details of project inside AB+C |
| project_id | number | ID associated with the permit within the database.  Also referred to as the FolderRSN. |
| masterpermitnum | number | If the permit is listed as the child of another permit, this is the Project ID of that parent permit.  A building permit |
| latitude | number | Coordinate that specifies the north - south position of a point on the surface of the Earth |
| longitude | number | Coordinate that specifies the east - west position of a point on the surface of the Earth |
| location | location | The geographic coordinates for the project which are comprised of both latitude and longitude |
| contractor_trade | text | Indicates contractor trade. |
| contractor_company_name | text | Company name of the primary contractor associated with the permit. |
| contractor_full_name | text | Full name of the contractor |
| contractor_phone | text | Contractor phone number |
| contractor_address1 | text | Contractor street address line 1 |
| contractor_address2 | text | Contractor street address line 2 |
| contractor_city | text | Contractor city |
| contractor_zip | text | Contractor zip |
| applicant_full_name | text | Full name of the applicant |
| applicant_org | text | Organization the applicant is associated with. |
| applicant_phone | text | Applicant phone |
| applicant_address1 | text | Applicant address line 1 |
| applicant_address2 | text | Applicant address line 2 |
| applicant_city | text | Applicant city |
| applicantzip | text | Applicant zip code |
| certificate_of_occupancy | text | Yes or No field to specify if the Certificate of Occupancy was required for this permit. This information applies only t |
| total_lot_sq_ft | number | The total square footage attributed to the lot size. |

## Fill rate of key fields

| field | non-null | fill |
|---|---|---|
| permit_number | 2,379,364 | 100.0% |
| permit_location | 2,364,521 | 99.4% |
| original_address1 | 2,377,719 | 99.9% |
| latitude | 2,022,247 | 85.0% |
| longitude | 2,022,247 | 85.0% |
| issue_date | 2,379,364 | 100.0% |
| description | 2,379,280 | 100.0% |
| contractor_company_name | 1,191,164 | 50.1% |
| contractor_full_name | 1,242,019 | 52.2% |
| applicant_full_name | 197,266 | 8.3% |
| applicant_org | 226,668 | 9.5% |
| housing_units | 1,827,931 | 76.8% |
| total_new_add_sqft | 460,030 | 19.3% |
| project_id | 2,379,364 | 100.0% |
| masterpermitnum | 1,564,700 | 65.8% |

## Valuation distribution

| field | rows | >= $250k | min | max | avg |
|---|---|---|---|---|---|
| total_job_valuation | 2379364 | 85408 | 0 | 8100000000 | 337,308 |
| total_valuation_remodel | 2379364 | 7773 | 0 | 1525000000 | 356,375 |
| building_valuation | 2379364 | 5471 | 0 | 540000000 | 1,822,682 |

## Distinct values: `permittype` (5 shown, top 60 by count)

| value | rows |
|---|---|
| EP | 688721 |
| PP | 546670 |
| BP | 521026 |
| MP | 506330 |
| DS | 116617 |

## Distinct values: `permit_type_desc` (5 shown, top 60 by count)

| value | rows |
|---|---|
| Electrical Permit | 688721 |
| Plumbing Permit | 546670 |
| Building Permit | 521026 |
| Mechanical Permit | 506330 |
| Driveway / Sidewalks | 116617 |

## Distinct values: `permit_class_mapped` (2 shown, top 60 by count)

| value | rows |
|---|---|
| Residential | 1624692 |
| Commercial | 754672 |

## Distinct values: `permit_class` (60 shown, top 60 by count)

| value | rows |
|---|---|
| Residential | 652604 |
| R- 101 Single Family Houses | 451938 |
| C-1000 Commercial Remodel | 287142 |
| Commercial | 178125 |
| R- 435 Renovations/Remodel | 163210 |
| R- 434 Addition & Alterations | 135996 |
| Res. Driveway & Sidewalk | 88088 |
| (null) | 47944 |
| Sign Permit | 42156 |
| C- 329 Com Structures Other Than Bldg | 32769 |
| R- 329 Res Structures Other Than Bldg | 32348 |
| C-1001 Commercial Finish Out | 31260 |
| C- 105 Five or More Family Bldgs | 30706 |
| R- 103 Two Family Bldgs | 26227 |
| C- 324 Office, Bank & Professional Bldgs | 16012 |
| R- 645 Demolition One Family Homes | 13572 |
| R- 438 Residential Garage/Carport Addn | 13434 |
| C- 437 Addn, Alter, Convn-NonRes | 13398 |
| R- 102 Secondary Apartment | 12522 |
| C- 328 Commercial Other Nonresident Bldg | 12192 |
| C- 327 Stores & Customer Services | 11379 |
| Res. Driveway | 9202 |
| C- 101 Single Family Houses | 8331 |
| R- 330  Accessory Use to Primary | 8149 |
| Com. Driveway & Sidewalk | 6912 |
| C- 104 Three & Four Family Bldgs | 5963 |
| C- 326 Schools & Other Educational Bldgs | 5487 |
| R- 649 Demolition All Other Bldgs Res | 3934 |
| C- 649 Demolition All Other Bldgs Com | 3744 |
| C- 321 Pkg Garage Bldg & Open Deck | 3330 |
| R-2001 Relocation Residential | 2929 |
| C- 318 Amusement, Social & Rec Bldgs | 2588 |
| R- 439 Addition Mobile Home | 2510 |
| Res. Driveway, Sidewalk, Curb, Gutter | 2499 |
| Res. Driveway, Curb, Gutter | 2084 |
| C- 320 Industrial Bldgs | 1604 |
| C- 322 Service Station & Repair Garage | 1484 |
| C- 319 Churches and Othr Religious Bldgs | 1273 |
| C- 213 Hotels, Motels, & Tourist Cabins | 1270 |
| Com. Driveway,Sidewalk,Curb,Gutter | 1089 |
| C- 103 Two Family Bldgs | 971 |
| C-1002 Commercial Remodel & Finish Out | 895 |
| C- 106 Mixed Use | 866 |
| C- 325 Public Works & Utilities Bldgs | 849 |
| C - Medical Gas | 840 |
| Com. Sidewalk | 838 |
| Res. Sidewalk | 821 |
| C- 323 Hospital & Institutional Bldgs | 729 |
| Com. Driveway | 693 |
| R- 437 Residential Boat Dock | 670 |
| C- 214 Other Nonhousekeeping Shelter | 610 |
| R- 436 Addn to increase housing units | 578 |
| R- 646 Demolition Two Family Bldgs | 536 |
| Com. Sidewalk, Curb, Gutter | 502 |
| R- 438 Residential Retaining Wall | 431 |
| C-2000 Relocation Commercial | 283 |
| R- 328 Resident Other Nonresident Bldg | 183 |
| C- 648 Demolition 5 or More Family Bldgs | 132 |
| Com. Driveway, Curb, Gutter | 114 |
| Res. Curb, Gutter | 112 |

## Distinct values: `work_class` (33 shown, top 60 by count)

| value | rows |
|---|---|
| Remodel | 874233 |
| New | 834488 |
| Repair | 179685 |
| Change Out | 118045 |
| Addition | 81727 |
| Addition and Remodel | 69652 |
| Irrigation | 47990 |
| (null) | 42354 |
| Demolition | 21957 |
| Upgrade | 21560 |
| Auxiliary Power | 20013 |
| Wall | 17308 |
| Homebuilder Loop | 14266 |
| Special Inspections Program | 5444 |
| Interior Demo Non-Structural | 5290 |
| Freestanding | 4469 |
| Shell | 4375 |
| Modification | 3874 |
| Relocation | 3217 |
| Fireline | 3139 |
| Life Safety | 2499 |
| Temporary  Loop | 1141 |
| Auxiliary Water | 890 |
| Cut Over/Tank Abandonment | 620 |
| Projecting | 331 |
| Billboard | 197 |
| Demo | 182 |
| Awning | 153 |
| Roof | 64 |
| Plumbing Utility Connection | 64 |
| Plumbing Service Line | 57 |
| Grease Interceptor (GI) replacement | 46 |
| Remodel Mobile Home | 34 |

## Distinct values: `status_current` (25 shown, top 60 by count)

| value | rows |
|---|---|
| Final | 2008891 |
| Expired | 169565 |
| VOID | 153334 |
| Active | 28099 |
| Withdrawn | 17785 |
| Cancelled | 675 |
| Pending | 233 |
| Cancelled - Contractor Required | 131 |
| Closed | 129 |
| Aborted | 120 |
| Inactive Pending Revision | 93 |
| On Hold | 78 |
| Pending Permit | 58 |
| Re Review | 55 |
| Denied but Closed | 43 |
| Suspended | 26 |
| (null) | 14 |
| Expired - License | 14 |
| Cancelled - New Permit Required | 9 |
| New Permit Required | 3 |
| Inactive Contractor | 3 |
| Revoked | 2 |
| Application Incomplete | 2 |
| Rejected | 1 |
| Awaiting Upload | 1 |

## Distinct values: `issue_method` (2 shown, top 60 by count)

| value | rows |
|---|---|
| Permit Center | 2341111 |
| Online | 38253 |

## Distinct values: `jurisdiction` (38 shown, top 60 by count)

| value | rows |
|---|---|
| AUSTIN FULL PURPOSE | 2117012 |
| AUSTIN 2 MILE ETJ | 127533 |
| AUSTIN LTD | 68454 |
| (null) | 25719 |
| LAKEWAY FULL PURPOSE | 6825 |
| AUSTIN 5 MILE ETJ | 5923 |
| WEST LAKE HILLS FULL PURPOSE | 5111 |
| BEE CAVE FULL PURPOSE | 4822 |
| BEE CAVE ETJ | 3564 |
| ROUND ROCK ETJ | 2662 |
| ROLLINGWOOD FULL PURPOSE | 1995 |
| SB 2038 ETJ RELEASE | 1715 |
| LAKEWAY ETJ | 1559 |
| OTHER | 1276 |
| THE HILLS FULL PURPOSE | 1252 |
| SUNSET VALLEY FULL PURPOSE | 1126 |
| PFLUGERVILLE FULL PURPOSE | 1117 |
| WEST LAKE HILLS ETJ | 867 |
| PFLUGERVILLE ETJ | 592 |
| SUNSET VALLEY ETJ | 61 |
| BASTROP ETJ | 46 |
| CREEDMOOR ETJ | 36 |
| LAGO VISTA ETJ | 23 |
| CEDAR PARK FULL PURPOSE | 16 |
| CREEDMOOR FULL PURPOSE | 12 |
| MANOR FULL PURPOSE | 10 |
| MUSTANG RIDGE FULL PURPOSE | 9 |
| SAN LEANNA FULL PURPOSE | 5 |
| MUSTANG RIDGE ETJ | 4 |
| VOLENTE FULL PURPOSE | 3 |
| POINT VENTURE FULL PURPOSE | 3 |
| MANOR ETJ | 3 |
| ROUND ROCK FULL PURPOSE | 2 |
| CEDAR PARK ETJ | 2 |
| BRIARCLIFF ETJ | 2 |
| BRIARCLIFF FULL PURPOSE | 1 |
| BEAR CREEK FULL PURPOSE | 1 |
| LEANDER FULL PURPOSE | 1 |

## Distinct values: `contractor_trade` (5 shown, top 60 by count)

| value | rows |
|---|---|
| (null) | 948742 |
| General Contractor | 564757 |
| Electrical Contractor | 367069 |
| Plumbing Contractor | 269769 |
| Mechanical Contractor | 229027 |

## Sample (20 most recent issued)

| permit_number | permit_type_desc | permit_class | work_class | issue_date | total_job_valuation | permit_location | contractor_company_name | applicant_org | description |
|---|---|---|---|---|---|---|---|---|---|
| 2026-131796 BP | Building Permit | R- 434 Addition & Alterations | Addition and Remodel | 2026-10-07T00:00:00.000 | 1 | 1902 JUSTIN LN UNIT B | Nuhorizon Remodeling | Nuhorizon Remodeling | Convert the covered patio and Porch on Unit B to conditioned space. 31 |
| 2026-126040 PP | Plumbing Permit | Residential | Repair | 2026-10-07T00:00:00.000 |  | 200 W WONSLEY DR | HC Plumbing |  | Replace sewer lines under the house and yard line for both units |
| 2026-130814 PP | Plumbing Permit | Residential | Change Out | 2026-10-07T00:00:00.000 |  | 14228 MARATHON RD | Proven Plumbing LLC |  | Replacement of an existing water heater |
| 2026-129672 EP | Electrical Permit | Sign Permit | Wall | 2026-10-07T00:00:00.000 |  | 8648 RESEARCH BLVD SVRD SB |  |  | Tim Hortons T1 Maple Leaf Front Elevation |
| 2026-123042 BP | Building Permit | C- 437 Addn, Alter, Convn-NonRes | Addition | 2026-10-07T00:00:00.000 | 1 | 520 E 6TH ST | Zapalac/Reed (MAIN) Construction Company | Zapalac/Reed (MAIN) Construction Company | Addition of a New Awning to Shell Building  2024 149559 DA - Concurren |
| 2026-084960 PP | Plumbing Permit | R- 435 Renovations/Remodel | Repair | 2026-10-07T00:00:00.000 |  | 3801 MENCHACA RD UNIT 30 | Talos Plumbing LLC dba Neighborhood Plumbing and Drain |  | Express: 2nd floor renovation to include plumbing for replacement of t |
| 2026-131168 PP | Plumbing Permit | C-1000 Commercial Remodel | Remodel | 2026-10-07T00:00:00.000 |  | 6433 CHAMPION GRANDVIEW WAY BLDG 1 | STELLAR PLUMBING INC |  | EPLAN - Remodel office and break area - 4th Floor |
| 2026-114871 EP | Electrical Permit | Sign Permit | Wall | 2026-10-07T00:00:00.000 |  | 4616 TRIANGLE AVE BLDG 4 UNIT 405 |  |  | FSG to install sign package - Channel letters  SALON LOFT |
| 2026-107738 MP | Mechanical Permit | C-1000 Commercial Remodel | Remodel | 2026-10-07T00:00:00.000 |  | 861 E BRAKER LN | Blue Star Beverage Supply LLC |  | Remove and replace existing tea and fountain equipment and chiller. Ex |
| 2026-108431 BP | Building Permit | C-1000 Commercial Remodel | Remodel | 2026-10-07T00:00:00.000 |  | 218 E 6TH ST | Zapalac Reed Construction (Main GC account) | Zapalac Reed Construction (Main GC account) | Interior structural repair no change in use height or area. No exterio |
| 2026-125195 EP | Electrical Permit | R- 101 Single Family Houses | New | 2026-10-07T00:00:00.000 |  | 12308 DILLON FALLS DR | Landmark Electric |  | Sheldon S403 B Left New - 2 Story SFR w/ 3 bedrooms 2.5 bathrooms atta |
| 2026-131165 PP | Plumbing Permit | C-1000 Commercial Remodel | Remodel | 2026-10-07T00:00:00.000 |  | 6433 CHAMPION GRANDVIEW WAY BLDG 1 | STELLAR PLUMBING INC |  | EPLAN - Remodel for Labs servery and IT -1st Floor. |
| 2026-083121 PP | Plumbing Permit | R- 103 Two Family Bldgs | New | 2026-10-07T00:00:00.000 |  | 909 E 44TH ST UNIT B | ETC Plumbing Inc. |  | Unit B New 2-Story duplex unit with habitable attic 3 Bed/3.5 Bath att |
| 2026-130094 PP | Plumbing Permit | Residential | Change Out | 2026-10-07T00:00:00.000 |  | 7510 ST AMANT PL BLDG A | Your Juan and Only Plumber |  | Replacement of an existing water heater We just brought the existing w |
| 2026-131629 BP | Building Permit | R- 329 Res Structures Other Than Bldg | New | 2026-10-07T00:00:00.000 | 0 | 12100 FENNEC WAY | Austin Pool Builders | Austin Pool Builders | Installation of a 134x9-0 in-ground concrete pool |
| 2022-058460 BP | Building Permit | R- 434 Addition & Alterations | Addition and Remodel | 2026-10-07T00:00:00.000 | 1 | 1119 W 9TH ST | Chris Devidal | Chris Devidal | Addition/remodel rolling in expired 2003-019681 PP for inspection new  |
| 2026-129684 EP | Electrical Permit | Sign Permit | Wall | 2026-10-07T00:00:00.000 |  | 8648 RESEARCH BLVD SVRD SB |  |  | Tim Hortons North Elevation Channel Letters |
| 2026-131345 EP | Electrical Permit | Residential | Repair | 2026-10-07T00:00:00.000 |  | 1908 BISSEL LN | Molitor Electric, Inc. |  | Emergency Repair to Meter. Replaced meter and mast |
| 2026-132283 BP | Building Permit | C-1000 Commercial Remodel | Remodel | 2026-10-07T00:00:00.000 |  | 6433 CHAMPION GRANDVIEW WAY BLDG 2 | Novo Construction **Main** | Novo Construction **Main** | ePlan Review: Remodel Labs and Break Area - 3rd Floor for Building 2 |
| 2026-108150 BP | Building Permit | R- 645 Demolition One Family Homes | Demolition | 2026-10-07T00:00:00.000 | 0 | 4711 PHILCO DR | Moore-Tate Projects and Design, LLC | Moore-Tate Projects and Design, LLC | Total Demo of a SFR 1612 sq ft built 1959.  ***The building shall not  |

## Open questions for review

- Which valuation field is authoritative for the >= $250k rule?
- Which field(s) separate new construction vs. addition/alteration vs. trade-only?
- Which field gives occupancy/use (commercial / multi-family / industrial / single-family)?
- Applicant/owner fields exist; spec says store no personal data. Confirm treatment (business names only?).
