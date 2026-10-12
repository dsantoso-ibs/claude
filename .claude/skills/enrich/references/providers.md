# Providers

Verified against vendor docs on 2026-10-12. Re-check before relying on prices.

| Provider | Role | Auth | Endpoint | Cost | Notes |
|---|---|---|---|---|---|
| Prospeo | email + mobile | `X-KEY` header | `POST https://api.prospeo.io/enrich-person` | 1 credit/email, 10/mobile, free on no match, free re-enrich within 90 days | Needs LinkedIn URL, or first+last name + company website/name. `NO_MATCH` returns HTTP 400 with `error_code`. |
| Findymail | email + phone | `Authorization: Bearer` | `POST /api/search/name`, `/api/search/business-profile`, `/api/search/phone`, `/api/verify` | 1 credit per verified email, 10 per phone | Phone: LinkedIn URL required, US numbers only, no results for EU persons. Verify charges even when the result is negative. |
| MillionVerifier | verifier | `api` query param | `GET https://api.millionverifier.com/api/v3/` | about 1.5 USD per 1,000 (third-party figure, unconfirmed) | `ok` = valid, `catch_all` = risky. Not independently benchmarked; test a few thousand of your own addresses. |

## Not yet implemented (docs could not be read when this was written)

Icypeas, Leadmagic, Hunter, Datagma, Dropcontact (async), Apollo, Lusha, Cognism (best for EU mobiles, enterprise priced). Add them after reading the current API docs; do not copy endpoints from memory.

## Mock-only tested

No live keys were available when the engine was written. The waterfall logic is tested offline with mocked providers; the HTTP adapters are written to the docs above but have **not** been run against the live APIs. First real run: use `--limit 10`.
