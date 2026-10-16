# Virel AI

**A browser-backed AI gateway for Google AI Studio.**

Virel AI accepts HTTP requests, submits them through Chromium, reads the visible response, and returns JSON, SSE or supported media files. The gateway key authenticates your clients; generation uses the website interface.

## Quick start

Python 3.12 and an account with access to AI Studio are required.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m playwright install chromium
Copy-Item .env.example .env
```

Set `VIREL_API_KEY`, `DEFAULT_MODEL`, and `CHROME_PROFILE_DIR` in `.env`. The verified setup uses `HEADLESS=false`. Run `./.venv/Scripts/python.exe get_session.py` for a new Google login, or reuse an existing profile after closing other processes using it.

```powershell
./.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001
```

Use one worker. For n8n in Docker Desktop, listen on `0.0.0.0` and set its ordinary OpenAI credential Base URL to `http://host.docker.internal:8001/v1` with your gateway key.

## Model selection

GET /v1/models returns the last account-UI observation of selectable text, image and speech model IDs. The ordinary n8n model picker uses those IDs directly. Paid, disabled and unimplemented output categories are excluded; each route checks the model category. Unknown capability fields remain null; appearing in the list does not guarantee quota or every modality.

Send the exact model ID in a request. Virel verifies the browser selection before submitting; it never falls back to another model. Unknown IDs return404, unavailable selections503, unsupported categories400. Responses disclose actual model and requested_model separately when a UI alias resolves to a concrete model. The documented audio whisper-1 compatibility alias remains unchanged.

Authenticated GET /v1/models?refresh=true rescans the UI while idle; a busy browser returns429. Ordinary listing reads the snapshot without interrupting generation. Discovery metadata includes observed_at and process-local generation_verified; model-specific thinking/search verification is cleared when controls are absent.

## Text request

POST `/v1/chat/completions` with `Authorization: Bearer <VIREL_API_KEY>`:

```json
{
  "messages": [{"role": "user", "content": "Hello"}]
}
```

Read `choices[0].message.content`. Missing `stream` returns JSON; explicit `stream: true` uses the inherited SSE adapter. Responses text uses POST `/v1/responses` with `{"input":"Hello"}`. Reported usage is returned when observed; unavailable counts remain null.

Native n8n OpenAI Chat 1.8 and Responses 2.3 text passed in raw and simplified modes. Clients own memory: send the complete ordered text history with each request. Virel replays it once in a verified fresh browser chat; validated tool-result continuations reuse that chat until the agent finishes. It does not store conversations. History is a text transcript, not native provider role enforcement. Full streaming protocols and video output remain staged work. AI Studio changes and account limits can affect generation.

## Client tools and agents

Chat Completions and Responses accept client-owned `type:function` tools with `stream:false`. AI Studio receives one real native relay function, `virel_client_tools`, whose array carries the requested original tool names and JSON arguments. Virel validates each against the caller schema and returns standard `tool_calls` / `function_call` items. Client results return together as one native function response in the same browser chat. `X-Virel-Tool-Transport: native_function_batch` discloses this mapping. Your client executes every tool; Virel never runs them. Structured Outputs is not used for this transport.

Use native n8n AI Agent + OpenAI Chat Model + Calculator with agent streaming disabled. Send complete ordered history and original call IDs with each result. The first request starts a fresh browser chat; matching results are added together to that same chat without replaying history or tool definitions. Further tool rounds stay there until the final answer. The next execution starts fresh. A fresh tool request using the same gateway credential supersedes that credential's older waiting round; late results from the older round are rejected without replaying tools. This does not cancel actions already running in your client. No extra client node, header or n8n patch is needed.

One browser supports one active tool loop. While awaiting results, unrelated generations return `429 tool_run_busy`. Idle timeout defaults to600seconds (`VIREL_TOOL_RUN_TTL_SECONDS`); restart, expiry, changed caller/conversational history/settings or stale IDs return409 rather than silently replaying work. System/developer instruction content may refresh between matching rounds (for example a dynamic clock); the latest instructions are forwarded separately from opaque tool outputs. Instruction roles and positions remain bound. Concurrent executions sharing one credential can supersede each other while waiting; parallel agents require separate browser capacity. Only hashes/call metadata are retained in memory, with no conversation database. Same-chat reuse does not guarantee lower token usage: the website still processes effective context.

