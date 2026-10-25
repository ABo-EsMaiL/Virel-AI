"""Native Model Context Protocol (MCP) Streamable HTTP / JSON-RPC 2.0 endpoint."""
import json
import uuid
from contextlib import aclosing
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from ..auth import verify_native_key
from ..config import DEFAULT_MODEL
from ..generation import checked_stream, require_ready
from ..image_agent import generate_chat_image, generate_chat_voice
from ..runtime import browser_manager, _get_semaphore

router = APIRouter()

MCP_TOOLS = [
    {
        "name": "virel_generate_image",
        "description": "Generate an image using Google AI Studio image models (e.g. gemini-3.1-flash-lite-image) in an isolated browser tab and save it locally.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed English visual prompt describing the image to generate."
                },
                "save_directory": {
                    "type": "string",
                    "description": "Optional absolute path to the project/workspace folder or file path where the image should be saved directly."
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "virel_generate_speech",
        "description": "Synthesize spoken MP3 audio (TTS) using Google AI Studio Flash TTS in an isolated browser tab and save it locally.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Exact text script to speak aloud (supports Arabic, English, etc.)."
                },
                "voice": {
                    "type": "string",
                    "description": "Optional voice name (e.g. 'Fola', 'Bodi', 'Koda', 'Lumi', 'Mako', 'Sola', 'alloy')."
                },
                "save_directory": {
                    "type": "string",
                    "description": "Optional absolute path to the project/workspace folder or file path where the MP3 should be saved directly."
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "virel_web_research",
        "description": "Run a live query or research prompt on Google AI Studio Gemini with Google Search Grounding enabled in an isolated tab.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The question, topic, or technical problem to research."
                },
                "enable_search": {
                    "type": "boolean",
                    "description": "Whether to enable live Google Search Grounding (default: true)."
                }
            },
            "required": ["prompt"]
        }
    }
]


def _rpc_result(req_id, result):
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})


def _rpc_error(req_id, code, message):
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


@router.get("/mcp", dependencies=[Depends(verify_native_key)])
async def mcp_info():
    """Health/info discovery for HTTP MCP clients."""
    return {
        "name": "virel-ai-mcp",
        "version": "0.1.1",
        "transport": "streamable-http",
        "protocolVersion": "2024-11-05",
        "tools": [t["name"] for t in MCP_TOOLS]
    }


@router.post("/mcp", dependencies=[Depends(verify_native_key)])
async def mcp_endpoint(request: Request):
    """JSON-RPC 2.0 handler for Model Context Protocol (MCP)."""
    try:
        body = await request.json()
    except Exception:
        return _rpc_error(None, -32700, "Parse error: invalid JSON payload.")

    if not isinstance(body, dict):
        return _rpc_error(None, -32600, "Invalid Request: expected JSON-RPC object.")

    method = body.get("method")
    req_id = body.get("id")
    params = body.get("params") or {}

    if method == "initialize":
        client_version = params.get("protocolVersion") if isinstance(params, dict) else None
        negotiated_version = client_version if isinstance(client_version, str) and client_version else "2024-11-05"
        return _rpc_result(req_id, {
            "protocolVersion": negotiated_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "virel-ai-mcp", "version": "0.1.1"}
        })

    if method in ("notifications/initialized", "notifications/cancelled"):
        return Response(status_code=202)

    if method == "ping":
        return _rpc_result(req_id, {})

    if method == "tools/list":
        return _rpc_result(req_id, {"tools": MCP_TOOLS})

    if method == "tools/call":
        if not isinstance(params, dict):
            return _rpc_error(req_id, -32602, "Invalid params.")
        name = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return _rpc_error(req_id, -32602, "Tool arguments must be an object.")

        if name == "virel_generate_image":
            prompt = args.get("prompt", "")
            if not isinstance(prompt, str) or not prompt.strip():
                return _rpc_error(req_id, -32602, "A non-empty 'prompt' string is required.")
            res = await generate_chat_image(prompt.strip(), save_directory=args.get("save_directory"))
            is_err = not bool(res.get("file_path"))
            payload = {
                "status": "error" if is_err else "success",
                "file_path": res.get("posix_path") or res.get("file_path"),
                "url": res.get("img_url"),
                "local_url": res.get("local_url"),
                "public_url": res.get("public_url"),
                "model": res.get("model"),
                "message": res.get("text")
            }
            return _rpc_result(req_id, {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                "isError": is_err
            })

        if name == "virel_generate_speech":
            text_val = args.get("text", "")
            if not isinstance(text_val, str) or not text_val.strip():
                return _rpc_error(req_id, -32602, "A non-empty 'text' string is required.")
            res = await generate_chat_voice(
                text_val.strip(),
                voice=args.get("voice"),
                save_directory=args.get("save_directory")
            )
            is_err = not bool(res.get("file_path"))
            payload = {
                "status": "error" if is_err else "success",
                "file_path": res.get("posix_path") or res.get("file_path"),
                "url": res.get("audio_url"),
                "local_url": res.get("local_url"),
                "public_url": res.get("public_url"),
                "voice": res.get("voice"),
                "message": res.get("text")
            }
            return _rpc_result(req_id, {
                "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                "isError": is_err
            })

        if name == "virel_web_research":
            prompt = args.get("prompt", "")
            if not isinstance(prompt, str) or not prompt.strip():
                return _rpc_error(req_id, -32602, "A non-empty 'prompt' string is required.")
            enable_search = args.get("enable_search", True)
            if not isinstance(enable_search, bool):
                enable_search = True
            try:
                await require_ready()
                sem = _get_semaphore()
                full_text = ""
                call_id = "mcp_" + uuid.uuid4().hex[:12]
                async with sem:
                    async with browser_manager.lock:
                        async with aclosing(checked_stream(
                            prompt.strip(),
                            call_id,
                            model_name=DEFAULT_MODEL,
                            enable_search=enable_search
                        )) as stream:
                            async for item in stream:
                                if isinstance(item, dict):
                                    full_text = item.get("text", full_text)
                                else:
                                    full_text += item
                return _rpc_result(req_id, {
                    "content": [{"type": "text", "text": full_text}],
                    "isError": False
                })
            except Exception as exc:
                detail = getattr(exc, "detail", str(exc))
                return _rpc_result(req_id, {
                    "content": [{"type": "text", "text": f"MCP research failed: {detail}"}],
                    "isError": True
                })

        return _rpc_error(req_id, -32601, f"Unknown tool: {name}")

    return _rpc_error(req_id, -32601, f"Method not found: {method}")
