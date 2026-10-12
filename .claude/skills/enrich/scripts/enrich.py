#!/usr/bin/env python3
"""enrich.py - waterfall contact enrichment (email + phone) with verification. Python 3.8+, stdlib only.

Source-agnostic: it takes plain records (CSV / JSON / JSONL / stdin) and returns the same records
plus enrichment fields. Claude (or any script) fetches records from Salesforce, lemlist, etc.,
pipes them through here, and writes the result back. Every record's own fields (id, ...) pass through.

Commands
  check     show which providers have keys (never prints keys)
  run       enrich records: find email and/or phone through the provider waterfall
  verify    validate emails already in the records (no finding)

Keys: environment variables, else ./.env, else ~/.config/enrich/.env
  PROSPEO_API_KEY  FINDYMAIL_API_KEY  MILLIONVERIFIER_API_KEY
"""
import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "enrich-skill/1.0 (python-urllib)"
POS_TTL = 90 * 86400   # a found contact is reused for 90 days (matches Prospeo's free re-enrich window)
NEG_TTL = 30 * 86400   # a miss is remembered for 30 days so reruns don't pay again

DEFAULT_CONFIG = {
    "email": ["prospeo", "findymail"],
    "phone": ["prospeo", "findymail"],
    "verifier": "millionverifier",
}

# ---------------------------------------------------------------------------- keys / http


def load_env():
    for p in (Path(".env"), Path("~/.config/enrich/.env").expanduser()):
        try:
            for line in p.read_text().splitlines():
                m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
                if m and m.group(1) not in os.environ:
                    os.environ[m.group(1)] = m.group(2).strip("'\"")
        except OSError:
            pass


class ProviderError(Exception):
    """Transient or per-request problem: skip this provider for this record."""


class FatalProviderError(ProviderError):
    """Bad key / no credits: stop using this provider for the rest of the run."""


def http(method, url, headers=None, body=None, timeout=45, retries=3):
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": UA, "Accept": "application/json"}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, parse(r.read())
        except urllib.error.HTTPError as e:
            payload = parse(e.read())
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(min(2 ** attempt * 2, 20))
                continue
            return e.code, payload
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise ProviderError("network error: %s" % getattr(e, "reason", e))


def parse(raw):
    try:
        return json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        return {}

# ---------------------------------------------------------------------------- person model


def domain_of(s):
    s = (s or "").strip().lower()
    if not s:
        return ""
    s = re.sub(r"^[a-z]+://", "", s).split("/")[0].split("?")[0]
    return re.sub(r"^www\.", "", s) if "." in s else ""


ALIASES = {
    "first_name": ["first_name", "firstname", "first name", "given_name", "vorname"],
    "last_name": ["last_name", "lastname", "last name", "surname", "family_name", "nachname"],
    "full_name": ["full_name", "fullname", "full name", "name", "contact_name"],
    "company": ["company", "company_name", "account", "account_name", "organization", "organisation", "firma"],
    "domain": ["domain", "company_domain", "website", "company_website", "url", "web", "homepage"],
    "linkedin": ["linkedin", "linkedin_url", "linkedin url", "linkedinurl", "li_url", "profile_url"],
    "email": ["email", "e-mail", "email_address", "work_email", "mail"],
    "phone": ["phone", "mobile", "phone_number", "telephone", "tel"],
}


def normalize(rec):
    low = {re.sub(r"\s+", " ", str(k)).strip().lower(): v for k, v in rec.items()}

    def pick(field):
        for a in ALIASES[field]:
            v = low.get(a)
            if v not in (None, ""):
                return str(v).strip()
        return ""

    p = {f: pick(f) for f in ALIASES}
    if not p["full_name"]:
        p["full_name"] = (p["first_name"] + " " + p["last_name"]).strip()
    if p["full_name"] and not (p["first_name"] and p["last_name"]):
        parts = p["full_name"].split()
        if len(parts) >= 2:
            p["first_name"], p["last_name"] = p["first_name"] or parts[0], p["last_name"] or parts[-1]
    p["domain"] = domain_of(p["domain"])
    return p