There is no fixed gateway count of tool definitions or calls per response. The configured request-byte limit (128MiB by default),32KiB/schema,64KiB arguments,24 nesting levels and actual model/context/output limits still apply. `parallel_tool_calls:false` permits at most one call. Choices `auto`, `none`, `required` and a declared named function are validated; constrained argument decoding is not promised. Schemas support typed objects/properties/required, arrays, enum and numeric/size bounds. Refs, patterns/composition, `strict:true`, built-in tools, tool streaming and media/tool combinations are unsupported. The observed AI Studio UI makes native Function calling incompatible with Google Search and URL Context. These are disabled while client functions are available and restored for ordinary requests or `tool_choice:none`. Search runs within Google, not as a gateway tool executor. This UI restriction prevents combined search-and-client-tool requests; Gemini API capabilities do not certify UI availability. The n8n Responses logger may show its own token estimate; HTTP `usage` retains website-reported counts or null. Explicit model IDs select their exact UI card even when a selected alias points to the same canonical model. Temporary model-unavailable errors return `503 upstream_unavailable`; the gateway does not change models or retry generation automatically.

## Image input

Chat user messages accept text and image parts together:

```json
{"messages":[{"role":"user","content":[
  {"type":"text","text":"Describe the animal."},
  {"type":"image_url","image_url":{"url":"https://upload.wikimedia.org/wikipedia/commons/9/9a/Gull_portrait_ca_usa.jpg"}}
]}]}
```

Omit the text part for a default image description. Responses uses `input_image` with a string `image_url`. Both accept PNG/JPEG/WebP base64 data URIs or public HTTPS URLs. Limits: 4 still images, 5 MiB and 20 million pixels each; 128 MiB request body by default. Local paths, redirects, private destinations, image file IDs and non-default detail are rejected. Request upload files are removed afterward.

Native n8n **Message a Model 2.3** passed with binary and URL images. Add text and image entries in the same node to send one request. It requires text, so use a neutral description for a picture without a custom question. **Analyze Image** remains unsupported because its automatic output-token limit is not controlled by the browser adapter. Optional UI response comparisons are skipped without voting; ambiguous usage remains null.

## Image generation and editing

Native n8n **Generate an Image** returns the actual PNG as binary data. Choose By ID and use an available image model such as `gemini-3.1-flash-lite-image` (Nano Banana 2 Lite). POST `/v1/images/generations` accepts:

```json
{"model":"gemini-3.1-flash-lite-image","prompt":"A red circle on white"}
```

Native **Edit an Image** accepts the original binary directly. Select `gpt-image-1`, Size=Auto and Quality=Auto. This is an explicit Virel compatibility selector for `DEFAULT_IMAGE_MODEL`, not GPT execution: n8n 2.3 hides the necessary edit input fields for Gemini IDs. Direct HTTP callers can use the actual Gemini ID with multipart `image` or `image[]` and `prompt` at `/v1/images/edits`.

Both return one image in `data[0].b64_json`, actual/requested model metadata and reported usage when available. Omit `output_format` (or use `auto`) to preserve the original model file byte-for-byte. Explicit `png`, `jpeg` or `webp` requests convert the final file on the server; `encoding` discloses original/output formats and whether conversion occurred. JPEG conversion uses quality100/no chroma subsampling by default; WebP defaults to lossless. Optional `output_compression`0–100 selects JPEG/WebP encoding quality. Transparent source pixels become white only when explicitly converting to JPEG.

| Option | Default and behavior |
|---|---|
| Text model / image model | `DEFAULT_MODEL=gemini-flash-latest` (observed UI alias); `DEFAULT_IMAGE_MODEL` is an eligible observed image model. Explicit model wins; no paid fallback. |
| Thinking / temperature | `high` / `1`; HTTP image `reasoning_effort` and `temperature` override them when the selected UI model supports the values. |
| Shape / resolution | `size=auto`, `aspect_ratio=Auto`, `resolution=1K`; offered ratios are verified in the UI. `size=1024x1024` enforces1:1/1K and actual1024square bytes. Lite exposes1K only. |
| Advanced image controls | HTTP `top_p` defaults0.95; `max_output_tokens` defaults65536, capped by the current UI maximum. Explicit values must pass real UI bounds/readback. |
| Original/output format | Default `auto` preserves the source. Explicit PNG/JPEG/WebP conversion uses existing Pillow; generation remains in AI Studio. |
| Output limits | One image, base64/native binary;20MiB output (`VIREL_MAX_GENERATED_IMAGE_MB`),20million pixels; edit-input limits above. |

