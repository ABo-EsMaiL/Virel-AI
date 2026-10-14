# Virel AI

[![Checks](https://github.com/ABo-EsMaiL/Virel-AI/actions/workflows/checks.yml/badge.svg)](https://github.com/ABo-EsMaiL/Virel-AI/actions/workflows/checks.yml)

**A browser-backed AI gateway, starting with Google AI Studio.**

Virel AI accepts HTTP requests, submits them through Chromium, reads the visible response, and returns JSON or SSE. Generation uses the website's interface; the gateway key authenticates your clients, not Google API requests.

```text
Client → Virel AI → Playwright / Chromium → AI Studio
```

## Status

Early development. Native n8n Chat and Responses text operations pass in raw and simplified modes, with reported request token usage. [Acceptance evidence](specs/002-n8n-text/evidence.md). Image preparation and inherited SSE adapters exist; isolated sessions, full streaming protocols and additional media capabilities remain staged work.

## Quick start

Python 3.12 and an account that can access AI Studio are required.

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

Set `VIREL_API_KEY`, an available `DEFAULT_MODEL`, and `CHROME_PROFILE_DIR` in `.env`. To prepare a new Google login, run `python get_session.py`. To reuse an existing profile, set its absolute path and close other processes using it.

```powershell
uvicorn app:app --host 127.0.0.1 --port 8001
```

**Base URL:** `http://localhost:8001/v1` · **Auth:** `Authorization: Bearer <VIREL_API_KEY>`

```json
{
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": false
}
```

POST to `/v1/chat/completions`; read `choices[0].message.content`. Use one worker. Docker clients need a reachable host address; see the [integration guide](docs/client-inputs.md).

## Development

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The project uses [GitHub Spec Kit](https://github.com/github/spec-kit), feature branches and regression checks. Private profiles, `.env` and runtime files are excluded from Git. UI changes, account limits and inherited protocol/security gaps still apply; see the [foundation report](docs/foundation-report.md).

[Architecture](docs/architecture.md) · [Roadmap](tasks/plan.md) · [Inputs](docs/client-inputs.md) · [Token usage](docs/usage.md) · [Contributing instructions](AGENTS.md)

## License

[MIT](LICENSE). Original attribution is preserved.
