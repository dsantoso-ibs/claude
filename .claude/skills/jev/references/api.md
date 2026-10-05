# TypeSafe / Jev API quick reference

Source: https://docs.typesafe.ai/api.md and /models.md (read 5 Oct 2026). If anything here disagrees with the live docs, the live docs win.

## Endpoint

```
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

`GET https://api.typesafe.ai/v1/models` lists the model names the key can use.

## Request

```json
{
  "state": "text, or an object/array of named fields",
  "model": "jev-latest",
  "questions": {
    "any_id_you_choose": { "type": "choice | score | noul", "instructions": "...", "criteria": "..." }
  }
}
```

- `state`: string, object or array. Named fields are best when there are several parts.
- `model`: `jev-latest` and `jev-preview` are aliases for `jev-1.13.0` (currently identical). Aliases move when a new version ships; **pin `jev-1.13.0`** once you've tuned thresholds. The response `model` field tells you which version answered.
- Question ids are for your code only; they are not sent to the model. Put the full meaning in `instructions`.
- `instructions` can be a string, object or array. Put the question in one field and data in others, and refer to fields in backticks: `{"candidate": {...}, "question": "Is this the same person as `candidate`?"}`. In `state`, refer to nested values like `` `ticket.messages[0].text` ``.

### Question types

| type | `criteria` | notes |
|---|---|---|
| `noul` | optional `{"true": "...", "false": "..."}` | yes/no |
| `choice` | **required** map `option -> description (or null)`, max 255 options | one option wins; Jev leans slightly to the first option |
| `score` | **required** ordered array of level descriptions, 2 to 10 levels | level 0 = first entry |

## Response

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "department": {"type": "choice", "choice": "billing",
                   "probabilities": {"billing": 0.88, "technical": 0.12, "sales": 0.0}, "confidence": 0.81},
    "frustration": {"type": "score", "score": 1.05, "legend": {"0": "Calm", "1": "Frustrated", "2": "Very angry"},
                    "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05}, "confidence": 0.92},
    "is_urgent": {"type": "noul", "noul": 0.95}
  },
  "usage": {"input_tokens": 296, "output_tokens": 20}
}
```

## Confidence

- `choice`: `(p_max - 1/n) / (1 - 1/n)`. 1 = all probability on one option, 0 = even split.
- `score`: 1 minus the probability-weighted average distance from the peak level, relative to an even spread. Probability on neighbouring levels costs less than on distant levels.
- `noul`: no confidence field. Use distance from 0.5: `|2p - 1|`.
- Thresholds scale with risk: read-only/recoverable actions can use a low bar, destructive or expensive ones a high bar. Validate on your own data.

## Limits and price (jev-1.13.0)

- $0.042 per 1M input tokens, output free.
- 64k tokens per request; 32k for `state` plus the single longest question.
- Rate limits at last check: 100k tokens/s and 80 requests/s. These adjust dynamically.
- Text only. English best.

## Errors

| Status | Meaning | Action |
|---|---|---|
| 401 | missing/invalid key | check the key; it must be a TypeSafe key |
| 422 | validation failed; body names the field | fix the question |
| 429 | rate limited | exponential backoff, honour `retry-after` |
| 529 | overloaded | backoff and retry |

## Known weak spots of jev-1.13 (TypeSafe's own list)

Literal reading of wording; arithmetic and counting; comparing dates; multi-hop indirection and double negatives; large state padded with irrelevant detail; adversarial text in the state; contradictory instructions vs criteria; option-order bias; text generation. Page: https://docs.typesafe.ai/model-jaggedness/jev-1.13.md

## Other documentation

- Index: https://docs.typesafe.ai/llms.txt (append `.md` to a page path for Markdown)
- Patterns: speculative fan-out, confidence-gated routing, composite scoring, intent routing
- Cookbooks include skill suggestion, reranking, classifying RAG passages, citation checks, guardrails
- SDKs: Python (`typesafe_sdk`) and JavaScript (`@typesafe-ai/sdk`); env var `TYPESAFE_API_KEY`
- Official build skill: `typesafe-ai/skills`