def can_match(p):
    """Minimum identity a finder needs: LinkedIn, or a name plus a company/domain."""
    return bool(p["linkedin"] or (p["full_name"] and (p["domain"] or p["company"])))


def person_key(p):
    base = p["linkedin"].lower().rstrip("/") or "|".join(
        [p["full_name"].lower(), p["domain"] or p["company"].lower()])
    return hashlib.sha1(base.encode()).hexdigest()

# ---------------------------------------------------------------------------- providers
# Each finder returns (value, meta) on a hit, None on a miss, raises ProviderError otherwise.
# `credits` is what the vendor documents it charges on a hit (used for the cost report and caps).


class Provider:
    name = ""
    env = ""
    kinds = ()
    credits = {}

    def __init__(self):
        self.key = os.environ.get(self.env, "")

    @property
    def ready(self):
        return bool(self.key)

    def _fatal(self, status, payload):
        if status in (401, 403):
            raise FatalProviderError("%s: invalid API key" % self.name)
        if status in (402, 423):
            raise FatalProviderError("%s: out of credits / subscription paused" % self.name)


class Prospeo(Provider):
    """https://prospeo.io/api-docs/enrich-person  - 1 credit/email, 10/mobile, free on no match."""
    name, env, kinds = "prospeo", "PROSPEO_API_KEY", ("email", "phone")
    credits = {"email": 1, "phone": 10}

    def _call(self, p, mobile):
        data = {}
        if p["linkedin"]:
            data["linkedin_url"] = p["linkedin"]
        else:
            if not (p["first_name"] and p["last_name"]):
                return None
            data.update(first_name=p["first_name"], last_name=p["last_name"])
            if p["domain"]:
                data["company_website"] = p["domain"]
            elif p["company"]:
                data["company_name"] = p["company"]
            else:
                return None
        body = {"only_verified_email": not mobile, "data": data}
        if mobile:
            body["only_verified_mobile"] = True
        st, r = http("POST", "https://api.prospeo.io/enrich-person",
                     {"X-KEY": self.key}, body)
        code = r.get("error_code") if isinstance(r, dict) else None
        if code == "INSUFFICIENT_CREDITS":
            raise FatalProviderError("prospeo: out of credits")
        if code == "INVALID_API_KEY":
            raise FatalProviderError("prospeo: invalid API key")
        self._fatal(st, r)
        if code in ("NO_MATCH", "INVALID_DATAPOINTS"):
            return None
        if st == 429:
            raise ProviderError("prospeo: rate limited")
        if st != 200 or r.get("error"):
            raise ProviderError("prospeo: HTTP %s %s" % (st, code or ""))
        return r.get("person") or {}

    def find_email(self, p):
        person = self._call(p, mobile=False)
        e = (person or {}).get("email") or {}
        v = e.get("email") if e.get("revealed", True) else None
        if v and "*" not in v and (e.get("status") or "").upper() == "VERIFIED":
            return v, {"verified_by_provider": True}
        return None

    def find_phone(self, p):
        person = self._call(p, mobile=True)
        m = (person or {}).get("mobile") or {}
        v = m.get("mobile_international") or m.get("mobile")
        if v and m.get("revealed") and "*" not in v:
            return v, {"line_type": "mobile"}
        return None


class Findymail(Provider):
    """https://app.findymail.com/docs/ - 1 credit/verified email, 10/phone. Phone: US only, no EU persons."""
    name, env, kinds = "findymail", "FINDYMAIL_API_KEY", ("email", "phone")
    credits = {"email": 1, "phone": 10}
    base = "https://app.findymail.com"

    def _post(self, path, body):
        st, r = http("POST", self.base + path, {"Authorization": "Bearer " + self.key}, body)
        self._fatal(st, r)
        if st == 429:
            raise ProviderError("findymail: rate limited")
        if st == 404 or st == 422:
            return {}
        if st != 200:
            raise ProviderError("findymail: HTTP %s" % st)
        return r

    def find_email(self, p):
        if p["linkedin"]:
            r = self._post("/api/search/business-profile", {"linkedin_url": p["linkedin"]})
        elif p["domain"] and p["full_name"]:
            r = self._post("/api/search/name", {"name": p["full_name"], "domain": p["domain"]})
        else:
            return None
        v = ((r or {}).get("contact") or {}).get("email")
        return (v, {"verified_by_provider": True}) if v else None

    def find_phone(self, p):
        if not p["linkedin"]:
            return None
        r = self._post("/api/search/phone", {"linkedin_url": p["linkedin"]})
        v = (r or {}).get("phone")
        return (v, {"line_type": (r.get("line_type") or "").lower()}) if v else None


