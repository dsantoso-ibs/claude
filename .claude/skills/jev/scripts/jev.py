#!/usr/bin/env python3
"""jev.py - small client for TypeSafe's Jev (System One) API. Python 3.8+, stdlib only.

Talks directly to https://api.typesafe.ai (NOT OpenRouter).

Commands
  save-key   store the API key (hidden prompt or stdin) in a private file
  check      verify the key works (lists models; never prints the key)
  selftest   one real call: 3 questions about a made-up sales email
  ask        one request: a state + a questions JSON file
  choose     one Choice question from the command line
  batch      run the same questions over many items (csv / jsonl / json / folder)

The API key is read from $TYPESAFE_API_KEY, else from ~/.config/typesafe/api_key.
It is never printed and never passed as a command-line argument.
"""
import argparse
import concurrent.futures as cf
import csv
import getpass
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai").rstrip("/")
DEFAULT_MODEL = os.environ.get("JEV_MODEL", "jev-latest")  # pin "jev-1.13.0" once thresholds are tuned
PRICE_PER_MTOK_USD = 0.042  # input only, output is free. Re-check https://docs.typesafe.ai/models
KEY_FILE = Path(os.environ.get("TYPESAFE_KEY_FILE", "~/.config/typesafe/api_key")).expanduser()
UA = "jev-skill/1.0 (python-urllib)"
TEXT_SUFFIXES = {".txt", ".md", ".eml", ".html", ".htm", ".log"}


class JevError(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


# --------------------------------------------------------------------------- key + http
def get_key():
    k = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if k:
        return k
    if KEY_FILE.exists():
        k = KEY_FILE.read_text().strip()
        if k:
            return k
    raise JevError(
        "No TypeSafe API key found. Create one at https://console.typesafe.ai/keys, then run "
        f"`python3 {Path(__file__).name} save-key` in your own terminal, or export TYPESAFE_API_KEY."
    )


def _ssl_context():
    """Verified TLS only. Prefer the certifi bundle when installed (fixes python.org builds on macOS
    that ship without root certificates); honour SSL_CERT_FILE if the user set it."""
    if os.environ.get("SSL_CERT_FILE"):
        return ssl.create_default_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


CERT_HINT = (
    "\nTLS certificate verification failed (your Python has no root certificates; nothing reached TypeSafe)."
    "\nFix, then re-run:  python3 -m pip install --upgrade certifi"
    "\nIf pip is unavailable: /usr/bin/python3 <this script> ...  (macOS system Python)."
    "\nDo not disable verification: this script sends your API key."
)


def http(method, path, payload=None, timeout=30, retries=4):
    key = get_key()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "Accept": "application/json", "User-Agent": UA}
    data = json.dumps(payload).encode() if payload is not None else None
    delay = 0.5
    for attempt in range(retries + 1):
        req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace").replace(key, "***")
            if e.code in (429, 529) and attempt < retries:  # rate limited / overloaded: back off
                ra = e.headers.get("retry-after", "")
                try:
                    wait = float(ra)
                except ValueError:
                    wait = delay
                time.sleep(min(wait, 20))
                delay *= 2
                continue
            hint = {401: " (missing/invalid key)", 422: " (request failed validation - see body)",
                    429: " (rate limited, retries exhausted)", 529: " (overloaded, retries exhausted)"}.get(e.code, "")
            raise JevError(f"HTTP {e.code}{hint}: {body[:800]}", e.code)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                raise JevError(f"Network error talking to {BASE_URL}: {e}{CERT_HINT}")
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise JevError(f"Network error talking to {BASE_URL}: {e}")


def jev_call(state, questions, model=None):
    t0 = time.time()
    resp = http("POST", "/v1/systemone",
                {"state": state, "model": model or DEFAULT_MODEL, "questions": questions})
    return resp, time.time() - t0


def cost_usd(input_tokens):
    return input_tokens * PRICE_PER_MTOK_USD / 1_000_000


