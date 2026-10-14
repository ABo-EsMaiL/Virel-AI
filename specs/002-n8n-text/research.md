# Research

- n8n image version: 2.41.4; public credential type `openAiApi` uses `apiKey` and `url`, tests `GET /models`, and adds Bearer authentication. Verified against the installed credential source.
- Native OpenAI node type: `@n8n/n8n-nodes-langchain.openAi`. Versions through 1.8 support `resource=text, operation=message` and POST `/chat/completions`; the request does not explicitly set stream. Current 2.3 uses `operation=response` and POST `/responses`; using the old operation on v2 is invalid.
- The v1 operation accumulates usage only when a usage object exists; otherwise it can return text. v2 consumes assistant `output` messages and official `output_text` content.
- The existing Chat default is stream=true, causing the native JSON operation to receive SSE. Fix the default, retain explicit SSE tests.
- The authorized existing Google profile reaches a visible prompt without a login redirect. The UI heading says Gemini 3.8 Flash; inherited selector logic does not verify it because the settings panel is collapsed and label normalization differs. Use visible heading evidence for the selected default; full routing remains stage 007.
- Tokens are currently word counts in Responses. Inspect generation-associated browser metadata before choosing a parser; absence is reported honestly. No direct Google SDK/API counting dependency.
- Native operations are invoked with n8n's installed server CLI using isolated new credential/workflow IDs. Do not overwrite existing entries or publish autonomous workflows.

Sources: [n8n CLI](https://docs.n8n.io/hosting/cli-commands/), [OpenAI credential](https://docs.n8n.io/integrations/builtin/credentials/openai/), installed credential/operation files, isolated browser readiness probe.