class MillionVerifier(Provider):
    """https://developer.millionverifier.com/ - ~1 credit/email. Result mapped to valid/risky/unknown/invalid."""
    name, env, kinds = "millionverifier", "MILLIONVERIFIER_API_KEY", ("verify",)
    credits = {"verify": 1}
    MAP = {"ok": "valid", "catch_all": "risky", "unknown": "unknown",
           "invalid": "invalid", "disposable": "invalid", "error": "unknown"}

    def verify(self, email):
        q = urllib.parse.urlencode({"api": self.key, "email": email, "timeout": 20})
        st, r = http("GET", "https://api.millionverifier.com/api/v3/?" + q, timeout=40)
        if st in (401, 403) or (isinstance(r, dict) and r.get("error") in ("apikey_not_found", "invalid_api_key")):
            raise FatalProviderError("millionverifier: invalid API key")
        if isinstance(r, dict) and r.get("error") and "credit" in str(r["error"]).lower():
            raise FatalProviderError("millionverifier: out of credits")
        if st != 200 or not isinstance(r, dict):
            raise ProviderError("millionverifier: HTTP %s" % st)
        return self.MAP.get(str(r.get("result", "")).lower(), "unknown")


REGISTRY = {c.name: c for c in (Prospeo, Findymail, MillionVerifier)}

# ---------------------------------------------------------------------------- cache


class Cache:
    def __init__(self, path):
        self.lock = threading.Lock()
        if path == ":none:":
            self.db = None
            return
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(Path(path).expanduser()), check_same_thread=False)
        self.db.execute("create table if not exists c(k text primary key, v text, t real)")

    def get(self, k):
        if not self.db:
            return None
        with self.lock:
            row = self.db.execute("select v,t from c where k=?", (k,)).fetchone()
        if not row:
            return None
        v = json.loads(row[0])
        if time.time() - row[1] > (POS_TTL if v.get("hit") else NEG_TTL):
            return None
        return v

    def put(self, k, v):
        if not self.db:
            return
        with self.lock:
            self.db.execute("insert or replace into c values(?,?,?)", (k, json.dumps(v), time.time()))
            self.db.commit()

# ---------------------------------------------------------------------------- waterfall


