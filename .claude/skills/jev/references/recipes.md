# Jev recipes

All commands assume `python3 scripts/jev.py` from the skill folder. Always `--dry-run` first on private data and confirm with the user. Question files live in `assets/questions/`; copy and edit them to fit the user's business, since the scale wording is what makes the scores meaningful.

Contents: 1 Sort an inbox by lead quality · 2 Triage support tickets · 3 Screen supplier invoices · 4 Pick the right skill for a message · 5 Route messages to a smaller model · 6 Filter relevant passages

---

## 1. Sort an inbox by lead quality

Questions: `assets/questions/leads.json` → `lead_strength` (score 0 to 3: not a lead / cold / warm / hot), `email_kind` (choice), `needs_personal_reply` (noul).

1. Get the emails into a CSV/JSONL/folder (one email per row/file; subject + body is plenty, drop long quoted history and signatures).
2. Write a **one-line description of what the business does** for `--context`. Jev needs it to judge "fit".
3. Edit the `lead_strength` levels if the user's definition of hot differs (e.g. what counts as a budget signal).
4. Run:
   ```bash
   python3 scripts/jev.py batch --input inbox.csv --text-col body --id-col id --text-field email \
     --context "<one line about the business>" --questions assets/questions/leads.json \
     --sort lead_strength:desc --out results/leads --dry-run
   ```
   Then without `--dry-run`.
5. Deliver `results/leads.csv` (hot leads on top). Rows with `needs_review=yes` form the **"check these" pile**; judge those yourself.
6. **Draft replies for the hot leads only** (that's Claude's job, not Jev's). Do not send anything without the user's go-ahead.

## 2. Triage support tickets by urgency and team

Questions: `assets/questions/tickets.json` → `urgency` (today / this_week / no_rush), `team` (technical / billing / sales / success), `churn_risk` (score 0 to 3).

- Use `--text-field ticket`. If the user has plan and tenure per customer, put them in an `account` column and add `--extra-cols account` (the churn question already refers to `account`). Remove that reference from the question if you don't have the column.
- Sort: urgency is a choice, so sort numerically by `churn_risk:desc` and group by `urgency` in the CSV afterwards (or add a numeric score question for urgency if the user wants strict ordering).
- Flagged rows → a person reads them. Write first replies for the `today` tickets only.

## 3. Screen supplier invoices for fraud signs

Questions: `assets/questions/invoices.json` → `risk` (score 0 to 3), `bank_change_with_pressure` (noul), `action` (pay_as_normal / hold_and_call_supplier / reject).

Jev reads **text only** and is weak at maths and dates, so split the work:

1. Convert each invoice to plain text first (PDF → text; OCR if scanned).
2. **Do the checks in code** and write the results as plain sentences into a `code_checks` column, for example:
   - `bank details differ from supplier record: yes`
   - `amount is 3.4x this supplier's average invoice`
   - `invoice date is 41 days after the supplier's last invoice`
   - `payment deadline stated: 2 days`
3. Put what you know about the supplier in a `supplier_known` column (usual bank details, usual amounts, date of last invoice, as text).
4. Run with `--text-field invoice --extra-cols supplier_known,code_checks --sort risk:desc`.
5. Present a table, riskiest first, with one line on why each was flagged (use the `code_checks` plus the invoice text).
6. **Nothing is paid, held or rejected on Jev's word.** It only decides what a human looks at first. Hold-and-call means phoning the supplier on a number already on file, never one from the invoice.

Privacy: invoices carry bank details. Ask before sending; consider masking all but the last 4 characters of account numbers in `invoice` and doing the "do they match?" comparison in code (that is what `code_checks` is for).

## 4. Pick the right skill (or tool, template, doc) for a message

One `choice` question where each option is a skill name and its one-line description, plus a `none` option:

```bash
python3 scripts/jev.py choose --state-file user_message.txt \
  --instructions "Which skill should be loaded for this request? Choose none if no skill clearly fits." \
  --option "docx=Create or edit Word documents" --option "xlsx=Spreadsheets and CSV work" \
  --option "none=No skill clearly fits"
```

- Take the answer if `confidence >= 0.6`; below that, Claude decides.
- Up to 255 options are allowed. Keep descriptions to the name plus the first line.
- Jev leans toward earlier options: for important routing, run twice with the list reversed and only accept agreeing answers.
- TypeSafe's skill-suggestion cookbook uses two requests (rank, then re-check the top few): https://docs.typesafe.ai/cookbooks/skill_suggestion.md

## 5. Route messages to a smaller, cheaper model

Idea: Jev names the smallest model that can do a job, and the job goes to a helper pinned to that model.

- Sizes to offer Jev (adapt to the models the user actually has): **tiny** (lookup, rename, one-line answer), **everyday** (normal email, post or short document), **large** (multi-step build, research, full report), **hardest** (strategy, or anything where a wrong call is expensive). Use fewer tiers if fewer models are available.
- Gate: if confidence < 0.6, or the message is a short reply that only makes sense inside the conversation ("yes do that but shorter"), Claude handles it itself.
- It must never slow or block a message; on any error, carry on without the router.
- Honest constraint in Claude Code: a hook can add a note to a message but cannot switch the model. The achievable design is a hook that calls `choose` and adds "Jev sized this as X, confidence Y", plus one helper agent per tier with the model pinned in its `model:` line. Say so plainly instead of inventing a setting.
- Keep it **off by default** with on/off/status switches. While on, every message goes to TypeSafe, so it stays off for private work.
- This skill does not build the hook automatically. If the user wants it, build it as a separate task, test it with ~8 sample messages from tiny to hardest plus 2 short replies, and show a table of what Jev picked and how sure it was.

## 6. Filter relevant passages (shrink a big input first)

Jev degrades when the state is padded with irrelevant text, so shrink it with Jev itself: one `noul` per passage ("Is `passage` relevant to the question in `query`?"), keep passages with p above about 0.5, then ask the real questions over what's left. Cookbook: https://docs.typesafe.ai/cookbooks/classifying_rag_passages.md

Use `batch` with a JSONL where each row has `text` (the passage) and `query` (extra column), and a one-question file. Count and combine the answers in code, never ask Jev to count.
