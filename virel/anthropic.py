"""Anthropic Messages wire adapter over existing browser generation and client tools."""
import asyncio
from contextlib import aclosing
import json
import logging
import re
import time
import uuid
from fastapi.responses import JSONResponse, StreamingResponse
from .config import MAX_REQUEST_BYTES
from .errors import GatewayError, provider_error
from .generation import validate_options, require_ready, reasoning_headers
from .messages import extract_prompt_and_images
from .schemas import ChatMessage
from .runtime import browser_manager
from .streaming import text_events
from .tools import bounded, is_tool_request, prepare_tools, _function_events

logger = logging.getLogger("virel.webhook")

def invalid(message, unsupported=False):
    raise GatewayError(400, message, "unsupported_capability" if unsupported else "invalid_request")

def cache_hint(part):
    hint = part.get("cache_control")
    if hint is not None and (not isinstance(hint, dict) or set(hint)-{"type","ttl"} or
            hint.get("type") != "ephemeral" or hint.get("ttl","5m") not in ("5m","1h")):
        invalid("Invalid cache_control hint.")

def text_blocks(value):
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        invalid("Text content must be a string or text blocks.")
    parts = []
    for part in value:
        if not isinstance(part, dict) or part.get("type") != "text" or set(part)-{"type","text","cache_control"} or not isinstance(part.get("text"),str):
            invalid("Only text blocks are supported here.", True)
        cache_hint(part)
        parts.append(part["text"])
    return "\n".join(parts)

def tool_result_blocks(value):
    if not isinstance(value, list) or not any(isinstance(p, dict) and p.get("type") == "tool_reference" for p in value):
        return text_blocks(value)
    for part in value:
        if isinstance(part, dict) and part.get("type") == "tool_reference":
            if set(part) != {"type", "tool_name"} or not isinstance(part["tool_name"], str):
                invalid("Invalid tool_reference block.")
        else:
            text_blocks([part])
    return json.dumps(value, ensure_ascii=False)


def loaded_tool_names(body, *, eager=False):
    """Derive visibility from validated, ordered client history, never tool-output prose."""
    tools = body.get("tools", [])
    if any(not isinstance(tool.get("name"), str) for tool in tools):
        invalid("Client tools require text names.")
    names = {tool["name"] for tool in tools}
    deferred = {tool.get("name") for tool in tools if tool.get("defer_loading", False)}
    loaded = names if eager else names - deferred
    if deferred and not loaded:
        invalid("At least one client tool must be non-deferred.")
    for message in body["messages"]:
        if not isinstance(message["content"], list):
            continue
        for part in message["content"]:
            if part.get("type") == "tool_use":
                if not isinstance(part.get("name"), str):
                    invalid("Historical tool use requires a text name.")
                if part["name"] in deferred and part["name"] not in loaded:
                    invalid("Historical tool use precedes discovery of its deferred definition.")
            if part.get("type") != "tool_result" or not isinstance(part.get("content"), list):
                continue
            for reference in part["content"]:
                if reference.get("type") != "tool_reference":
                    continue
                name = reference["tool_name"]
                if name not in names:
                    invalid("Tool reference must identify a declared client tool.")
                if not part.get("is_error", False):
                    loaded.add(name)
    return loaded if deferred and not eager else None


def media_part(part):
    source = part.get("source")
    if not isinstance(source, dict):
        invalid("Media requires a source.")
    kind = source.get("type")
    if kind == "base64":
        if set(source)-{"type","media_type","data"} or not isinstance(source.get("data"),str) or not isinstance(source.get("media_type"),str) or not re.fullmatch(r"[\w.+-]+/[\w.+-]+",source["media_type"]):
            invalid("Invalid base64 media source.")
        uri = "data:"+source["media_type"]+";base64,"+source["data"]
    elif kind == "url":
        if set(source)-{"type","url"} or not isinstance(source.get("url"),str):
            invalid("Invalid URL media source.")
        uri = source["url"]
    elif kind == "text" and part["type"] == "document":
        if set(source)-{"type","media_type","data"} or not isinstance(source.get("data"),str) or source.get("media_type") != "text/plain":
            invalid("Invalid text document source.")
        return {"type":"text","text":source["data"]}
    else:
        invalid("Unsupported media source; use URL, base64 or text documents.", True)
    if part["type"] == "image":
        return {"type":"image_url","image_url":{"url":uri}}
    return {"type":"file","file":{("file_data" if kind=="base64" else "file_url"):uri}}