class Engine:
    def __init__(self, config, cache, max_credits=None, mock=None):
        self.cfg = config
        self.cache = cache
        self.max_credits = max_credits
        self.lock = threading.Lock()
        self.spent = {}
        self.dead = {}          # provider -> reason (fatal error this run)
        self.skipped_nokey = set()
        self.providers = {}
        for name in set(config["email"] + config["phone"] + [config["verifier"]]):
            if mock and name in mock:
                self.providers[name] = mock[name]
                continue
            if name not in REGISTRY:
                raise SystemExit("unknown provider in config: %s (known: %s)" % (name, ", ".join(REGISTRY)))
            self.providers[name] = REGISTRY[name]()

    # -- bookkeeping
    def total(self):
        return sum(self.spent.values())

    def charge(self, name, kind):
        with self.lock:
            self.spent[name] = self.spent.get(name, 0) + self.providers[name].credits.get(kind, 0)

    def usable(self, name, kind):
        pr = self.providers[name]
        if name in self.dead or kind not in pr.kinds:
            return False
        if not pr.ready:
            self.skipped_nokey.add(name)
            return False
        cost = pr.credits.get(kind, 0)
        return not (self.max_credits is not None and self.total() + cost > self.max_credits)

    def _try(self, name, kind, fn, trace):
        try:
            return fn()
        except FatalProviderError as e:
            self.dead[name] = str(e)
            trace.append("%s:%s" % (name, "disabled"))
        except ProviderError as e:
            trace.append("%s:error(%s)" % (name, str(e)[:60]))
        return "err"

    # -- verification
    def verify(self, email, trace):
        name = self.cfg["verifier"]
        if not self.usable(name, "verify"):
            return "unverified"
        k = "v|%s|%s" % (name, email.lower())
        c = self.cache.get(k)
        if c:
            return c["status"]
        r = self._try(name, "verify", lambda: self.providers[name].verify(email), trace)
        if r == "err":
            return "unverified"
        self.charge(name, "verify")
        self.cache.put(k, {"hit": True, "status": r})
        return r

    # -- finding
    def find(self, kind, p, trace, reverify=False):
        """Return (value, source, status, extra) or None."""
        fallback = None  # best non-valid email seen, used only if nothing better turns up
        for name in self.cfg[kind]:
            if not self.usable(name, kind):
                trace.append("%s:skipped" % name)
                continue
            k = "f|%s|%s|%s" % (name, kind, person_key(p))
            c = self.cache.get(k)
            if c is not None:
                res = (c["value"], c["meta"]) if c.get("hit") else None
                trace.append("%s:%s(cached)" % (name, "hit" if res else "miss"))
            else:
                fn = getattr(self.providers[name], "find_" + kind)
                res = self._try(name, kind, lambda: fn(p), trace)
                if res == "err":
                    continue
                self.cache.put(k, {"hit": bool(res), "value": res[0] if res else None, "meta": res[1] if res else {}})
                if res:
                    self.charge(name, kind)
                trace.append("%s:%s" % (name, "hit" if res else "miss"))
            if not res:
                continue
            value, meta = res
            if kind == "phone":
                return value, name, "found", meta
            status = "valid" if meta.get("verified_by_provider") and not reverify else self.verify(value, trace)
            if status in ("valid", "unverified"):
                return value, name, "valid" if status == "valid" else "unverified", meta
            if status in ("risky", "unknown") and not fallback:
                fallback = (value, name, status, meta)
            # invalid -> keep falling through the waterfall
        return fallback

    def enrich(self, rec, want_email=True, want_phone=False, reverify=False):
        p = normalize(rec)
        out = dict(rec)
        trace = []
        out.update(email_found="", email_status="", email_source="", phone_found="", phone_source="",
                   phone_type="")
        if not can_match(p):
            out["enrich_trace"] = "skipped: need LinkedIn URL, or full name + company/domain"
            return out
        if want_email:
            if p["email"]:
                out.update(email_found=p["email"], email_source="input")
                out["email_status"] = self.verify(p["email"], trace)
                if out["email_status"] in ("invalid",):
                    r = self.find("email", p, trace, reverify)
                    if r:
                        out.update(email_found=r[0], email_source=r[1], email_status=r[2])
            else:
                r = self.find("email", p, trace, reverify)
                if r:
                    out.update(email_found=r[0], email_source=r[1], email_status=r[2])
                else:
                    tried = any(not t.endswith(":skipped") for t in trace)
                    out["email_status"] = "not_found" if tried else "not_checked"
        if want_phone:
            r = self.find("phone", p, trace)
            if r:
                out.update(phone_found=r[0], phone_source=r[1], phone_type=r[3].get("line_type", ""))
        out["enrich_trace"] = " > ".join(trace)
        return out

# ---------------------------------------------------------------------------- io


def read_records(path):
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8-sig")
    s = text.lstrip()
    if s.startswith("["):
        return json.loads(s)
    if s.startswith("{"):
        return [json.loads(l) for l in s.splitlines() if l.strip()]
    return list(csv.DictReader(text.splitlines()))


def write_records(rows, path):
    if path in (None, "-"):
        json.dump(rows, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return
    p = Path(path)
    if p.suffix == ".csv":
        cols = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, cols)
            w.writeheader()
            w.writerows(rows)
    elif p.suffix == ".jsonl":
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    else:
        p.write_text(json.dumps(rows, indent=2, ensure_ascii=False))


