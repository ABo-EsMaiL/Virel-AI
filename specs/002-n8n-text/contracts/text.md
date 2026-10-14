# Text contracts

Chat: POST /v1/chat/completions, Bearer key, one nonempty user prompt, optional available model. Missing stream returns JSON. Success: choices[0].message.content; reported usage or null/unavailable provenance. Explicit stream retains Chat SSE.

Responses: POST /v1/responses or /responses. String or text message input; instructions may precede the prompt. Success: completed assistant output containing output_text and annotations, plus output_text convenience field. No tools/files/conversations claimed.

Common errors: structured error.message/type/code; 401 auth, 400/422 bad input or unsupported capability, 429 admission/rate limit, 503 not ready/model unavailable, 502 upstream error, 504 timeout. Once streaming headers have been sent, emit an error event rather than claiming a successful completion.

System: health remains readable; sensitive diagnostics/shutdown use gateway auth. Credentials test GET /v1/models with the configured key.