def native_history(messages, *, desktop=False):
    if not isinstance(messages,list) or not messages:
        invalid("A nonempty messages array is required.")
    history = []
    for index, message in enumerate(messages):
        extra = set(message)-{"role","content"} if isinstance(message,dict) else set()
        role_valid = isinstance(message,dict) and message.get("role") in (("user","assistant","system") if desktop else ("user","assistant"))
        if not isinstance(message,dict) or extra or not role_valid:
            # Structural names only; never log content, role or unknown-field values.
            fields = sorted(key if isinstance(key,str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}",key)
                            else "<redacted>" for key in extra)[:16]
            role = message.get("role") if isinstance(message,dict) else None
            role_kind = role if role in ("user","assistant","system","developer","tool","function","human","ai") else type(role).__name__
            logger.warning("Messages shape rejected index=%d object=%s role_valid=%s role_kind=%s extra_count=%d extra_fields=%s",
                           index, isinstance(message,dict), role_valid, role_kind, len(extra), fields)
            invalid("Messages require user/assistant roles and content.")
        role, content = message["role"], message.get("content")
        if isinstance(content,str):
            history.append({"role":role,"content":content})
            continue
        if not isinstance(content,list) or not content:
            invalid("Message content requires nonempty supported blocks.")
        parts, calls = [], []
        def flush():
            if parts or calls:
                turn = {"role":role,"content":list(parts)}
                if calls: turn["tool_calls"] = list(calls)
                history.append(turn)
                parts.clear(); calls.clear()
        for part in content:
            if not isinstance(part,dict):
                invalid("Content blocks must be objects.")
            cache_hint(part)
            kind = part.get("type")
            if kind == "text":
                if set(part)-{"type","text","cache_control"} or not isinstance(part.get("text"),str):
                    invalid("Invalid text block.")
                parts.append({"type":"text","text":part["text"]})
            elif kind == "tool_use" and role == "assistant":
                if set(part)-{"type","id","name","input","cache_control"} or not isinstance(part.get("input"),dict):
                    invalid("Invalid tool_use block.")
                calls.append({"id":part.get("id"),"type":"function",
                              "function":{"name":part.get("name"),"arguments":bounded(part["input"],65536,"Tool arguments")}})
            elif kind == "tool_result" and role == "user":
                if set(part)-{"type","tool_use_id","content","is_error","cache_control"} or type(part.get("is_error",False)) is not bool:
                    invalid("Invalid tool_result block.")
                flush()
                result = tool_result_blocks(part.get("content",""))
                if part.get("is_error"):
                    result = json.dumps({"is_error":True,"content":result},ensure_ascii=False)
                history.append({"role":"tool","tool_call_id":part.get("tool_use_id"),"content":result})
            elif kind in ("image","document") and role == "user":
                if set(part)-{"type","source","cache_control","title","context","citations"}:
                    invalid("Unsupported media block fields.",True)
                if part.get("citations") is not None and (not isinstance(part["citations"],dict) or part["citations"] != {"enabled":False}):
                    invalid("Document citations are unavailable.",True)
                if part.get("title") or part.get("context"):
                    parts.append({"type":"text","text":text_blocks(part.get("title",""))+"\n"+text_blocks(part.get("context",""))})
                parts.append(media_part(part))
            else:
                invalid("Unsupported content block: "+str(kind)+". Signed thinking and hosted tool blocks are unavailable.", True)
        flush()
    return history