# --------------------------------------------------------------------------- answers
def flatten(ans):
    """-> dict(type, value, confidence, probs). Noul has no API confidence: use |2p-1| (documented)."""
    t = ans.get("type")
    if t == "choice":
        return {"type": t, "value": ans.get("choice"), "confidence": ans.get("confidence"),
                "probs": ans.get("probabilities")}
    if t == "score":
        return {"type": t, "value": ans.get("score"), "confidence": ans.get("confidence"),
                "probs": ans.get("probabilities")}
    if t == "noul":
        p = ans.get("noul")
        return {"type": t, "value": p, "confidence": None if p is None else abs(2 * p - 1), "probs": None}
    return {"type": t, "value": None, "confidence": None, "probs": None}


def is_uncertain(flat, min_conf, noul_min_conf):
    c = flat["confidence"]
    if c is None:
        return True
    return c < (noul_min_conf if flat["type"] == "noul" else min_conf)


def fmt_answer(qid, ans):
    f = flatten(ans)
    if f["type"] == "choice":
        pr = ", ".join(f"{k} {v:.2f}" for k, v in sorted((f["probs"] or {}).items(), key=lambda kv: -kv[1])[:4])
        return f"{qid}: choice={f['value']}  confidence={f['confidence']:.2f}  ({pr})"
    if f["type"] == "score":
        legend = ans.get("legend", {})
        near = legend.get(str(round(f["value"])), "")
        return f"{qid}: score={f['value']:.2f}  confidence={f['confidence']:.2f}  (nearest level: {near})"
    if f["type"] == "noul":
        return f"{qid}: noul={f['value']:.2f}  (probability yes; no confidence field - near 0.5 = unsure)"
    return f"{qid}: {ans}"


# --------------------------------------------------------------------------- commands
def cmd_save_key(a):
    if sys.stdin.isatty():
        key = getpass.getpass("TypeSafe API key (hidden): ").strip()
    else:
        key = sys.stdin.read().strip()
    if not key or any(c.isspace() for c in key):
        raise JevError("That doesn't look like a key (empty or contains whitespace). Nothing saved.")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(KEY_FILE.parent, 0o700)
    except OSError:
        pass
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(key + "\n")
    os.chmod(KEY_FILE, 0o600)
    print(f"Saved to {KEY_FILE} (owner-only permissions). The key is not displayed. Run `check` next.")


def cmd_check(a):
    r = http("GET", "/v1/models")
    names = [m.get("name") for m in r.get("models", [])]
    print("Key works. Models available:", ", ".join(n for n in names if n) or "(none listed)")


SELFTEST_EMAIL = (
    "Hi, we run an online skincare store and want an AI agent to answer our order emails. "
    "Budget is signed off and we want to start next month. Can we book a call this week?"
)
SELFTEST_QUESTIONS = {
    "lead_strength": {
        "type": "score",
        "instructions": "How strong a sales lead is this email for a small AI automation agency?",
        "criteria": [
            "Not a lead at all: spam, vendor pitch, newsletter, job seeker, support request or existing client",
            "Cold: vague interest, tiny budget or poor fit",
            "Warm: a real need that fits, but no budget or timeline yet",
            "Hot: a clear need that fits, plus at least two of: a stated budget, a stated timeline, a decision maker writing",
        ],
    },
    "email_kind": {
        "type": "choice",
        "instructions": "What kind of email is this?",
        "criteria": {
            "new_lead": "Someone who is not yet a client asking about our services",
            "existing_client": "A current client writing about their work with us",
            "vendor_pitch": "Someone trying to sell us something",
            "spam": "Unwanted bulk or scam email",
            "job_seeker": "Someone asking for a job",
            "newsletter": "A mass-mailed newsletter or announcement",
            "support": "A request for help with something already bought",
        },
    },
    "needs_personal_reply": {
        "type": "noul",
        "instructions": "Does this email need a personal reply from a human on our team?",
        "criteria": {"true": "A person is asking something that needs a human answer",
                     "false": "Automated, bulk or informational; no personal reply needed"},
    },
}


