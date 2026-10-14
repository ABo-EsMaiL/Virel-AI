"""Offline contract checks: no Google account, uploads, or real prompts required."""

import asyncio
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from playwright.async_api import async_playwright

import app as gateway
from virel import auth, config, messages, runtime
from virel.schemas import ChatMessage
from virel.dom import FETCH_RESPONSE_STATE


class GatewayTests(unittest.TestCase):
    def setUp(self):
        # Without a context manager, TestClient does not start the Google browser.
        self.client = TestClient(gateway.app)
        self.key_patch = patch.object(auth, "API_KEY", "test-key")
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer test-key"}
        self.calls = []

        async def fake_stream(prompt, **kwargs):
            self.calls.append((prompt, kwargs))
            yield {"delta": "أهلاً", "text": "أهلاً"}
            yield {"delta": " بيك", "text": "أهلاً بيك"}
            yield {"delta": "", "text": "أهلاً بيك"}

        self.stream_patch = patch.object(runtime.browser_manager, "send_prompt_and_stream", fake_stream)
        self.stream_patch.start()
        self.addCleanup(self.stream_patch.stop)
        runtime._semaphore = None
        runtime.browser_manager.lock = asyncio.Lock()
        runtime.limiter.reset()

    def post(self, route, body, headers=None):
        return self.client.post(route, json=body, headers=self.headers if headers is None else headers)

    def test_authentication(self):
        body = {"messages": [{"role": "user", "content": "hello"}]}
        self.assertEqual(self.post("/v1/chat/completions", body, {}).status_code, 401)
        self.assertEqual(self.post("/v1/chat/completions", body, {"Authorization": "Bearer wrong"}).status_code, 401)
        self.assertEqual(self.calls, [])

    def test_invalid_chat_body_is_rejected(self):
        self.assertEqual(self.post("/v1/chat/completions", {}).status_code, 422)
        self.assertEqual(self.calls, [])

    def test_empty_gateway_key_disables_auth_only(self):
        with patch.object(auth, "API_KEY", ""):
            response = self.post("/v1/chat/completions", {"messages": [{"role": "user", "content": "hello"}], "stream": False}, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls[-1][0], "hello")

    def test_chat_json_and_headers(self):
        headers = dict(self.headers, **{"x-batch-size": "3", "x-enable-search": "true"})
        response = self.post("/v1/chat/completions", {"model": "gemini-test", "messages": [{"role": "user", "content": "hello"}], "stream": False}, headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["choices"][0]["message"]["content"], "أهلاً بيك")
        self.assertEqual(response.json()["model"], "gemini-test")
        prompt, options = self.calls[0]
        self.assertEqual(prompt, "hello")
        self.assertEqual((options["model_name"], options["batch_size"], options["enable_search"]), ("gemini-test", 3, True))

    def test_chat_sse(self):
        response = self.post("/v1/chat/completions", {"messages": [{"role": "user", "content": "hello"}], "stream": True})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        events = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertEqual(events[-1], "[DONE]")
        chunks = [json.loads(event) for event in events[:-1]]
        self.assertEqual(chunks[0]["choices"][0]["delta"]["role"], "assistant")
        self.assertEqual("".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks), "أهلاً بيك")
        self.assertEqual(chunks[-1]["choices"][0]["finish_reason"], "stop")

    def test_busy_chat_returns_429(self):
        semaphore = asyncio.Semaphore(1)
        asyncio.run(semaphore.acquire())
        with patch.object(runtime, "_semaphore", semaphore):
            response = self.post("/v1/chat/completions", {"messages": []})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.calls, [])

    def test_busy_responses_routes_return_429(self):
        semaphore = asyncio.Semaphore(1)
        asyncio.run(semaphore.acquire())
        with patch.object(runtime, "_semaphore", semaphore):
            for route in ("/v1/responses", "/responses"):
                self.assertEqual(self.post(route, {"input": "hello"}).status_code, 429)
        self.assertEqual(self.calls, [])

    def test_login_setup_and_server_use_same_profile(self):
        import get_session
        self.assertEqual(get_session.CHROME_PROFILE_DIR, config.CHROME_PROFILE_DIR)
        self.assertTrue(Path(get_session.CHROME_PROFILE_DIR).is_absolute())

    def test_response_routes(self):
        for route in ("/v1/responses", "/responses"):
            with self.subTest(route=route):
                response = self.post(route, {"input": "hello", "instructions": "بالمصري", "stream": False})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["output_text"], "أهلاً بيك")
                self.assertEqual(self.calls[-1][0], "[System Instructions]\nبالمصري\n\nhello")

    def test_responses_current_sse_contract(self):
        response = self.post("/v1/responses", {"input": "hello", "stream": True})
        self.assertIn('"object": "response.chunk"', response.text)
        self.assertIn('"object": "response.done"', response.text)
        self.assertTrue(response.text.endswith("data: [DONE]\n\n"))

    def test_legacy_completion(self):
        response = self.post("/v1/completions", {"prompt": ["hello", "world"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["choices"][0]["text"], "أهلاً بيك")
        self.assertEqual(self.calls[-1][0], "hello world")

    def test_health_without_browser(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["gateway"], "Virel (AIStudio Web Hook)")

    def test_models_have_no_chatgpt_leftovers(self):
        response = self.client.get("/v1/models", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(item["id"].startswith("gemini-") for item in response.json()["data"]))

    def test_prompt_conversion_preserves_current_contract(self):
        prompt, images = messages.extract_prompt_and_images([
            ChatMessage(role="system", content="القواعد"),
            ChatMessage(role="assistant", content="رد قديم"),
            ChatMessage(role="user", content="<thought>سر</thought> السؤال"),
        ])
        self.assertEqual(prompt, "[System Instructions]\nالقواعد\n\nالسؤال")
        self.assertEqual(images, [])

    def test_base64_image_written_into_temporary_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(messages, "TEMP_UPLOADS_DIR", folder):
            data = b"image-fixture"
            prompt, images = messages.extract_prompt_and_images([ChatMessage(role="user", content=[
                {"type": "text", "text": "اقرأ الصورة"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(data).decode()}},
            ])])
            self.assertEqual(prompt, "اقرأ الصورة")
            self.assertEqual(len(images), 1)
            self.assertEqual(Path(images[0]).suffix, ".jpg")
            self.assertEqual(Path(images[0]).read_bytes(), data)


class BrowserExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_button_fallback_without_primary_selector(self):
        script = FETCH_RESPONSE_STATE
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content('<button class="primary">Run</button>')
                state = await page.evaluate(script, 0)
                self.assertFalse(state["is_running"])
                await page.set_content('<button aria-label="Cancel generation">Stop</button>')
                state = await page.evaluate(script, 0)
                self.assertTrue(state["is_running"])
                await page.set_content('<div>No button</div>')
                state = await page.evaluate(script, 0)
                self.assertFalse(state["is_running"])
                await page.set_content('''
                    <ms-chat-turn><div class="user-prompt-container">السؤال</div></ms-chat-turn>
                    <ms-chat-turn><div class="model-prompt-container">
                        <ms-text-chunk>أهلاً<button>Copy</button></ms-text-chunk>
                        <ms-thought-chunk><ms-text-chunk>تفكير</ms-text-chunk></ms-thought-chunk>
                        <ms-code-block>print(1)</ms-code-block>
                    </div></ms-chat-turn>
                ''')
                state = await page.evaluate(script, 0)
                self.assertEqual(state["text"], "أهلاً\n\nprint(1)")
                self.assertTrue(state["new_model_turn_started"])
                self.assertTrue(await page.locator("button").is_visible())
                await page.set_content('''<ms-chat-turn>
                    <div class="model-prompt-container">Prohibited content</div>
                </ms-chat-turn>''')
                state = await page.evaluate(script, 0)
                self.assertTrue(state["has_error"])
                self.assertIn("CONTENT_BLOCKED", state["error_text"])
            finally:
                await browser.close()


if __name__ == "__main__":
    unittest.main()
