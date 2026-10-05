# Kling 3.0

General-purpose video model. Good motion at a fair price. The default for video. PAID: always quote and wait for my explicit go first.

| Field | Value |
|---|---|
| Model ID | `kling-3.0/video` |
| Provider | Kie AI |
| Method | Async (submit, then poll) |
| Type | Video |
| API key | .env -> KIE_API_KEY |
| Docs | https://docs.kie.ai/market/kling/kling-3-0 and https://docs.kie.ai/market/common/get-task-detail |
| Cost | not in the docs, check kie.ai/pricing before quoting. Guide ballpark: $0.20 to $0.35 per second |

Field names verified against docs.kie.ai on 2026-10-05.

## Endpoint

```
POST https://api.kie.ai/api/v1/jobs/createTask
Authorization: Bearer $KIE_API_KEY
Content-Type: application/json
```

## Request format

```json
{
  "model": "kling-3.0/video",
  "input": {
    "prompt": "the full prompt",
    "sound": false,
    "duration": "5",
    "aspect_ratio": "16:9",
    "mode": "std",
    "multi_shots": false,
    "image_urls": ["https://public-url-of-first-frame"]
  }
}
```

- `sound`, `duration`, `aspect_ratio`, `mode`, `multi_shots` are all required by the docs. Send them every time.
- `duration` is a STRING, "3" to "15".
- `aspect_ratio`: `16:9`, `9:16`, `1:1` (optional when images are given).
- `mode`: `std` = 1280x720, `pro` = 1920x1080, `4K` = 3840x2160.
- `image_urls` is optional. One URL = first frame. Two URLs = first and last frame (only when `multi_shots` is false). URLs must be PUBLIC, see Uploading refs.
- Multi-shot: set `multi_shots: true` and pass `multi_prompt: [{"prompt": "...", "duration": 3}]` (up to 5 shots, 1 to 12 s each) instead of `prompt`. Only a first frame is allowed.
- `kling_elements` (named reference objects used as `@name` in the prompt) and `callBackUrl` exist but we don't use them. We poll.
- Sound costs more on most Kling tiers, default `sound` to false for drafts.

## Uploading refs

Local files must become public URLs first. Kie's upload service (same Bearer key):

```
POST https://kieai.redpandaai.co/api/file-base64-upload
{ "base64Data": "data:image/png;base64,....", "uploadPath": "images/generate", "fileName": "logo.png" }
```

(or `/api/file-stream-upload` with multipart `file`). The response has `fileUrl` / `downloadUrl`. Uploads are deleted after 24 hours.

## Response handling

1. POST returns `data.taskId`.
2. Poll `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId={taskId}` every 10 to 15 seconds.
3. `data.state` is one of `waiting`, `queuing`, `generating`, `success`, `fail`.
4. On `success`, `data.resultJson` is a JSON STRING: parse it, the video URL is `resultUrls[0]`.
5. On `fail`, report `data.failMsg` / `failCode` and stop. Do not retry without asking, retries cost money.
6. Download immediately, URLs expire in hours. Save flat into `generations/`, then write the sidecar log.

HTTP codes: 401 bad key, 404 task not found, 429 rate limited.

## Notes

- Never start a run without my explicit go on the quoted cost. One approval = one run.
- Fallback providers if Kie lacks the model or errors: fal.ai, then WaveSpeed AI (note the swap).
- Use `std` for drafts, `pro` only for finals.