def normalize_request(body, *, desktop=False):
    if not isinstance(body,dict):
        invalid("Expected a JSON object.")
    bounded(body,MAX_REQUEST_BYTES,"Messages request")
    allowed = {"model","messages","system","max_tokens","stream","tools","tool_choice","temperature","top_p","top_k",
               "stop_sequences","metadata","thinking","output_config","context_management","service_tier"}
    if set(body)-allowed:
        invalid("Unsupported Messages request fields.",True)
    if not isinstance(body.get("model"),str) or not body["model"].strip():
        invalid("A nonempty model is required.")
    maximum = body.get("max_tokens")
    if type(maximum) is not int or not 1 <= maximum <= 2147483647:
        invalid("max_tokens must be a positive integer.")
    if type(body.get("stream",False)) is not bool:
        invalid("stream must be boolean.")
    for name in ("top_p","top_k"):
        if body.get(name) is not None: invalid(name+" is unavailable.",True)
    if body.get("stop_sequences") not in (None,[]): invalid("stop_sequences are unavailable.",True)
    if body.get("service_tier") not in (None,"auto"): invalid("Only automatic service routing is available.",True)
    metadata=body.get("metadata")
    if metadata is not None:
        if not isinstance(metadata,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in metadata.items()):
            invalid("metadata must be a string map.")
        bounded(metadata,16384,"Metadata")
    thinking=body.get("thinking")
    if thinking is not None and thinking not in ({"type":"adaptive"},{"type":"adaptive","display":"omitted"}):
        invalid("thinking supports adaptive with optional display omitted; signed transcripts and token budgets are unavailable.",True)
    output=body.get("output_config",{})
    if not isinstance(output,dict) or set(output)-{"effort"}:
        invalid("output_config supports effort only.",True)
    context=body.get("context_management")
    if context is not None and context not in ({},{"edits":[]},{"edits":[{"type":"clear_thinking_20251015","keep":"all"}]}):
        invalid("Context edits are unavailable; no thinking transcript is emitted to clear.",True)
    converted={"model":body["model"],"messages":native_history(body.get("messages"),desktop=desktop),"stream":False}
    if "system" in body:
        converted["messages"].insert(0,{"role":"system","content":text_blocks(body["system"])})
    if "temperature" in body: converted["temperature"]=body["temperature"]
    if "effort" in output: converted["reasoning_effort"]=output["effort"]
    tools=body.get("tools",[])
    if not isinstance(tools,list): invalid("tools must be an array.")
    if tools:
        converted["tools"]=[]
        for index, tool in enumerate(tools):
            extra = set(tool)-{"name","description","input_schema","cache_control","type","defer_loading"} if isinstance(tool,dict) else set()
            kind = tool.get("type","custom") if isinstance(tool,dict) else None
            if not isinstance(tool,dict) or extra or kind != "custom":
                fields = sorted(key if isinstance(key,str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}",key)
                                else "<redacted>" for key in extra)[:16]
                kind_label = kind if isinstance(kind,str) and (kind == "custom" or re.fullmatch(r"(?:bash|text_editor|computer|web_search|web_fetch|tool_search_tool_regex|tool_search_tool_bm25)_[0-9]{8}",kind)) else type(kind).__name__
                flags = {key:tool[key] if type(tool[key]) is bool else type(tool[key]).__name__
                         for key in ("strict","defer_loading","eager_input_streaming") if isinstance(tool,dict) and key in tool}
                logger.warning("Tool shape rejected index=%d kind=%s extra_count=%d extra_fields=%s flags=%s",
                               index, kind_label, len(extra), fields, flags)
                invalid("Only client-owned custom tools are available.",True)
            cache_hint(tool)
            if "defer_loading" in tool and type(tool["defer_loading"]) is not bool:
                invalid("defer_loading must be boolean.")
            if tool.get("defer_loading") and tool.get("cache_control") is not None:
                invalid("Deferred tools cannot have cache_control.")
            converted["tools"].append({"type":"function","function":{"name":tool.get("name"),
                "description":tool.get("description",""),"parameters":tool.get("input_schema")}})
    if "tool_choice" in body:
        choice=body["tool_choice"]
        if not isinstance(choice,dict) or set(choice)-{"type","name","disable_parallel_tool_use"} or type(choice.get("disable_parallel_tool_use",False)) is not bool:
            invalid("Invalid tool_choice.")
        kind=choice.get("type")
        if kind=="tool":
            converted["tool_choice"]={"type":"function","function":{"name":choice.get("name")}}
        elif kind in ("auto","none","any") and "name" not in choice:
            converted["tool_choice"]={"auto":"auto","none":"none","any":"required"}[kind]
        else: invalid("Invalid tool_choice.")
        converted["parallel_tool_calls"]=not choice.get("disable_parallel_tool_use",False)
    ordinary={k:v for k,v in converted.items() if k not in ("tools","tool_choice","parallel_tool_calls")}
    options=validate_options(ordinary)
    options["max_output_tokens"]=maximum
    return converted,options

def native_payload(payload,identifier):
    message=payload["choices"][0]["message"]
    content=[]
    if message.get("content"): content.append({"type":"text","text":message["content"]})
    for call in message.get("tool_calls",[]):
        content.append({"type":"tool_use","id":call["id"],"name":call["function"]["name"],"input":json.loads(call["function"]["arguments"])})
    usage=payload.get("usage")
    return {"id":identifier,"type":"message","role":"assistant","model":payload["model"],"content":content,
            "stop_reason":"tool_use" if message.get("tool_calls") else ("max_tokens" if payload["choices"][0]["finish_reason"] == "length" else "end_turn"),"stop_sequence":None,
            "usage":{"input_tokens":usage["prompt_tokens"] if usage else None,
                     "output_tokens":usage["completion_tokens"] if usage else None}}

def native_error(error):
    detail=provider_error(error)
    kind={401:"authentication_error",403:"permission_error",404:"not_found_error",413:"request_too_large",
          429:"rate_limit_error",529:"overloaded_error"}.get(error.status_code,"api_error" if error.status_code>=500 else "invalid_request_error")
    return {"type":"error","error":{"type":kind,"message":detail["message"]},"request_id":"req_"+uuid.uuid4().hex[:16]}

