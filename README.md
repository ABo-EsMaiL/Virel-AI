# Virel AI

**A browser-backed AI gateway for Google AI Studio.**

Virel AI accepts HTTP requests, submits them through Chromium, reads the visible response, and returns JSON or SSE. The gateway key authenticates your clients; generation uses the website interface.

## Quick start

Python 3.12 and an account with access to AI Studio are required.

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

Set `VIREL_API_KEY`, `DEFAULT_MODEL`, and `CHROME_PROFILE_DIR` in `.env`. The verified setup uses `HEADLESS=false`. Run `python get_session.py` for a new Google login, or reuse an existing profile after closing other processes using it.

```powershell
uvicorn app:app --host 127.0.0.1 --port 8001
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

Native n8n OpenAI Chat 1.8 and Responses 2.3 text passed in raw and simplified modes. Sessions/history, full streaming protocols, media and tools remain staged work. AI Studio changes and account limits can affect generation.

## License

[MIT](LICENSE). Original attribution is preserved.
