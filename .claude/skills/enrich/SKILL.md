---
name: enrich
description: Find and verify business email addresses and phone numbers for a list of contacts using a provider waterfall (Prospeo, then Findymail, then others) with email verification, the same pattern Clay and lemlist use. Source-agnostic - works on CSV/JSON from anywhere, including records Claude pulls from Salesforce or lemlist via MCP and writes back. Use whenever the user wants to enrich prospects or leads, find or look up emails or phone numbers, find a mobile number, validate, verify or clean email addresses, check whether emails are valid or bounce, "waterfall" enrichment, or fill missing contact data on a list, campaign or CRM records.
---

# Contact enrichment waterfall

`scripts/enrich.py` (Python 3.8+, standard library only). It takes plain records and returns the same records plus enrichment fields. It does not know about Salesforce or lemlist: **Claude moves the data**, the script enriches it.

How the waterfall works: for each contact it tries provider 1; on a miss it tries provider 2, and so on. A found email is accepted straight away only if the provider itself verified it (Prospeo and Findymail only return verified emails); otherwise it goes through the verifier. `invalid` falls through to the next provider; `risky` / `unknown` is kept only as a last resort. Phones have no verifier. Providers charge only on a hit. Results (hits and misses) are cached in sqlite, so a rerun never pays twice.

## 1. First use

1. `python3 scripts/enrich.py check` shows which keys exist. Never print or ask the user to paste keys into chat. Tell them to put keys in `~/.config/enrich/.env` (or a git-ignored `.env`):
   ```
   PROSPEO_API_KEY=...
   FINDYMAIL_API_KEY=...
   MILLIONVERIFIER_API_KEY=...
   ```
2. Providers without a key are skipped automatically, so partial setups work. With no verifier key, emails the provider did not verify come back as `unverified`.
3. `python3 -m unittest discover -s tests` (offline, mocked) confirms the engine itself works.

## 2. Typical flow from Claude

**Ask which enrichment first: email or phone. Never both in one run.** The CLI enforces this (`--email` or `--phone`, exactly one). Phones cost about 10x an email, so phone enrichment is only for when it is necessary: default to email, and offer phone afterwards only for the contacts that matter (e.g. valid email found, high-priority account), by writing just those records to a new file.

1. **Get records** with whatever fits: Salesforce MCP (`soqlQuery` on Contact/Lead: Id, FirstName, LastName, Account.Name, Account.Website, LinkedIn field, Email, Phone), lemlist MCP (`search_campaign_leads`, `search_contacts`), or a CSV the user supplies. Write them to a JSON file in the scratchpad. **Keep the record id** (`id`, `Id`, anything) - it passes through untouched and is how results get matched back.
2. **Dry run and a test**: `run records.json --email --dry-run` (or `--phone`), then `run records.json --email --limit 10 --out test.csv`. Show the user the hit rate and credits before the full run.
3. **Full run**: `run records.json --email --out enriched.json --max-credits 500`. Always set `--max-credits` on big lists.
4. **Write back** only after the user has seen the results. Salesforce: `updateSobjectRecord` per row (or review a CSV first). lemlist: `update_lead` / `create_or_update_contact`. Don't overwrite an existing value without telling the user. Only write rows with `email_status` `valid` (or `unverified` if the user accepts that); never write `risky`, `unknown`, `invalid`.

Pure verification of emails already on file: `verify records.json --out verified.json` (adds `email_status`).

## 3. Input and output

Input columns are matched flexibly (`First Name`, `firstname`, `Account`, `Website`, `LinkedIn URL`, ...). Minimum per record: a **LinkedIn URL**, or **full name + company or domain**. A domain is much more accurate than a company name. Records below the minimum are skipped without spending credits.

Added fields: `email_found`, `email_status` (`valid`, `unverified`, `risky`, `unknown`, `invalid`, `not_found`, `not_checked`), `email_source`, `phone_found`, `phone_source`, `phone_type`, `enrich_trace` (e.g. `prospeo:miss > findymail:hit`).

Flags: `--email` or `--phone` (required, mutually exclusive), `--email-providers a,b`, `--phone-providers a,b`, `--config file.json` (`{"email":[...],"phone":[...],"verifier":"..."}`), `--workers N`, `--cache :none:`, `--reverify`.

## 4. Providers (see `references/providers.md`)

Default chain: email `prospeo > findymail`, phone `prospeo > findymail`, verifier `millionverifier`. Add a provider by writing a `Provider` subclass in `enrich.py` (`find_email`, `find_phone` or `verify`, a `credits` table) and registering it in `REGISTRY`. Only add one after reading its current API docs.

## 5. Rules

- **Personal data.** Names and company data are sent to the providers. Tell the user once per dataset, and don't enrich EU contacts without the user confirming they have a lawful basis (GDPR). Findymail documents that it returns nothing for EU persons' phones.
- **Hit rates are not guaranteed.** Vendor figures (about 80% email, 66% phone) are marketing; report the real numbers from the run summary.
- **Credits cost real money.** Phones are about 10x an email. Emails first; phones only where necessary.
- If a provider shows `DISABLED` in the summary (bad key or no credits), say so; the run continued with the others.