HTTP example: `{"prompt":"A kite above a green hill","aspect_ratio":"16:9","temperature":0.4,"reasoning_effort":"minimal","output_format":"jpeg"}`. Image extensions not exposed by a native node require a client that actually sends them. Existing native n8n Generate/Edit work without conversion nodes.

The installed n8n OpenAI2.3 Edit serializer does not send its visible Output Format/Compression fields. Virel handles these standard fields when received; a missing field preserves the original. n8n itself is unchanged. Its Generate node also hides many options for Gemini IDs. Server behavior cannot infer an unsent client selection.

Quality tiers, pixel masks, guaranteed transparency, input fidelity, hosted output URLs, batches and arbitrary resized dimensions remain unavailable. They return field-specific errors with supported alternatives; quality is not silently mapped to resolution or thinking. AI Studio can refuse requests (recitation/safety), and available image models can lack Search/URL tools. Quota/rate-limit UI failures return429 with `upstream_rate_limit`; no automatic retries or stale/input image fallback.

## PDF input

Native n8n **Message a Model 2.3** accepts PDF file entries alongside a text question: use Binary File, public HTTPS URL, or File ID from the official **Upload a File** node. Scanned and ordinary PDFs are submitted as original documents through the same browser upload/readiness checks.

Responses file parts use one source:

```json
{"input":[{"role":"user","content":[
  {"type":"input_text","text":"Summarize this document."},
  {"type":"input_file","file_id":"file-<uploaded-id>"}
]}]}
```

Alternatively use file_url, or filename plus file_data containing strict base64/data:application/pdf;base64,... . Default gateway limits:10 PDFs per request,50 MiB and 1000 pages each;128 MiB request body. Configure VIREL_MAX_PDF_MB, VIREL_MAX_PDF_PAGES, VIREL_MAX_PDFS and VIREL_MAX_REQUEST_MB in .env. Encrypted or corrupt PDFs and unsafe URLs are rejected. These are gateway limits, not a guarantee of every model's support.

POST /v1/files accepts multipart file and purpose=user_data or assistants. Authenticated list/retrieve/content/delete endpoints are available. Files remain private to this gateway, expire after one hour and are cleaned every 60 seconds/startup; expired IDs fail immediately. Storage is bounded at 20 files/100 MiB. Configure VIREL_API_KEY to enable stored IDs; request copies are deleted afterward. PDF input does not implement File Search or vector stores.

## Generation controls

Native text requests accept temperature (0–2, subject to the selected UI model) and reasoning effort. Chat uses reasoning_effort; Responses uses reasoning.effort. Missing effort uses THINKING_MODE=high; missing temperature resets an available UI control to1. Unsupported explicit controls return an error before generation.

In the native n8n Responses node, add Reasoning → Effort and set Summary to None; add Temperature separately. No Code or conversion node is needed. Reasoning summaries are not implemented.

ENABLE_URL_CONTEXT=true enables the current model's URL Context tool for links in prompts, alongside Google Search when configured. /health reports actual thinking, temperature and URL-tool verification. Tool availability and URL retrieval still depend on AI Studio and the selected model.

## Video input

MP4 and WebM video questions work through the native n8n Responses File Data field: connect the binary file directly, set its filename and add your text question. Virel passes the original video into AI Studio after validation and waits for upload/tokenization readiness. No conversion node or local video model is used.

This is a Virel extension to input_file, not official OpenAI video compatibility. Chat file parts accept the same filename/file_data fields; identifiable direct public HTTPS file_url sources are also supported. Media-only HTTP requests get a description prompt; the native n8n node requires text. Stored video IDs, playlists, clipping and video generation are not implemented.