async def messages_response(body,sem,owner,*,desktop=False):
    converted,options=normalize_request(body,desktop=desktop)
    alias = converted["model"] if desktop else None
    if desktop:
        from .models import desktop_aliases
        await require_ready()
        target = desktop_aliases(browser_manager.model_catalog).get(alias)
        if target is None:
            raise GatewayError(404,"Requested Desktop alias was not observed as available.","model_not_found")
        converted["model"] = target
    identifier="msg_"+uuid.uuid4().hex[:24]
    now=int(time.time())
    logger.info("Messages request %s desktop=%s stream=%s tools=%d deferred=%d max_tokens=%d",
                identifier, desktop, body.get("stream", False), len(body.get("tools", [])),
                sum(tool.get("defer_loading", False) for tool in body.get("tools", [])), body["max_tokens"])
    plan=None
    if is_tool_request(converted):
        visible = loaded_tool_names(body, eager=desktop)
        plan=prepare_tools(converted,False,visible_tools=visible)
        if visible is not None:
            plan["deferred_tools"] = sorted(tool["name"] for tool in body["tools"] if tool.get("defer_loading", False))
        plan["materialize_defaults"]=True
        browser_manager.prepare(plan["history"],bool(plan["declarations"]))
    await require_ready()
    if plan:
        source=_function_events(plan,options,sem,owner,identifier,now,converted["model"],False,False)
    else:
        prompt,images=extract_prompt_and_images([ChatMessage(**m) for m in converted["messages"]])
        if not prompt.strip() and not images: invalid("A nonempty prompt is required.")
        source=text_events(prompt,identifier,now,converted["model"],False,sem,images=images,**options)
    headers={**reasoning_headers(converted), "X-Virel-Prompt-Cache":"unavailable","X-Virel-Thinking-Transcript":"unavailable",
             "X-Virel-Model-Provider":"google-ai-studio","X-Virel-Stop-Reason":"browser-completion-or-tool-use"}
    if alias:
        headers.update({"X-Virel-Model-Alias":alias,"X-Virel-Requested-UI-Model":converted["model"]})
    async def completed():
        final=None
        async with aclosing(source):
            async for item in source:
                if "response" in item: final=item
        if final is None: raise GatewayError(502,"Generation ended without a completed message.","incomplete_upstream_stream")
        payload = native_payload(final["response"],identifier)
        if alias:
            payload["virel"] = {"compatibility_alias":True,"requested_ui_model":converted["model"],
                                "actual_model":payload["model"],"actual_provider":"google-ai-studio"}
            payload["model"] = alias
        return payload,final
    if not body.get("stream",False):
        payload,final=await completed()
        if alias:
            headers["X-Virel-Actual-Model"] = payload["virel"]["actual_model"]
        return JSONResponse(payload,headers={**final.get("headers",{}),**headers})
    async def serialize():
        pending=None
        def event(kind,**values):
            return "event: "+kind+"\ndata: "+json.dumps({"type":kind,**values},ensure_ascii=False)+"\n\n"
        try:
            payload,final=await completed()
            pending=final.get("pending")
            yield event("message_start",message={**payload,"content":[],"stop_reason":None,"usage":payload["usage"]})
            for index,block in enumerate(payload["content"]):
                initial={**block,"text":""} if block["type"]=="text" else {**block,"input":{}}
                yield event("content_block_start",index=index,content_block=initial)
                if block["type"]=="text":
                    value=block["text"]
                    step=max(16,(len(value)+59)//60)
                    for offset in range(0,len(value),step):
                        if offset: await asyncio.sleep(0.025)
                        yield event("content_block_delta",index=index,delta={"type":"text_delta","text":value[offset:offset+step]})
                else:
                    yield event("content_block_delta",index=index,delta={"type":"input_json_delta","partial_json":json.dumps(block["input"],ensure_ascii=False)})
                yield event("content_block_stop",index=index)
            yield event("message_delta",delta={"stop_reason":payload["stop_reason"],"stop_sequence":None},usage=payload["usage"])
            yield event("message_stop")
        except GatewayError as error:
            yield "event: error\ndata: "+json.dumps(native_error(error),ensure_ascii=False)+"\n\n"
        except BaseException:
            if pending is not None and browser_manager.tool_run.pending is pending:
                browser_manager.tool_run.clear()
            raise
    return StreamingResponse(serialize(),media_type="text/event-stream",headers={**headers,
        "Cache-Control":"no-cache","X-Accel-Buffering":"no","X-Virel-Stream-Mode":"completed_browser_snapshot_paced"})
