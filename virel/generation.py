"""Checked browser results shared by protocol adapters."""
import asyncio
from contextlib import aclosing
from anyio import CancelScope
import logging
import math
from .images import prepared_images
from .file_inputs import prepared_file_inputs
from .config import DEFAULT_MODEL
from .errors import GatewayError
from .runtime import browser_manager

logger = logging.getLogger("virel.webhook")


async def require_ready():
    await browser_manager.recover_browser()
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
    if text_options is not None and not isinstance(text_options, (dict, str)):
        raise GatewayError(400, "text options must be an object or string.", "invalid_request")
    for name in ("tools", "tool_choice", "conversation", "previous_response_id", "background", "include"):
        if body.get(name):
            raise GatewayError(400, f"{name} is not supported in this text stage.", "unsupported_capability")
    response_format = body.get("response_format")
    if response_format is not None and not isinstance(response_format, (dict, str)):
        raise GatewayError(400, "response_format must be an object or string.", "invalid_request")
    for name in ("top_p",):
        if body.get(name) is not None:
            raise GatewayError(400, f"{name} is not implemented by the browser adapter.", "unsupported_parameter")
    if body.get("n", 1) != 1:
        raise GatewayError(400, "Only one completion is supported.", "unsupported_parameter")

    options = {}
    for name in ("max_tokens", "max_completion_tokens", "max_output_tokens"):
        maximum = body.get(name)
        if maximum is None:
            continue
        if type(maximum) is not int or not 1 <= maximum <= 2147483647:
            raise GatewayError(400, f"{name} must be a positive integer.", "invalid_request")
        if "max_output_tokens" in options and options["max_output_tokens"] != maximum:
            raise GatewayError(400, "Conflicting output token limits.", "invalid_request")
        options["max_output_tokens"] = maximum
    effort = body.get("reasoning_effort")
    reasoning = body.get("reasoning")
    if reasoning is not None:
        if not isinstance(reasoning, dict):
            raise GatewayError(400, "reasoning must be an object.", "invalid_request")
        if set(reasoning) - {"effort", "summary"} or reasoning.get("summary") not in (None, "none", "auto", "concise", "detailed"):
            raise GatewayError(400, "Reasoning summaries and budgets are not implemented.", "unsupported_parameter")
        nested = reasoning.get("effort")
        if effort is not None and nested is not None and effort != nested:
            raise GatewayError(400, "Conflicting reasoning effort fields.", "invalid_request")
        effort = nested if nested is not None else effort
    if effort is not None:
        if not isinstance(effort, str) or effort not in ("low", "medium", "high", "max"):
            raise GatewayError(400, "Reasoning effort must be low, medium, high or max (native high).", "unsupported_parameter")
        options["reasoning_effort"] = "high" if effort == "max" else effort
    temperature = body.get("temperature")
    if temperature is not None:
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2 or not math.isfinite(temperature):
            raise GatewayError(400, "Temperature must be a finite number between 0 and 2.", "invalid_request")
        options["temperature"] = temperature
    return options


def reasoning_headers(body):
    effort = body.get("reasoning_effort")
    if effort is None and isinstance(body.get("reasoning"), dict):
        effort = body["reasoning"].get("effort")
    return {"X-Virel-Reasoning-Requested": "max", "X-Virel-Reasoning-Applied": "high"} if effort == "max" else {}


def _browser_error(text):
    if any(marker in text.lower() for marker in ("model isn't available right now", "model isn’t available right now", "model is not available right now", "model is currently unavailable", "model is overloaded", "service unavailable")):
        return GatewayError(503, "AI Studio reports that the model is temporarily unavailable. Try again later; no gateway retry or model fallback was made.", "upstream_unavailable")
    if any(marker in text.lower() for marker in ("quota exceeded", "daily limit of requests", "reached your rate limit")):
        return GatewayError(429, "AI Studio quota or rate limit reached. Wait for the provider reset; no automatic retry was made.", "upstream_rate_limit")
    if "MODEL_NOT_FOUND" in text:
        return GatewayError(404, "Requested UI model was not found.", "model_not_found")
    if "UNSUPPORTED_MODEL" in text or "UNSUPPORTED_GOOGLE_SEARCH" in text:
        return GatewayError(400, "The requested model capability is not available.", "unsupported_capability")
    if "TIMEOUT" in text or "NO_RESPONSE_STARTED" in text:
        return GatewayError(504, "AI Studio generation timed out.", "upstream_timeout")
    if "RESET_FAILED" in text:
        return GatewayError(503, "AI Studio could not start a verified fresh chat.", "browser_not_ready")
    if "MODEL_UNAVAILABLE" in text:
        return GatewayError(503, "The requested UI model could not be verified.", "model_unavailable")
    if "not initialized" in text or "Could not locate chat prompt" in text:
        return GatewayError(503, "AI Studio prompt UI is unavailable.", "browser_not_ready")
    logger.error("Upstream error detail: %s", text)
    msg = f"AI Studio could not complete this generation: {text}" if text and text.strip() else "AI Studio could not complete this generation."
    return GatewayError(502, msg, "upstream_error")