Defaults:50 MiB/video,2 videos/request,20 million pixels/frame; configure VIREL_MAX_VIDEO_MB, VIREL_MAX_VIDEOS and VIREL_MAX_VIDEO_PIXELS. There is no separate duration cap. The HTTP body cap includes base64 overhead; website/model limits still apply. Validation samples a real frame in a bounded child process; request files are removed on completion/error/cancellation. Native MP4/H.264 and WebM/VP9 passed; other encodings and live URL transport need separate acceptance.

## Audio input

Native n8n **Transcribe Audio** and **Translate Audio** operations work with ordinary OpenAI credentials pointed at Virel. Pass a binary audio file directly; transcription preserves the spoken language, translation returns English. Both use the AI Studio browser, not an external transcription service.

POST /v1/audio/transcriptions or /v1/audio/translations with multipart file and model. Native n8n hardcodes whisper-1: Virel accepts it as a compatibility alias for DEFAULT_MODEL. Responses expose actual model and requested_model; Virel does not run Whisper. JSON returns text and observed usage; response_format=text returns plain text. Language hints are prompt guidance. Explicit temperature, timestamps, streaming and subtitle formats are unsupported.

The validator accepts WAV, MP3/MPEG, M4A/audio-only MP4, OGG, FLAC and audio-only WebM containers, checks MIME/container consistency and decodes a sample before upload. WAV and MP3 passed through native n8n; other listed containers passed isolated decoder checks and still need browser acceptance for each encoding. Audio defaults to 25 MiB per file, configurable with VIREL_MAX_AUDIO_MB. There is no additional duration cap; website/model/context and processing deadlines still apply. Request files are removed on completion/error/cancellation. No stored-audio IDs are implemented.

Limits are positive gateway settings, not unlimited provider capacity. Raising them cannot override website/account/model limits; base64 also increases the request body size. PDF storage remains 20 files/100 MiB with one-hour expiry.

## Speech output

Native n8n **Generate Audio 2.3** returns real speech generated through AI Studio. POST `/v1/audio/speech`:

```json
{"model":"tts-1","input":"Hello from Virel AI.","voice":"alloy","response_format":"mp3","speed":1}
```

`tts-1` and `tts-1-hd` explicitly select `DEFAULT_SPEECH_MODEL=gemini-3.8-flash-tts`; both use the same actual model. These selectors do not run OpenAI TTS or promise an HD tier. Direct callers can send an eligible observed Gemini TTS ID. Actual/requested model and voice are disclosed in response headers.

| Native voice selector | Actual AI Studio voice |
|---|---|
| `alloy` | `DEFAULT_SPEECH_VOICE=Fola` |
| `echo` / `fable` / `nova` | Bodi / Koda / Lumi |
| `onyx` / `shimmer` | Mako / Sola |

These select Gemini voices, not reproductions of OpenAI voices. Direct callers can request an exact available UI voice name. Selection must be verified before Run; unavailable voices fail explicitly.

Omitted `response_format`/`auto` preserves the original PCM16 mono24kHz WAV byte-for-byte at speed1. Native n8n requests MP3 by default. Explicit `mp3`, `opus` (Ogg), `aac` (ADTS), `flac`, `wav` or `pcm` (raw signed16LE mono24kHz) produce matching files. Existing PyAV performs only requested file encoding and pitch-preserving `speed`0.25–4; speech synthesis stays in the browser. `X-Virel-Source-Format`, `X-Virel-Output-Format`, `X-Virel-Audio-Speed` and `X-Virel-Audio-Processing` disclose processing.

Defaults:4096input characters,50MiB source/output and600seconds source duration, configurable via `VIREL_MAX_SPEECH_CHARACTERS`, `VIREL_MAX_GENERATED_AUDIO_MB`, `VIREL_MAX_SPEECH_SECONDS`. A killable30second worker validates/encodes files; temporary files are removed on completion/error/cancellation. These limits cannot override AI Studio/account quotas. Reported counts use `X-Virel-Input-Tokens`, `X-Virel-Output-Tokens`, `X-Virel-Total-Tokens`; unavailable counts are omitted and provenance headers say unavailable/unknown. Streaming, instructions/style parameters, voice cloning, multiple speakers and text-model thinking/Search controls are unsupported by this route. No n8n patch or local TTS model is required.

## License

[MIT](LICENSE). Original attribution is preserved.