def cmd_selftest(a):
    print(f"Test email: {SELFTEST_EMAIL}\n")
    resp, dt = jev_call(SELFTEST_EMAIL, SELFTEST_QUESTIONS, a.model)
    for qid, ans in resp["answers"].items():
        print(fmt_answer(qid, ans))
    u = resp.get("usage", {})
    print(f"\nmodel={resp.get('model')}  time={dt:.2f}s  input_tokens={u.get('input_tokens')}  "
          f"output_tokens={u.get('output_tokens')} (free)  cost=${cost_usd(u.get('input_tokens', 0)):.6f}")


def _read_state(a):
    if a.state is not None:
        s = a.state
    elif a.state_file:
        s = sys.stdin.read() if a.state_file == "-" else Path(a.state_file).read_text()
    else:
        raise JevError("Provide --state TEXT or --state-file PATH (use - for stdin).")
    if a.json_state:
        return json.loads(s)
    return s


def _load_json_arg(v):
    v = v.strip()
    return json.loads(v) if v.startswith("{") else json.loads(Path(v).read_text())


def cmd_ask(a):
    state = _read_state(a)
    questions = _load_json_arg(a.questions)
    resp, dt = jev_call(state, questions, a.model)
    if a.raw:
        print(json.dumps(resp, indent=2))
    else:
        for qid, ans in resp["answers"].items():
            print(fmt_answer(qid, ans))
    u = resp.get("usage", {})
    print(f"\nmodel={resp.get('model')} time={dt:.2f}s input_tokens={u.get('input_tokens')} "
          f"cost=${cost_usd(u.get('input_tokens', 0)):.6f}", file=sys.stderr)


def cmd_choose(a):
    crit = {}
    for o in a.option:
        name, _, desc = o.partition("=")
        crit[name.strip()] = desc.strip() or None
    if len(crit) < 2:
        raise JevError("Give at least two --option name=description pairs.")
    q = {"pick": {"type": "choice", "instructions": a.instructions, "criteria": crit}}
    resp, dt = jev_call(_read_state(a), q, a.model)
    ans = resp["answers"]["pick"]
    print(json.dumps({"choice": ans["choice"], "confidence": ans["confidence"],
                      "probabilities": ans["probabilities"], "seconds": round(dt, 2)}))


# ---- batch
def load_items(path, text_key, id_key, extra_keys):
    p = Path(path)
    items = []

    def mk(i, rid, text, row):
        extra = {k: row.get(k, "") for k in extra_keys} if row else {}
        return {"id": str(rid if rid not in (None, "") else i), "text": text, "extra": extra}

    if p.is_dir():
        files = [f for f in sorted(p.rglob("*")) if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES]
        for i, f in enumerate(files):
            items.append(mk(i, f.relative_to(p), f.read_text(errors="replace"), None))
    elif p.suffix.lower() == ".csv":
        with open(p, newline="", encoding="utf-8-sig") as fh:
            rd = csv.DictReader(fh)
            if text_key not in (rd.fieldnames or []):
                raise JevError(f"CSV has no column '{text_key}'. Columns: {rd.fieldnames}. Use --text-col.")
            for i, row in enumerate(rd):
                items.append(mk(i + 1, row.get(id_key) if id_key else None, row.get(text_key, ""), row))
    elif p.suffix.lower() in (".jsonl", ".json"):
        raw = p.read_text(encoding="utf-8-sig")
        rows = ([json.loads(l) for l in raw.splitlines() if l.strip()]
                if p.suffix.lower() == ".jsonl" else json.loads(raw))
        for i, row in enumerate(rows):
            if isinstance(row, str):
                items.append(mk(i + 1, None, row, None))
            else:
                items.append(mk(i + 1, row.get(id_key) if id_key else None, str(row.get(text_key, "")), row))
    else:
        raise JevError(f"Don't know how to read {path}. Use .csv, .jsonl, .json or a folder of .txt/.md/.eml files.")
    return items


