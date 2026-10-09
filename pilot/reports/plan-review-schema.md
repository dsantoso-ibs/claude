# M7.0 reviewer summary: Plan Review Cases (`n8ck-xkda`)
*Hand-written from the auto-profile below plus ad-hoc queries run 2026-10-09. Schema discovery only; no ingest planned yet.*

**Plan Review Cases looks like a better stage-3 source than the spec assumed.** It is the building-permit *application* record: 161,848 rows, `applied_date` 2014-01-02 to **2026-10-08** (current), `issued_date` filled on 151,674. Unlike Site Plan Cases it carries **valuation** (`total_job_valuation`, `building_valuation`), `number_of_units`, `number_of_floors`, footage, `work_class`, `sub_type` (the same `C-`/`R-` use class as issued permits), `status_current` and `project_name`.

- Applications with `total_job_valuation >= $250k`: **3,773 all-time; 93 applied in 2026 (about 10 a month); 43 of those not yet issued** (the open pipeline, with valuation, weeks before the contractor-chosen permit stage). Examples seen: 11600 Menchaca Rd ($13M, new, awaiting upload), 8515 FM 969 Rd ($11.75M), 8016 Burleson Rd Bldg 1 ($4.7M, in review), 4912 E Ben White Blvd ($2.5M, owner AMERCO Real Estate Company of Texas).
- **Owner organization is filled on only 1,106 of 3,773 (29%)** of the >= $250k applications; so the contact story is weaker than in Site Plan Cases (56% owner, 87% applicant).
- Link key: `permit_number` here is `2026-131555 PR` style; the later issued permit is `2026-xxxxxx BP`, so linking needs address/geo (`propx`/`propy`, `location`, `project_name` holds the address). `folder_description` and `project_name` may help fuzzy matching.
- Early stage: `applied_date` to `issued_date` gives a lead-time measure **without needing site plans at all**, for the same projects already in `candidates`.

## Suggested decision for Donny
Treat Plan Review Cases as a candidate M7 source alongside Site Plan Cases: Site Plan = earliest (before design is final, owner named, no money field), Plan Review = later but has valuation and units and likely 3 to 8 weeks of lead on the issued permit. Measure both lead times.

---