def build_engine(args, mock=None):
    load_env()
    cfg = dict(DEFAULT_CONFIG)
    if args.config:
        cfg.update(json.loads(Path(args.config).read_text()))
    if args.email_providers:
        cfg["email"] = args.email_providers.split(",")
    if args.phone_providers:
        cfg["phone"] = args.phone_providers.split(",")
    return Engine(cfg, Cache(args.cache), args.max_credits, mock)


def summarize(eng, rows, want_email, want_phone):
    n = len(rows)
    print("\n--- summary ---", file=sys.stderr)
    if want_email:
        ok = sum(1 for r in rows if r.get("email_status") in ("valid", "unverified"))
        risky = sum(1 for r in rows if r.get("email_status") in ("risky", "unknown"))
        bad = sum(1 for r in rows if r.get("email_status") == "invalid")
        print("email: %d/%d usable, %d risky/unknown, %d invalid" % (ok, n, risky, bad), file=sys.stderr)
    if want_phone:
        print("phone: %d/%d found" % (sum(1 for r in rows if r.get("phone_found")), n), file=sys.stderr)
    print("credits used: %s (total %d)" % (json.dumps(eng.spent), eng.total()), file=sys.stderr)
    for name, why in eng.dead.items():
        print("DISABLED %s: %s" % (name, why), file=sys.stderr)
    if eng.skipped_nokey:
        print("no key, skipped: %s (run `check`)" % ", ".join(sorted(eng.skipped_nokey)), file=sys.stderr)


def cmd_check(args):
    load_env()
    for name, cls in REGISTRY.items():
        pr = cls()
        print("%-16s %-8s %s" % (name, "/".join(cls.kinds), "key set" if pr.ready else "MISSING " + cls.env))


def cmd_run(args):
    recs = read_records(args.input)
    if args.limit:
        recs = recs[:args.limit]
    want_email = args.email or not args.phone
    eng = build_engine(args)
    if args.dry_run:
        ok = sum(1 for r in recs if can_match(normalize(r)))
        worst = {"email": 1, "phone": 10}
        est = ok * ((worst["email"] if want_email else 0) + (worst["phone"] if args.phone else 0))
        print("records: %d, matchable: %d, worst-case credits ~%d (only hits are charged)" % (len(recs), ok, est))
        print("email waterfall: %s | phone: %s | verifier: %s" % (
            ">".join(eng.cfg["email"]), ">".join(eng.cfg["phone"]), eng.cfg["verifier"]))
        return
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(lambda r: eng.enrich(r, want_email, args.phone, args.reverify), recs))
    write_records(rows, args.out)
    summarize(eng, rows, want_email, args.phone)


def cmd_verify(args):
    recs = read_records(args.input)
    eng = build_engine(args)

    def one(r):
        p = normalize(r)
        out = dict(r)
        trace = []
        out["email_status"] = eng.verify(p["email"], trace) if p["email"] else "no_email"
        return out
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(one, recs))
    write_records(rows, args.out)
    summarize(eng, rows, True, False)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("input", nargs="?", default="-", help="CSV/JSON/JSONL file, or - for stdin")
        p.add_argument("--out", help="output file (.csv/.json/.jsonl); default JSON on stdout")
        p.add_argument("--config", help="JSON file overriding the provider order")
        p.add_argument("--email-providers", help="comma list, e.g. prospeo,findymail")
        p.add_argument("--phone-providers", help="comma list")
        p.add_argument("--max-credits", type=int, help="hard cap on provider credits for this run")
        p.add_argument("--workers", type=int, default=4)
        p.add_argument("--cache", default=os.environ.get("ENRICH_CACHE", "~/.cache/enrich/cache.sqlite"),
                       help="sqlite cache path, or :none:")
    sub.add_parser("check")
    r = sub.add_parser("run")
    common(r)
    r.add_argument("--email", action="store_true", help="find emails (default if neither flag given)")
    r.add_argument("--phone", action="store_true", help="find phone numbers")
    r.add_argument("--reverify", action="store_true", help="re-verify even provider-verified emails")
    r.add_argument("--limit", type=int, help="only the first N records (use for a test run)")
    r.add_argument("--dry-run", action="store_true")
    v = sub.add_parser("verify")
    common(v)
    args = ap.parse_args(argv)
    {"check": cmd_check, "run": cmd_run, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    main()
