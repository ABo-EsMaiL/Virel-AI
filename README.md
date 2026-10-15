# Virel AI

**A browser-backed AI gateway for Google AI Studio.**

Virel AI accepts HTTP requests, submits them through Chromium, reads the visible response, and returns JSON or SSE. The gateway key authenticates your clients; generation uses the website interface.

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

## Text request

POST `/v1/chat/completions` with `Authorization: Bearer <VIREL_API_KEY>`:

```json
{
  "messages": [{"role": "user", "content": "Hello"}]
}
```

Read `choices[0].message.content`. Missing `stream` returns JSON; explicit `stream: true` uses the inherited SSE adapter. Responses text uses POST `/v1/responses` with `{"input":"Hello"}`. Reported usage is returned when observed; unavailable counts remain null.

Native n8n OpenAI Chat 1.8 and Responses 2.3 text passed in raw and simplified modes. Clients own memory: send the complete ordered text history with each request. Virel replays it once in a verified fresh browser chat; it does not store conversations. History is a text transcript, not native provider role enforcement. Full streaming protocols, video, audio output, image generation and tools remain staged work. AI Studio changes and account limits can affect generation.

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

## Audio input

Native n8n **Transcribe Audio** and **Translate Audio** operations work with ordinary OpenAI credentials pointed at Virel. Pass a binary audio file directly; transcription preserves the spoken language, translation returns English. Both use the AI Studio browser, not an external transcription service.

POST /v1/audio/transcriptions or /v1/audio/translations with multipart file and model. Native n8n hardcodes whisper-1: Virel accepts it as a compatibility alias for DEFAULT_MODEL. Responses expose actual model and requested_model; Virel does not run Whisper. JSON returns text and observed usage; response_format=text returns plain text. Language hints are prompt guidance. Explicit temperature, timestamps, streaming and subtitle formats are unsupported.

The validator accepts WAV, MP3/MPEG, M4A/audio-only MP4, OGG, FLAC and audio-only WebM containers, checks MIME/container consistency and decodes a sample before upload. WAV and MP3 passed through native n8n; other listed containers passed isolated decoder checks and still need browser acceptance for each encoding. Audio defaults to 25 MiB per file, configurable with VIREL_MAX_AUDIO_MB. There is no additional duration cap; website/model/context and processing deadlines still apply. Request files are removed on completion/error/cancellation. No stored-audio IDs or audio generation are implemented.

Limits are positive gateway settings, not unlimited provider capacity. Raising them cannot override website/account/model limits; base64 also increases the request body size. PDF storage remains 20 files/100 MiB with one-hour expiry.

## License

[MIT](LICENSE). Original attribution is preserved.