async def checked_stream(prompt, request_id, **options):
    await require_ready()
    if browser_manager.model_catalog_observed:
        browser_manager.require_model(options.get("model_name") or DEFAULT_MODEL, output_kind=options.get("output_kind", "text"))
    browser_manager.last_usage = None
    browser_manager.last_finish_reason = None
    browser_manager.last_timings = {}
    text = ""
    has_image = False
    has_functions = False
    outcome = "failed"
    try:
        sources = options.pop("images", [])
        fallback_prompt = options.pop("fallback_prompt", prompt)
        image_sources = [source for source in sources if isinstance(source, str)]
        file_sources = [source for source in sources if isinstance(source, dict)]
        async with prepared_images(image_sources) as image_paths, prepared_file_inputs(file_sources) as file_paths:
            images, file_paths = iter(image_paths), iter(file_paths)
            paths = [next(file_paths) if isinstance(source, dict) else next(images) for source in sources]
            # The audio route owns validation and lifetime of these private paths.
            paths.extend(options.pop("attachments", []))
            async with aclosing(browser_manager.send_prompt_and_stream(prompt, request_id=request_id, images=paths, **options)) as stream:
                async for item in stream:
                    current = item.get("text", "") if isinstance(item, dict) else item
                    if isinstance(item, dict) and "error" in item:
                        err_str = str(item["error"])
                        if any(marker in err_str.lower() for marker in ("quota exceeded", "daily limit of requests", "reached your rate limit", "rate_limit")):
                            from .runtime import account_manager
                            rotated = account_manager.rotate_to_next(reason="quota_exceeded")
                            if rotated:
                                logger.warning(f"Active account hit daily quota! Auto-rotating to {rotated.id} ({rotated.label})...")
                                await browser_manager.switch_account(rotated)
                                options["images"] = sources
                                options["continuation"] = None
                                async for retry_item in checked_stream(fallback_prompt, request_id, **options):
                                    yield retry_item
                                return
                            earliest_secs = account_manager.earliest_reset_seconds()
                            hrs = earliest_secs / 3600.0
                            raise GatewayError(429, f"All configured Google accounts have reached their daily quota. Earliest reset in {hrs:.1f} hours; no gateway retry was made.", "upstream_rate_limit")
                        raise _browser_error(err_str)
                    if isinstance(item, dict):
                        browser_manager.last_finish_reason = item.get("finish_reason", browser_manager.last_finish_reason)
                        has_functions |= bool(item.get("function_calls")) and "function_settings" in options
                        has_image |= bool(item.get("image")) and options.get("output_kind") == "image"
                        text = current
                    else:
                        text += item
                    yield item
        if not text.strip() and not has_image and not has_functions and browser_manager.last_finish_reason != "max_tokens":
            raise GatewayError(502, "AI Studio returned no response text.", "empty_upstream_response")
        outcome = "completed"
    except (asyncio.CancelledError, GeneratorExit):
        with CancelScope(shield=True):
            await browser_manager.cancel_generation()
        outcome = "cancelled"
        raise
    except (TimeoutError, asyncio.TimeoutError):
        with CancelScope(shield=True):
            await browser_manager.cancel_generation()
        raise GatewayError(504, "AI Studio generation timed out.", "upstream_timeout") from None
    except GatewayError as error:
        if error.status_code == 504:
            with CancelScope(shield=True):
                await browser_manager.cancel_generation()
        raise
    except Exception:
        raise GatewayError(502, "The browser generation failed.", "upstream_error") from None
    finally:
        usage = browser_manager.last_usage
        logger.info("Request %s outcome=%s model=%s finish_reason=%s usage=%s", request_id, outcome, browser_manager.active_model,
                    browser_manager.last_finish_reason or "unavailable", usage.responses() if usage else "unavailable")


def usage_headers(request_id):
    return {"X-Request-ID": request_id,
            "X-Virel-Usage-Source": "google_ai_studio" if browser_manager.last_usage else "unavailable",
            "X-Virel-Usage-Accuracy": "reported" if browser_manager.last_usage else "unknown"}


def response_model(requested):
    if browser_manager.model_verified and browser_manager.active_model:
        return browser_manager.active_model
    return requested
