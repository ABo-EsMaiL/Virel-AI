"""Measured browser usage, protocol mapping and request correlation."""
import asyncio
import json
from pathlib import Path
import unittest

from virel.usage import BrowserUsageObserver, parse_usage

FIXTURE=Path(__file__).with_name('fixtures')/'ai_studio_generate_text.json'
ENDPOINT='https://alkalimakersuite-pa.clients6.google.com/$rpc/google.internal.alkali.applications.makersuite.v1.MakerSuiteService/GenerateContent'


class UsageTests(unittest.TestCase):
    def test_observed_counts_include_thinking_once(self):
        usage=parse_usage(FIXTURE.read_text(encoding='utf-8'))
        self.assertEqual(usage.chat(),{'prompt_tokens':21,'completion_tokens':159,'total_tokens':180,'completion_tokens_details':{'reasoning_tokens':150}})
        self.assertEqual(usage.responses(),{'input_tokens':21,'output_tokens':159,'total_tokens':180,'output_tokens_details':{'reasoning_tokens':150}})
        self.assertNotIn('prompt_tokens_details',usage.chat())

    def test_partial_and_inconsistent_counts_are_not_fabricated(self):
        for changed in (None,-1,True,'21'):
            data=json.loads(FIXTURE.read_text(encoding='utf-8'))
            data[0][0][2][0]=changed
            self.assertIsNone(parse_usage(json.dumps(data)))
        data=json.loads(FIXTURE.read_text(encoding='utf-8'))
        data[0][0][2][2]=30
        self.assertIsNone(parse_usage(json.dumps(data)))

    def test_unfinished_or_unrelated_packet_is_not_usage(self):
        data=json.loads(FIXTURE.read_text(encoding='utf-8'))
        data[0][0][0][0][1]=None
        self.assertIsNone(parse_usage(json.dumps(data)))
        self.assertIsNone(parse_usage('[21,[],[[[20],1]],null,null,[[1,21]]]'))
        self.assertIsNone(parse_usage('not JSON'))


class Request:
    method='POST'
    url=ENDPOINT
    def __init__(self,prompt):self.post_data=json.dumps({'text':prompt})

class Response:
    status=200
    def __init__(self,request,wait=None):self.request=request;self.wait=wait
    async def text(self):
        if self.wait:await self.wait.wait()
        return FIXTURE.read_text(encoding='utf-8')


class CorrelationTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_current_registered_generation_is_used(self):
        observer=BrowserUsageObserver()
        observer.begin('one','hello')
        request=Request('hello')
        observer.on_request(request)
        observer.on_response(Response(request))
        usage=await observer.finish('one')
        self.assertEqual(usage.total_tokens,180)
        observer.begin('two','hello')
        # A repeated prompt is not sufficient without a request registered in this attempt.
        observer.on_response(Response(request))
        self.assertIsNone(await observer.finish('two'))

    async def test_late_previous_response_cannot_overwrite_new_attempt(self):
        observer=BrowserUsageObserver()
        observer.begin('old','same')
        old=Request('same');observer.on_request(old)
        gate=asyncio.Event()
        observer.on_response(Response(old,gate))
        observer.begin('new','same')
        gate.set()
        await asyncio.sleep(0)
        self.assertIsNone(await observer.finish('new'))

    async def test_tokenization_and_wrong_prompt_are_not_generation_usage(self):
        observer=BrowserUsageObserver();observer.begin('one','actual prompt')
        unrelated=Request('different prompt');observer.on_request(unrelated)
        observer.on_response(Response(unrelated))
        tokenizer=Request('actual prompt');tokenizer.url=ENDPOINT.replace('GenerateContent','CountTokens')
        observer.on_request(tokenizer);observer.on_response(Response(tokenizer))
        self.assertIsNone(await observer.finish('one'))
