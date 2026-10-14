"""Native text and honest failure regressions; no live account required."""
import asyncio
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import app
from virel import auth, runtime


class TextContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer test-key"}
        for target, name, value in ((auth,"API_KEY","test-key"),(runtime.browser_manager,"is_ready",True)):
            replacement=patch.object(target,name,value)
            replacement.start();self.addCleanup(replacement.stop)
        runtime._semaphore=None
        runtime.browser_manager.lock=asyncio.Lock()
        runtime.limiter.reset()
        runtime.browser_manager.last_usage=None

    def stream(self, *items):
        async def fake(prompt, **kwargs):
            for item in items:yield item
        replacement=patch.object(runtime.browser_manager,"send_prompt_and_stream",fake)
        replacement.start();self.addCleanup(replacement.stop)

    def chat(self, **extra):
        return self.client.post('/v1/chat/completions',headers=self.headers,json={"messages":[{"role":"user","content":"hello"}],**extra})

    def test_native_chat_defaults_to_json(self):
        self.stream({"delta":"answer","text":"answer"})
        response=self.chat()
        self.assertEqual(response.headers['content-type'],'application/json')
        self.assertEqual(response.json()['choices'][0]['message']['content'],'answer')

    def test_native_responses_text_type_and_unknown_usage(self):
        self.stream({"delta":"answer","text":"answer"})
        response=self.client.post('/v1/responses',headers=self.headers,json={"input":[{"role":"user","content":[{"type":"input_text","text":"hello"}]}]})
        content=response.json()['output'][0]['content'][0]
        self.assertEqual(content['type'],'output_text')
        self.assertEqual(content['annotations'],[])
        self.assertIsNone(response.json()['usage'])
        self.assertEqual(response.headers['x-virel-usage-source'],'unavailable')

    def test_browser_error_is_not_success(self):
        self.stream({"error":"[Error: permission denied]"})
        response=self.chat(stream=False)
        self.assertEqual(response.status_code,502)
        self.assertEqual(response.json()['error']['code'],'upstream_error')
        self.assertNotIn('choices',response.json())

    def test_timeout_error_is_504(self):
        self.stream({"error":"[Error: HARD_CEILING_TIMEOUT - request expired]"})
        self.assertEqual(self.chat(stream=False).status_code,504)

    def test_not_ready_is_503(self):
        self.stream({"delta":"unused","text":"unused"})
        with patch.object(runtime.browser_manager,'is_ready',False):
            response=self.chat(stream=False)
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['error']['code'],'browser_not_ready')

    def test_auth_errors_have_provider_error_shape(self):
        response=self.client.post('/v1/chat/completions',json={"messages":[{"role":"user","content":"hello"}]})
        self.assertEqual(response.status_code,401)
        self.assertIn('message',response.json()['error'])

    def test_late_stream_error_is_not_normal_stop(self):
        self.stream({"delta":"part","text":"part"},{"error":"[Error: permission denied]"})
        response=self.chat(stream=True)
        self.assertIn('"error"',response.text)
        self.assertNotIn('"finish_reason": "stop"',response.text)

    def test_diagnostics_require_auth(self):
        for path in ('/debug/state','/debug_dom','/shutdown'):
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,401)

    def test_empty_prompt_is_rejected(self):
        self.stream({"delta":"unused","text":"unused"})
        response=self.client.post('/v1/chat/completions',headers=self.headers,json={"messages":[{"role":"user","content":" "}],"stream":False})
        self.assertEqual(response.status_code,400)

    def test_requested_tools_are_not_silently_dropped(self):
        self.stream({"delta":"unused","text":"unused"})
        response=self.chat(stream=False,tools=[{"type":"function","function":{"name":"read_file","parameters":{}}}])
        self.assertEqual(response.status_code,400)

    def test_measured_usage_maps_and_resets_between_requests(self):
        from virel.usage import TokenUsage
        counts = TokenUsage(21,159,180,150)
        seen=[]
        async def measured(prompt, **options):
            seen.append(options['request_id'])
            yield {'delta':'answer','text':'answer'}
            runtime.browser_manager.last_usage=counts
        with patch.object(runtime.browser_manager,'send_prompt_and_stream',measured):
            chat=self.chat().json()
            response=self.client.post('/v1/responses',headers=self.headers,json={'input':'hello'})
        self.assertEqual(chat['usage'],counts.chat())
        self.assertEqual(response.json()['usage'],counts.responses())
        self.assertEqual(response.headers['x-request-id'],seen[-1])
        self.assertEqual(response.headers['x-virel-usage-source'],'google_ai_studio')
        self.assertNotEqual(seen[0],seen[1])
        self.stream({'delta':'next','text':'next'})
        unknown=self.chat()
        self.assertIsNone(unknown.json()['usage'])
        self.assertEqual(unknown.headers['x-virel-usage-accuracy'],'unknown')

    def test_model_catalog_only_advertises_verified_selection(self):
        manager=runtime.browser_manager
        with patch.object(manager,'model_verified',True),patch.object(manager,'active_model','gemini-3.8-flash'):
            response=self.client.get('/v1/models',headers=self.headers)
            self.assertEqual([item['id'] for item in response.json()['data']],['gemini-3.8-flash'])
        with patch.object(manager,'model_verified',False):
            self.assertEqual(self.client.get('/v1/models',headers=self.headers).json()['data'],[])
        self.assertEqual(self.client.get('/v1/models').status_code,401)

    def test_selected_model_label_requires_exact_match(self):
        from virel.browser import model_matches
        self.assertTrue(model_matches('Chat with Gemini 3.8 Flash','gemini-3.8-flash'))
        self.assertTrue(model_matches('Gemini 3.8 Flash\ngemini-3.8-flash\ndescription','gemini-3.8-flash'))
        self.assertFalse(model_matches('Gemini 3.8 Flash Lite','gemini-3.8-flash'))
        self.assertFalse(model_matches('Gemini 2.5 Flash','gemini-3.8-flash'))

    def test_invalid_raw_body_returns_provider_error(self):
        for route in ('/v1/responses','/v1/completions'):
            with self.subTest(route=route):
                response=self.client.post(route,headers={**self.headers,'Content-Type':'application/json'},content='{')
                self.assertEqual(response.status_code,422)
                self.assertEqual(response.json()['error']['code'],'validation_error')
                response=self.client.post(route,headers=self.headers,json=[])
                self.assertEqual(response.status_code,400)

    def test_nontext_responses_input_is_rejected(self):
        self.stream({'delta':'unused','text':'unused'})
        for input_value in ([{'role':'user','content':[{'type':'input_file','file_id':'file-1'}]}],None,42,[{}]):
            response=self.client.post('/v1/responses',headers=self.headers,json={'input':input_value})
            self.assertEqual(response.status_code,400)

    def test_unsupported_execution_options_and_bad_text_values(self):
        self.stream({'delta':'unused','text':'unused'})
        for extra in ({'background':True},{'model':42},{'instructions':{}},{'text':{'format':{'type':'json_object'}}}):
            response=self.client.post('/v1/responses',headers=self.headers,json={'input':'hello',**extra})
            self.assertEqual(response.status_code,400)
        response=self.client.post('/v1/responses',headers=self.headers,json={'input':[{'role':'user','content':[{'type':'input_text','text':42}]}]})
        self.assertEqual(response.status_code,400)

    def test_literal_error_prefix_is_valid_model_text(self):
        self.stream({'delta':'[Error: example]','text':'[Error: example]'})
        response=self.chat()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['choices'][0]['message']['content'],'[Error: example]')

    def test_malformed_legacy_responses_messages_are_rejected(self):
        for messages in ({},['hello'],[{'content':'hello'}],[{'role':42,'content':'hello'}]):
            with self.subTest(messages=messages):
                response=self.client.post('/v1/responses',headers=self.headers,json={'messages':messages})
                self.assertEqual(response.status_code,400)
