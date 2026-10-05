---
name: generate
description: Generate images and videos via AI model APIs. Triggers on /generate, generate image, generate video, create image, thumbnail, animate.
---

# /generate

Routes every media request to the cheapest capable model, saves the output flat into one folder, and logs how it was made.

Pipeline: **Route** (pick model + provider, read its recipe) -> **Prep refs** (load real reference files) -> **Generate** (call API, poll if async) -> **Log** (sidecar JSON).

## Models

| Task | Default model | Recipe |
|---|---|---|
| Image (default) | Nano Banana 2 Lite | models/nano-banana-2-lite.md |
| Video (default) | Kling 3.0 | models/kling-3.md |

Add a row here plus one recipe file in `models/` whenever a new model is wired up. Candidates not yet wired: Nano Banana 2 (quality images), GPT Image 2 (text inside images, via fal.ai), Veo 3.1 (hero video from a start frame), Seedance 2.0 Fast (reference-to-video, via fal.ai).

Read the recipe file before every generation.

## Keys

Read keys from `.env` in the repo root (`GOOGLE_API_KEY`, `KIE_API_KEY`, `FAL_KEY`, `WAVESPEED_API_KEY`). Never paste keys into code, commands that get logged, or chat. If a needed key is empty, stop and tell me which one.

## Provider routing

1. Default to the LOWEST COST provider that runs the model well (check Kie AI, fal.ai, WaveSpeed AI).
2. If the cheapest route lacks the model, fails auth, or errors, fall back to the next provider.
3. Never hide a provider swap. Say which route ran and why.

Auth differs per provider: Google AI Studio takes the key in the URL (`?key=`), fal.ai uses `Authorization: Key {KEY}`, Kie AI uses `Authorization: Bearer {KEY}`.

## Output

- Save every file FLAT into `/Users/dsantoso/git/claude/generations/`.
- No subfolders. Reference images live in `generations/refs/`.
- Naming: `{project}_{description}_{timestamp}.{ext}` (timestamp = unix seconds).
- Async jobs: download the result immediately, URLs often expire within hours.

## Rules

- Quote the cost and wait for my explicit go before any paid video run. Quoting alone is not approval. One approval = one run.
- Draft on the cheap image model first. Only rerun on a quality model when I pick a favourite.
- Never describe a logo or face in text. Pass the real image file as a reference. If it's missing, stop and ask me for it.
- Run multiple generations one at a time to avoid rate limits.
- After every save, write the sidecar log (see Logging).

## Logging

Next to every saved file, write a JSON file with the same basename and a `.json` extension:

```json
{
  "model": "gemini-3.1-flash-lite-image",
  "provider": "Google AI Studio",
  "prompt": "the full text prompt that was sent to the API",
  "refs": ["refs/logo.png"],
  "params": { "aspect": "16:9", "size": "1K" },
  "created": "2026-07-30T09:41:00Z"
}
```

## Maintenance

Model ids change when providers ship new versions. On a "model not found" error, open the provider's model page, copy the id fresh, and update the recipe file.
