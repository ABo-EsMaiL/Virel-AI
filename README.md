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

Native n8n OpenAI Chat 1.8 and Responses 2.3 text passed in raw and simplified modes. Clients own memory: send the complete ordered text history with each request. Virel replays it once in a verified fresh browser chat; it does not store conversations. History is a text transcript, not native provider role enforcement. Full streaming protocols, PDFs/audio/video, image generation and tools remain staged work. AI Studio changes and account limits can affect generation.

## Image input

Chat user messages accept text and image parts together:

```json
{"messages":[{"role":"user","content":[
  {"type":"text","text":"Describe the animal."},
  {"type":"image_url","image_url":{"url":"https://upload.wikimedia.org/wikipedia/commons/9/9a/Gull_portrait_ca_usa.jpg"}}
]}]}
```

Omit the text part for a default image description. Responses uses `input_image` with a string `image_url`. Both accept PNG/JPEG/WebP base64 data URIs or public HTTPS URLs. Limits: 4 still images, 5 MiB and 20 million pixels each; 32 MiB request body. Local paths, redirects, private destinations, file IDs and non-default detail are rejected. Request upload files are removed afterward.

Native n8n **Message a Model 2.3** passed with binary and URL images. Add text and image entries in the same node to send one request. It requires text, so use a neutral description for a picture without a custom question. **Analyze Image** remains unsupported because its automatic output-token limit is not controlled by the browser adapter. Optional UI response comparisons are skipped without voting; ambiguous usage remains null.

## License

[MIT](LICENSE). Original attribution is preserved.
