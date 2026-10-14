"""Checked browser results shared by protocol adapters."""
import asyncio
from contextlib import aclosing
import logging
from .errors import GatewayError
from .runtime import browser_manager

logger = logging.getLogger("virel.webhook")


def require_ready():
    if not browser_manager.is_ready:
        raise GatewayError(503, "AI Studio is not ready. Check the browser login and prompt UI.", "browser_not_ready")


def validate_options(body):
    if not isinstance(body, dict):
        raise GatewayError(400, "Expected a JSON object.", "invalid_request")
    if "model" in body and (not isinstance(body["model"], str) or not body["model"].strip()):
        raise GatewayError(400, "Model must be a nonempty string.", "invalid_request")
    if "instructions" in body and not isinstance(body["instructions"], str):
        raise GatewayError(400, "Instructions must be text.", "invalid_request")
    text_options = body.get("text")
    if text_options is not None and text_options != {"format": {"type": "text"}}:
        raise GatewayError(400, "Structured text formatting is not supported yet.", "unsupported_parameter")
    for name in ("tools", "tool_choice", "conversation", "previous_response_id", "background", "reasoning", "include"):
        if body.get(name):
            raise GatewayError(400, f"{name} is not supported in this text stage.", "unsupported_capability")
    for name in ("temperature", "max_tokens", "max_completion_tokens", "max_output_tokens", "top_p", "response_format"):
        if body.get(name) is not None:
            raise GatewayError(400, f"{name} is not implemented by the browser adapter.", "unsupported_parameter")
    if body.get("n", 1) != 1:
        raise GatewayError(400, "Only one completion is supported.", "unsupported_parameter")


def _browser_error(text):
    if "TIMEOUT" in text or "NO_RESPONSE_STARTED" in text:
        return GatewayError(504, "AI Studio generation timed out.", "upstream_timeout")
    if "RESET_FAILED" in text:
        return GatewayError(503, "AI Studio could not start a verified fresh chat.", "browser_not_ready")
    if "MODEL_UNAVAILABLE" in text:
        return GatewayError(503, "The requested UI model could not be verified.", "model_unavailable")
    if "not initialized" in text or "Could not locate chat prompt" in text:
        return GatewayError(503, "AI Studio prompt UI is unavailable.", "browser_not_ready")
    return GatewayError(502, "AI Studio could not complete this generation.", "upstream_error")


async def checked_stream(prompt, request_id, **options):
    require_ready()
    browser_manager.last_usage = None
    browser_manager.last_timings = {}
    text = ""
    outcome = "failed"
    try:
        async with aclosing(browser_manager.send_prompt_and_stream(prompt, request_id=request_id, **options)) as stream:
            async for item in stream:
                current = item.get("text", "") if isinstance(item, dict) else item
                if isinstance(item, dict) and "error" in item:
                    raise _browser_error(str(item["error"]))
                if isinstance(item, dict):
                    text = current
                else:
                    text += item
                yield item
        if not text.strip():
            raise GatewayError(502, "AI Studio returned no response text.", "empty_upstream_response")
        outcome = "completed"
    except (TimeoutError, asyncio.TimeoutError):
        raise GatewayError(504, "AI Studio generation timed out.", "upstream_timeout") from None
    except GatewayError:
        raise
    except Exception:
        raise GatewayError(502, "The browser generation failed.", "upstream_error") from None
    finally:
        usage = browser_manager.last_usage
        logger.info("Request %s outcome=%s model=%s usage=%s", request_id, outcome, browser_manager.active_model,
                    usage.responses() if usage else "unavailable")


def usage_headers(request_id):
    return {"X-Request-ID": request_id,
            "X-Virel-Usage-Source": "google_ai_studio" if browser_manager.last_usage else "unavailable",
            "X-Virel-Usage-Accuracy": "reported" if browser_manager.last_usage else "unknown"}
