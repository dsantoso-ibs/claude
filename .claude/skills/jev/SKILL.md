---
name: jev
description: Use TypeSafe's Jev, a very fast, very cheap decision model (System One), to sort, triage, classify, score and route piles of text. Calls the TypeSafe API directly (api.typesafe.ai), not OpenRouter. Use when the user says "use Jev", "ask Jev", "sort/triage/rank/classify these with Jev", or wants to sort an inbox by lead quality, triage support tickets, screen supplier invoices for fraud signs, route a message to a skill or model, or make many small yes/no, pick-one or rate-on-a-scale decisions over many items cheaply. Also use for setting up or testing the TypeSafe API key and for any mention of typesafe, System One or jev-latest. Jev decides, Claude writes. Never use Jev for writing, chat, reasoning, counting, maths or date arithmetic.
---

# Jev via TypeSafe (direct)

Jev is not an LLM. It never writes text. You send a **state** (text or JSON) plus typed **questions**; it returns decisions in about 0.3 s. Input costs $0.042 per 1M tokens, output is free. This skill talks to TypeSafe directly, so no OpenRouter account is involved.

**Rule: Jev decides, Claude writes.** Jev picks, scores and flags. Claude drafts replies, does maths and date checks, and makes the call when Jev is unsure.

## Endpoint

```
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer $TYPESAFE_API_KEY
{"state": <string|object|array>, "model": "jev-latest", "questions": {<id>: <question>}}
```

Model is `jev-latest` (currently `jev-1.13.0`). Not `typesafe/jev-1.13`, which is the OpenRouter name. Limits: 64K tokens per request (32K for state plus the longest question), text only, English works best, 80 req/s.

Docs, if anything has moved: https://docs.typesafe.ai/llms.txt (API reference: https://docs.typesafe.ai/api.md).

## Setup (once)

1. Get a key at https://console.typesafe.ai/keys.
2. Run `python3 .claude/skills/jev/scripts/jev.py setup`. It prompts with hidden input and saves to `~/.config/typesafe/api_key` (mode 600). Alternatively export `TYPESAFE_API_KEY`.
3. Run `python3 .claude/skills/jev/scripts/jev.py test`. It sends a made-up sales email with 3 questions and prints answers, latency and cost.

Key handling: never ask the user to paste the key into chat, never write it into the repo or any file that might be shared, never echo it back. If the test fails, show the exact error (401 means bad key, 422 means malformed request).

## Question types

| Type | Use for | `criteria` | Answer |
|---|---|---|---|
| `choice` | pick one option | map `option -> description` (or `null`), max 255 options | `choice`, `probabilities`, `confidence` |
| `score` | rate on your scale | ordered array of level descriptions (2 to 10) | `score` (can fall between levels), `confidence` |
| `noul` | probability a statement is true | optional `{"true": ..., "false": ...}` | `noul` 0 to 1 (no confidence field) |

```json
{
  "team":  {"type": "choice", "instructions": "Which team should reply?",
            "criteria": {"sales": "New business", "support": "Existing customer problem"}},
  "lead":  {"type": "score",  "instructions": "How strong a lead is this?",
            "criteria": ["Not a lead", "Cold", "Warm", "Hot"]},
  "reply": {"type": "noul",   "instructions": "Does this need a personal reply today?"}
}
```

Tips: write level and option descriptions concretely (they are the rubric). Ask several questions in one call, since they are answered in one parallel pass and the state is only billed once. `instructions` may be an object holding the question plus extra data, referenced by name in backticks (for example `known_supplier`). Question ids are yours and are not sent to the model.

## Helper script

`scripts/jev.py` (stdlib Python 3, no installs) handles auth, retry with backoff on 429/5xx, concurrency, confidence gating and cost.

```bash
# one state, several questions
python3 .claude/skills/jev/scripts/jev.py ask --state email.txt --questions .claude/skills/jev/examples/lead-quality.json

# a pile: .json list or .jsonl of strings or {"id":..., "state":...}; one call per item, 8 in parallel
python3 .claude/skills/jev/scripts/jev.py batch --items emails.json \
  --questions .claude/skills/jev/examples/lead-quality.json --out results.json
```

Output per item: compact `answers`, plus `check`, the list of question ids Jev is unsure about. Default thresholds: choice/score `confidence < 0.6`, or noul between 0.25 and 0.75. Tune with `--min-confidence`, `--noul-low`, `--noul-high`. Failed items land in the check pile with an `error`. The summary line prints items, seconds, input tokens and cost.

Ready-made question sets in `examples/`: `lead-quality.json` (inbox sorting), `ticket-triage.json` (support), `invoice-fraud.json` (supplier invoices).

## Workflows

**Sort an inbox by lead quality.** Load emails, run `batch` with `lead-quality.json`, sort by `lead.score` descending, output one spreadsheet with hot leads on top. Items in `check` go to a "check these" pile for Claude or the user. Claude drafts replies for hot leads only.

**Triage tickets.** `ticket-triage.json`. If the plan and customer tenure are known, include them in the state, as `{"ticket": "...", "plan": "...", "months": 14}`. Flag low-confidence items for a person. Claude writes first replies for `urgency == today` only.

**Screen supplier invoices.** Jev reads text only, so convert each invoice to plain text first and include what is known about the supplier (usual bank details, usual amounts, last invoice date) as `known_supplier`. Do the sums and date comparisons in code or yourself, not in Jev. Output a table, riskiest first, with one line why. Nothing is paid or rejected on Jev's word alone.

**Route a message** (model size or skill choice). Ask one `choice` question with the candidate options and descriptions. If `confidence < 0.6`, Claude decides. Jev cannot switch Claude's model mid-session, so route to a pinned subagent or just use it as a hint.

**Confidence-gated action.** Act automatically only when confident (for example 0.9 or higher for anything that hides or deletes). Everything else stays for a person.

## Do not use Jev for

Writing, chat, reasoning, counting, maths, date arithmetic, or long inputs full of irrelevant text. Give those to Claude or code. Batch many small items rather than one huge state, and keep each state under 32K tokens.

## Privacy

Everything sent as `state` or `instructions` leaves this machine for TypeSafe. Ask the user before sending anything private (personal data, contracts, financials, customer PII). Say so plainly when the data looks sensitive, and offer to redact first.