def build_state(item, context, text_field, max_chars):
    text = item["text"] or ""
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars] + "\n[...truncated...]"
    state = {}
    if context:
        state["context"] = context
    state[text_field] = text
    state.update(item["extra"])
    return state, truncated


def check_refs(questions, state):
    """Warn if a question references a `field` that the state doesn't have (typo guard)."""
    roots = set(re.findall(r"`([A-Za-z_]\w*)", json.dumps(questions)))
    missing = sorted(r for r in roots if r not in state)
    if missing:
        print(f"WARNING: questions reference {missing} but the state only has {sorted(state)}. "
              "Fix --text-field / --context / --extra-cols or the question wording.", file=sys.stderr)


def cmd_batch(a):
    questions = _load_json_arg(a.questions)
    extra_keys = [c for c in (a.extra_cols or "").split(",") if c]
    items = load_items(a.input, a.text_col, a.id_col, extra_keys)
    if a.limit:
        items = items[: a.limit]
    if not items:
        raise JevError("No items found in the input.")
    built = [build_state(it, a.context, a.text_field, a.max_chars) for it in items]
    check_refs(questions, built[0][0])

    if a.dry_run:
        chars = sum(len(json.dumps(s)) for s, _ in built) + len(items) * len(json.dumps(questions))
        est_tok = chars // 4
        print(f"DRY RUN - nothing sent. {len(items)} items -> {len(items)} requests to {BASE_URL}")
        print(f"Rough size ~{est_tok:,} input tokens, ~${cost_usd(est_tok):.4f}. Output tokens are free.")
        print(f"Truncated items: {sum(1 for _, t in built if t)}")
        print("First request state (this is exactly what would leave your computer):")
        print(json.dumps(built[0][0], ensure_ascii=False, indent=2)[:3000])
        print("Questions:", json.dumps(questions, ensure_ascii=False)[:1500])
        return

    results = [None] * len(items)
    t0 = time.time()
    done = 0

    def work(i):
        try:
            resp, _ = jev_call(built[i][0], questions, a.model)
            return i, resp, None
        except JevError as e:
            return i, None, str(e)

    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, resp, err in ex.map(work, range(len(items))):
            results[i] = (resp, err)
            done += 1
            if done % 10 == 0 or done == len(items):
                print(f"  {done}/{len(items)} done", file=sys.stderr)
    wall = time.time() - t0

    qids = list(questions)
    rows, in_tok, model_seen = [], 0, None
    for it, (state_trunc), (resp, err) in zip(items, built, results):
        row = {"id": it["id"], "preview": re.sub(r"\s+", " ", it["text"] or "")[:100],
               "truncated": "yes" if state_trunc[1] else ""}
        reasons = []
        if err or not resp:
            row["error"] = err or "no response"
            row["needs_review"] = "yes"
            rows.append((row, None))
            continue
        model_seen = resp.get("model")
        in_tok += resp.get("usage", {}).get("input_tokens", 0)
        for q in qids:
            ans = resp["answers"].get(q)
            if not ans:
                reasons.append(f"{q}:missing")
                continue
            f = flatten(ans)
            v = f["value"]
            row[q] = round(v, 3) if isinstance(v, float) else v
            row[q + "_conf"] = None if f["confidence"] is None else round(f["confidence"], 3)
            if is_uncertain(f, a.min_confidence, a.noul_min_confidence):
                reasons.append(q)
        if state_trunc[1]:
            reasons.append("truncated")
        row["needs_review"] = "yes" if reasons else ""
        row["review_reasons"] = ",".join(reasons)
        rows.append((row, resp))

    if a.sort:
        key, _, direction = a.sort.partition(":")
        rev = direction.lower() != "asc"

        def sk(pair):
            r = pair[0]
            v = r.get(key)
            return (1, 0) if not isinstance(v, (int, float)) else (0, -v if rev else v)

        rows.sort(key=sk)

    base = Path(a.out)
    base.parent.mkdir(parents=True, exist_ok=True)
    with open(f"{base}.jsonl", "w", encoding="utf-8") as fh:
        for r, resp in rows:
            fh.write(json.dumps({"row": r, "response": resp}, ensure_ascii=False) + "\n")
    cols = ["id", "preview"]
    for q in qids:
        cols += [q, q + "_conf"]
    cols += ["needs_review", "review_reasons", "truncated", "error"]
    with open(f"{base}.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r, _ in rows:
            w.writerow(r)

    n_err = sum(1 for r, _ in rows if r.get("error"))
    n_rev = sum(1 for r, _ in rows if r.get("needs_review"))
    if n_err == len(rows):
        raise JevError("Every request failed. First error: " + next(r["error"] for r, _ in rows if r.get("error")))
    print(f"\n{len(items)} items in {wall:.1f}s  model={model_seen}  input_tokens={in_tok:,}  "
          f"cost=${cost_usd(in_tok):.5f}  errors={n_err}  needs_review={n_rev}")
    for q in qids:
        if questions[q].get("type") == "choice":
            counts = {}
            for r, _ in rows:
                if r.get(q) is not None:
                    counts[r[q]] = counts.get(r[q], 0) + 1
            if counts:
                print(f"  {q}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))
    if n_err:
        print(f"  {n_err} item(s) failed - see the 'error' column; first: "
              + next(r["error"] for r, _ in rows if r.get("error"))[:200])
    print(f"Wrote {base}.csv and {base}.jsonl")


# --------------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description="Jev (TypeSafe System One) client - direct API")
    ap.add_argument("--model", default=None, help=f"default {DEFAULT_MODEL}; pin e.g. jev-1.13.0")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("save-key").set_defaults(fn=cmd_save_key)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("selftest").set_defaults(fn=cmd_selftest)

    def add_state(p):
        p.add_argument("--state")
        p.add_argument("--state-file")
        p.add_argument("--json-state", action="store_true", help="parse the state as JSON (object/array)")

    p = sub.add_parser("ask")
    add_state(p)
    p.add_argument("--questions", required=True, help="path to questions JSON, or a JSON string")
    p.add_argument("--raw", action="store_true")
    p.set_defaults(fn=cmd_ask)

    p = sub.add_parser("choose")
    add_state(p)
    p.add_argument("--instructions", required=True)
    p.add_argument("--option", action="append", required=True, help="name=description (repeat)")
    p.set_defaults(fn=cmd_choose)

    p = sub.add_parser("batch")
    p.add_argument("--input", required=True, help=".csv / .jsonl / .json / folder of .txt .md .eml")
    p.add_argument("--questions", required=True)
    p.add_argument("--context", help="one line about the business; sent as state field `context`")
    p.add_argument("--text-col", default="text", help="column/key holding the item text (default text)")
    p.add_argument("--id-col", help="column/key to use as the row id")
    p.add_argument("--extra-cols", help="comma list of extra columns/keys to send as their own state fields")
    p.add_argument("--text-field", default="text", help="state field name for the item text, e.g. email")
    p.add_argument("--max-chars", type=int, default=20000)
    p.add_argument("--workers", type=int, default=8, help="parallel requests (limit is 80 req/s)")
    p.add_argument("--min-confidence", type=float, default=0.6, help="choice/score below this -> needs_review")
    p.add_argument("--noul-min-confidence", type=float, default=0.2,
                   help="noul with |2p-1| below this (p within 0.4-0.6 by default) -> needs_review")
    p.add_argument("--sort", help="question_id:desc|asc (numeric answers: score/noul)")
    p.add_argument("--limit", type=int)
    p.add_argument("--out", default="jev-results")
    p.add_argument("--dry-run", action="store_true", help="show what would be sent; send nothing")
    p.set_defaults(fn=cmd_batch)

    a = ap.parse_args()
    try:
        a.fn(a)
    except JevError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
