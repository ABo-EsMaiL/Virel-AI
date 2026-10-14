# Client inputs

Examples describe HTTP shapes, not a requirement to add custom client code. Native n8n operations must work without a Code or replacement HTTP Request node.

## Text: existing Chat adapter

```json
{"messages":[{"role":"user","content":"Hello"}],"stream":false}
```

POST `/v1/chat/completions`; text is `choices[0].message.content`. `model` must correspond to a real UI model. The catalog advertises only the current verified UI selection. Missing stream defaults to JSON.

## Images: preparation exists; native acceptance pending

```json
{"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,<bytes>"}},{"type":"text","text":"Describe this image"}]}],"stream":false}
```

Image-only removes the text part. URL/base64/binary paths, validation and native image-only acceptance belong to the vision stage. Arbitrary local paths are an inherited unsafe input behavior, not a client integration technique.

## PDF and other media: planned

Native n8n Model Response can accept a File message from binary data or a File ID. File upload, IDs and lifecycle must be implemented in Virel AI before this workflow works. See [n8n text operations](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-langchain.openai/text-operations/) and [file operations](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-langchain.openai/file-operations/).

| Capability | Native operation to verify |
|---|---|
| Image input | Analyze Image or an Image message |
| PDF | Model Response File message / Upload a File |
| Audio input | Transcribe / Translate |
| Video input | A client operation exposing video input; verify availability first |
| Image/audio/video output | Corresponding generation/edit operation with real artifacts |
| Tools | Tool calls, execution by the client, and correlated tool results |

Google Search grounding is not a client filesystem tool call. Each modality requires actual UI/model support and native acceptance tests.

## n8n in Docker

On Docker Desktop, use `http://host.docker.internal:8001/v1` when Virel AI runs on the host and listens on a reachable interface. Container localhost points to the container. Credential fields and node parameters must be verified against the installed version.

## Verified n8n text setup

Native OpenAI 1.8: Text / Message, model by ID, Messages → user/text. Native OpenAI 2.3: Text / Model Response, Messages → Text/user. Raw and Simplify Output modes passed. Use the ordinary OpenAI credential with the gateway key and Docker host Base URL above. Keep all experiments in **Virel AI - Native text smoke**. [Results and limitations](../specs/002-n8n-text/evidence.md).
