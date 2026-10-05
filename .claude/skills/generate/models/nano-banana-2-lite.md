# Nano Banana 2 Lite

Cheap, fast image model with good reference-image support. The default for drafts and everyday images.

| Field | Value |
|---|---|
| Model ID | `gemini-3.1-flash-lite-image` (full Nano Banana 2: `gemini-3.1-flash-image`, Pro: `gemini-3-pro-image`) |
| Provider | Google AI Studio (also hosted on fal.ai as a fallback) |
| Method | Sync (instant reply) |
| Type | Image |
| API key | .env -> GOOGLE_API_KEY |
| Docs | https://ai.google.dev/gemini-api/docs/image-generation |
| Cost | about $0.034 per 1K image (guide ballpark, check Google's pricing page) |

Checked against ai.google.dev on 2026-10-05. The docs now only show the Interactions API, so that is the primary route below. The older `generateContent` route is a fallback that I could not confirm in the docs.

## Endpoint (Interactions API)

```
POST https://generativelanguage.googleapis.com/v1beta/interactions
x-goog-api-key: $GOOGLE_API_KEY
Content-Type: application/json
```

Auth is a header, so the key stays out of the URL.

## Request format

```json
{
  "model": "gemini-3.1-flash-lite-image",
  "input": [
    { "type": "text", "text": "the full prompt" },
    { "type": "image", "mime_type": "image/png", "data": "<base64 of ref image>" }
  ],
  "response_format": {
    "type": "image",
    "mime_type": "image/jpeg",
    "aspect_ratio": "16:9",
    "image_size": "1K"
  }
}
```

Add one `{"type": "image", ...}` block per reference image (real files from `generations/refs/`). Omit them for text-only prompts. Field names are snake_case. Aspect ratios include `1:1`, `3:2`, `16:9`, `4:3`, `5:4`, `9:16`, `21:9`. `image_size` values seen in docs: `1K`, `2K`.

## Response handling

Verified live on 2026-10-05 (HTTP 200, `status: completed`). The docs' `output_image.data` path is wrong for the raw REST response. The image is in the `steps` array:

```
steps[] where type == "model_output"  ->  content[] where type == "image"  ->  .data (base64), .mime_type
```

A `thought` step may come first, so find the step by type, not index. Decode and save using the returned `mime_type` (jpg or png). If no image content is present, print the step types and any text content, it is usually a refusal reason.

## Fallback: classic generateContent (unverified)

```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-image:generateContent
x-goog-api-key: $GOOGLE_API_KEY
{ "contents": [{ "parts": [ {"text": "..."}, {"inline_data": {"mime_type": "image/png", "data": "<b64>"}} ]}],
  "generationConfig": { "responseModalities": ["IMAGE"], "imageConfig": { "aspectRatio": "16:9" } } }
```

Image comes back at `candidates[0].content.parts[*].inlineData.data`. Only use if the Interactions call fails, and tell me which route ran.

## Notes

- Request body above was tested as written with no refs. The reference-image `input` block is still untested.
- Rate limits: run generations one at a time.
- Text rendered inside images is weak, use GPT Image 2 for that (not yet wired).
