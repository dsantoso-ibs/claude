#!/usr/bin/env python3
"""Call TypeSafe's Jev (System One) directly: POST https://api.typesafe.ai/v1/systemone.

Stdlib only. Commands: setup, test, ask, batch. Key comes from $TYPESAFE_API_KEY or
~/.config/typesafe/api_key (chmod 600). The key is never printed.
"""
import argparse, concurrent.futures as cf, getpass, json, os, pathlib, random, sys, time
import urllib.request, urllib.error

URL = os.environ.get("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")
MODEL = os.environ.get("TYPESAFE_MODEL", "jev-latest")
KEY_FILE = pathlib.Path.home() / ".config" / "typesafe" / "api_key"
USD_PER_MTOK = 0.042  # input only; output is free (checked 2026-10, docs.typesafe.ai/models)
RETRY_STATUS = {429, 500, 502, 503, 504, 529}


def get_key():
    key = os.environ.get("TYPESAFE_API_KEY") or (KEY_FILE.read_text().strip() if KEY_FILE.exists() else "")
    if not key:
        sys.exit("No TypeSafe key. Run: python3 jev.py setup   (key from https://console.typesafe.ai/keys)")
    return key


def call(state, questions, model=MODEL, retries=5, timeout=30):
    """One request. Returns (response_json, seconds). Retries 429/5xx with backoff."""
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(URL, body, {
            "Authorization": f"Bearer {get_key()}", "Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r), time.time() - t0
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if e.code in RETRY_STATUS and attempt < retries:
                wait = float(e.headers.get("retry-after") or 2 ** attempt) + random.random() * 0.3
                time.sleep(wait)
                continue
            hint = {401: "bad/missing key", 422: "malformed request"}.get(e.code, "")
            raise RuntimeError(f"HTTP {e.code} {hint}: {detail}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"network error: {e}")


def flatten(resp, min_conf, noul_band):
    """Compact per-question view + a list of questions that need a human/Claude."""
    out, review = {}, []
    for qid, a in resp["answers"].items():
        t = a["type"]
        if t == "choice":
            out[qid] = {"choice": a["choice"], "confidence": a["confidence"]}
            unsure = a["confidence"] < min_conf
        elif t == "score":
            out[qid] = {"score": a["score"], "confidence": a["confidence"]}
            unsure = a["confidence"] < min_conf
        else:  # noul has no confidence; treat the middle of 0..1 as unsure
            out[qid] = {"noul": a["noul"]}
            unsure = noul_band[0] < a["noul"] < noul_band[1]
        if unsure:
            review.append(qid)
    return out, review


def cost(tokens):
    return tokens * USD_PER_MTOK / 1e6


def read_state(arg):
    text = sys.stdin.read() if arg == "-" else pathlib.Path(arg).read_text()
    try:
        return json.loads(text)
    except ValueError:
        return text


def cmd_setup(_):
    key = getpass.getpass("Paste TypeSafe API key (hidden): ").strip()
    if not key:
        sys.exit("empty key")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key)
    KEY_FILE.chmod(0o600)
    print(f"Saved to {KEY_FILE} (mode 600). Run: python3 jev.py test")


def cmd_test(_):
    state = ("Hi, we run an online skincare store and want an AI agent to answer our order emails. "
             "Budget is signed off and we want to start next month. Can we book a call this week?")
    qs = {
        "team": {"type": "choice", "instructions": "Which team should reply?",
                 "criteria": {"sales": "New business enquiry", "support": "Existing customer problem",
                              "billing": "Invoices, refunds"}},
        "lead_strength": {"type": "score", "instructions": "How good a lead is this?",
                          "criteria": ["Not a lead", "Cold", "Warm", "Hot: clear need plus budget/timeline"]},
        "needs_reply_today": {"type": "noul", "instructions": "Does this need a personal reply today?"},
    }
    resp, secs = call(state, qs)
    print(json.dumps(resp["answers"], indent=2))
    tok = resp["usage"]["input_tokens"]
    print(f"\nmodel={resp['model']}  {secs:.2f}s  input_tokens={tok}  cost=${cost(tok):.6f}")


def cmd_ask(a):
    qs = json.loads(pathlib.Path(a.questions).read_text())
    resp, secs = call(read_state(a.state), qs, a.model)
    flat, review = flatten(resp, a.min_confidence, (a.noul_low, a.noul_high))
    tok = resp["usage"]["input_tokens"]
    print(json.dumps({"answers": flat, "check": review, "full": resp["answers"] if a.full else None,
                      "seconds": round(secs, 2), "input_tokens": tok, "cost_usd": round(cost(tok), 6)},
                     indent=2))


def load_items(path):
    text = pathlib.Path(path).read_text()
    if path.endswith(".jsonl"):
        items = [json.loads(l) for l in text.splitlines() if l.strip()]
    else:
        items = json.loads(text)
    # accept ["text", ...] or [{"id":..., "state":...}, ...]
    return [i if isinstance(i, dict) and "state" in i else {"id": n, "state": i}
            for n, i in enumerate(items)]


def cmd_batch(a):
    qs = json.loads(pathlib.Path(a.questions).read_text())
    items = load_items(a.items)
    band = (a.noul_low, a.noul_high)
    results, total_tok, t0 = [None] * len(items), 0, time.time()

    def work(n):
        try:
            resp, _ = call(items[n]["state"], qs, a.model)
            flat, review = flatten(resp, a.min_confidence, band)
            return n, {"id": items[n]["id"], "answers": flat, "check": review}, resp["usage"]["input_tokens"]
        except Exception as e:  # keep going; failed items go to the check pile
            return n, {"id": items[n]["id"], "error": str(e), "check": ["error"]}, 0

    with cf.ThreadPoolExecutor(a.workers) as ex:
        for n, r, tok in ex.map(work, range(len(items))):
            results[n] = r
            total_tok += tok
    pathlib.Path(a.out).write_text(json.dumps(results, indent=2))
    flagged = sum(1 for r in results if r["check"])
    print(f"{len(items)} items in {time.time()-t0:.1f}s, {total_tok} input tokens, "
          f"${cost(total_tok):.5f}. {flagged} need checking. Wrote {a.out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    sub.add_parser("test").set_defaults(fn=cmd_test)
    for name, fn in (("ask", cmd_ask), ("batch", cmd_batch)):
        s = sub.add_parser(name)
        s.add_argument("--questions", required=True, help="JSON file: map of question id -> question")
        s.add_argument("--model", default=MODEL)
        s.add_argument("--min-confidence", type=float, default=0.6)
        s.add_argument("--noul-low", type=float, default=0.25)
        s.add_argument("--noul-high", type=float, default=0.75)
        if name == "ask":
            s.add_argument("--state", required=True, help="file path, or - for stdin (text or JSON)")
            s.add_argument("--full", action="store_true", help="include probabilities")
        else:
            s.add_argument("--items", required=True, help=".json list or .jsonl; strings or {id,state}")
            s.add_argument("--out", default="jev_results.json")
            s.add_argument("--workers", type=int, default=8)
        s.set_defaults(fn=fn)
    a = p.parse_args()
    try:
        a.fn(a)
    except RuntimeError as e:
        sys.exit(f"jev: {e}")


if __name__ == "__main__":
    main()
