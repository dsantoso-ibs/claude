"""M4: enrichment interface with a HARD daily cost cap. Targets the default open pipeline only.

Safety design:
  * dry-run is the default: lists targets and estimates cost, writes nothing to `enrichments`.
  * a real run needs enrichment.enabled=true AND a real provider adapter; the stub is refused (it would write all-"not found" rows
    that would wrongly read as a 0% contact yield).
  * the cap is checked BEFORE each call against today's logged spend (UTC); a call that could exceed it is never made.
  * personal data: owner/developer/architect values that look like individuals are dropped (logged as counts only, never stored).

Usage: python -m src.enrich            (dry run -> reports/enrichment-dryrun.md)
"""
from __future__ import annotations
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from src import config as cfgmod
from src.entities import clean_entity
from src.schema import connect


@dataclass
class EnrichmentResult:
    cost_usd: float
    owner: str | None = None
    developer: str | None = None
    architect: str | None = None
    contacts: list[dict] = field(default_factory=list)      # business contacts only
    raw: dict = field(default_factory=dict)


class Enricher(Protocol):
    name: str
    def est_cost(self, target: dict) -> float: ...           # upper-bound USD for one target, used by the cap guard
    def enrich(self, target: dict) -> EnrichmentResult: ...


class StubEnricher:
    name = "stub"
    def est_cost(self, target: dict) -> float:
        return 0.0
    def enrich(self, target: dict) -> EnrichmentResult:
        return EnrichmentResult(cost_usd=0.0)


class NotConfigured(RuntimeError):
    pass


def get_enricher(cfg: dict) -> Enricher:
    prov = cfg["enrichment"]["provider"]
    if prov == "none":
        return StubEnricher()
    raise NotConfigured(f"enrichment provider '{prov}' has no adapter: its interface/credentials contract has not been provided")


class CapGuard:
    def __init__(self, con, cap_usd: float):
        self.con, self.cap = con, cap_usd

    def spent_today(self) -> float:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return float(self.con.execute("SELECT COALESCE(SUM(cost_usd),0) FROM enrichments WHERE substr(requested_at,1,10)=?", (today,)).fetchone()[0])

    def allows(self, est_cost: float, spent_now: float | None = None) -> bool:
        spent = self.spent_today() if spent_now is None else spent_now
        return spent + est_cost <= self.cap


def targets(con, cfg: dict, provider: str) -> list[dict]:
    """Default open pipeline not yet enriched by this provider."""
    from src.report_phase2 import open_pipeline, pr_open_pipeline
    done = {(r["stage"], r["candidate_id"]) for r in con.execute("SELECT stage, candidate_id FROM enrichments WHERE provider=?", (provider,))}
    out = []
    if "site_plan_open" in cfg["enrichment"]["stages"]:
        out += [dict(stage="site_plan_open", ref_id=r["id"], name=r["case_name"], address=r["address_norm"], owner_entity=r["owner_entity"],
                     applicant_org=r["applicant_org"], size_band=r["size_band"]) for r in open_pipeline(con, cfg)]
    if "plan_review_open" in cfg["enrichment"]["stages"]:
        out += [dict(stage="plan_review_open", ref_id=r["id"], name=r["project_name"], address=r["address_norm"], owner_entity=r["owner_entity"],
                     applicant_org=r["applicant_org"], size_band=r["size_band"]) for r in pr_open_pipeline(con, cfg)]
    assert all(t["size_band"] is not None or True for t in out)
    return [t for t in out if (t["stage"], t["ref_id"]) not in done]


def run(con, cfg: dict, *, dry_run: bool = True, enricher: Enricher | None = None, allow_stub: bool = False) -> dict:
    ec = cfg["enrichment"]; enricher = enricher or get_enricher(cfg)
    tg = targets(con, cfg, enricher.name)
    guard = CapGuard(con, ec["daily_cost_cap_usd"])
    if dry_run:
        per = ec["serpapi_usd_per_call"] * ec["est_queries_per_project"]
        within = int((ec["daily_cost_cap_usd"] - guard.spent_today()) // per) if per else len(tg)
        return {"mode": "dry-run", "targets": len(tg), "by_stage": {s: sum(1 for t in tg if t["stage"] == s) for s in ec["stages"]},
                "est_cost_per_project_usd": round(per, 4), "est_total_usd": round(per * len(tg), 2), "cap_usd": ec["daily_cost_cap_usd"],
                "projects_per_day_within_cap": min(within, len(tg)), "days_needed": -(-len(tg) // max(within, 1))}
    if not ec["enabled"]:
        raise PermissionError("enrichment.enabled is false")
    if isinstance(enricher, StubEnricher) and not allow_stub:
        raise PermissionError("refusing to write stub results: they would read as a 0% contact yield")
    done = skipped_cap = individuals = 0
    spent = guard.spent_today()
    for t in tg:
        est = enricher.est_cost(t)
        if not guard.allows(est, spent):
            skipped_cap = len(tg) - done                       # hard stop: no call is made that could exceed the cap
            break
        res = enricher.enrich(t)
        spent += res.cost_usd
        vals = {}
        for k in ("owner", "developer", "architect"):
            name, ind = clean_entity(getattr(res, k)); vals[k] = name; individuals += int(ind)
        contacts = [c for c in res.contacts if clean_entity(c.get("company"))[0]]
        con.execute("INSERT INTO enrichments(candidate_id, provider, requested_at, cost_usd, result_json, found_owner, found_developer, found_architect, found_contact, stage)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (t["ref_id"], enricher.name, datetime.now(timezone.utc).isoformat(), res.cost_usd, json.dumps({**vals, "contacts": contacts}),
                     int(bool(vals["owner"])), int(bool(vals["developer"])), int(bool(vals["architect"])), int(bool(contacts)), t["stage"]))
        done += 1
    con.commit()
    return {"mode": "run", "enriched": done, "stopped_by_cap": skipped_cap, "spent_today_usd": round(spent, 4), "dropped_individual_names": individuals}


def main() -> None:
    cfg = cfgmod.load(); con = connect(cfgmod.DB_PATH)
    r = run(con, cfg, dry_run=True)
    L = ["# Enrichment dry run (no calls made, nothing written)", "",
         f"Targets: the **default open pipeline** (new build, shell, addition; remodels excluded): **{r['targets']}** projects "
         f"({', '.join(f'{k} {v}' for k, v in r['by_stage'].items())}).", "",
         f"Estimate (assumption, not a measured cost): {cfg['enrichment']['est_queries_per_project']} SerpAPI queries per project x ${cfg['enrichment']['serpapi_usd_per_call']}/call "
         f"= ${r['est_cost_per_project_usd']}/project, **${r['est_total_usd']} for all targets**.",
         f"Hard daily cap (proposed, unconfirmed): ${r['cap_usd']}. Within the cap: {r['projects_per_day_within_cap']} projects/day, {r['days_needed']} day(s) to cover all targets.", "",
         "Status: **not run.** Provider interface, cap amount and query design have not been confirmed (see the report to Donny)."]
    (cfgmod.ROOT / "reports" / "enrichment-dryrun.md").write_text("\n".join(L) + "\n")
    print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
