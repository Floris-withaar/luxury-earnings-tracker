"""One small wrapper around the Anthropic Messages API.

Every LLM step calls `complete` or `ask_json` and names its step, so each step can use
a different model. Tests pass in a fake client, so nothing here needs a network.
"""
from __future__ import annotations

import json
import os
import re

# The model for each step. Research is simple and frequent, so it gets the cheapest model.
# Extraction and the written note run a few times a quarter and get the stronger one.
MODELS = {
    "research": os.environ.get("TRACKER_MODEL_RESEARCH") or "claude-haiku-5-5",
    "extract": os.environ.get("TRACKER_MODEL_EXTRACT") or "claude-sonnet-5-5",
    "interpret": os.environ.get("TRACKER_MODEL_INTERPRET") or "claude-sonnet-5-5",
}
# Server-side web search tool. Docs:
# https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

# List prices in USD per million tokens (input, output), as published on 15 Nov 2026 at
# https://platform.claude.com/docs/en/about-claude/pricing. Used only to estimate cost.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00)}
SEARCH_PRICE = 10.00 / 1000   # USD per web search

# Output limit per step. The current models think before they answer and that thinking counts
# toward the limit, so each limit leaves room for it. This is also the ceiling on what one call can cost.
LIMITS = {"research": 4000, "extract": 12000, "interpret": 4000}
# How hard the model works. None keeps the model's default. The note is short and simple, so it gets less.
EFFORT = {"research": None, "extract": None, "interpret": "medium"}
CEILING = 20000               # the SDK needs streaming above about 21,000 output tokens

USAGE: list[dict] = []        # one entry per API call in this run


class LLMUnavailable(RuntimeError):
    """Raised when the LLM steps cannot run (no key, or the SDK is missing)."""


class LLMCutOff(RuntimeError):
    """The answer hit the output limit before it was complete, so it cannot be trusted."""


class LLMRefused(RuntimeError):
    """The model declined the request."""


def get_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMUnavailable("Set ANTHROPIC_API_KEY to run the LLM steps.")
    try:
        import anthropic
    except ImportError as exc:
        raise LLMUnavailable("Run: pip install --require-hashes -r requirements.txt") from exc
    return anthropic.Anthropic()


def _record(step: str, model: str, response) -> None:
    usage = getattr(response, "usage", None)
    tools = getattr(usage, "server_tool_use", None)
    USAGE.append({
        "step": step, "model": model,
        "input": getattr(usage, "input_tokens", 0) or 0,
        "output": getattr(usage, "output_tokens", 0) or 0,
        "searches": getattr(tools, "web_search_requests", 0) or 0,
    })


def usage_summary() -> dict:
    """Tokens, searches and an estimated cost for everything called in this run."""
    steps, total = {}, 0.0
    for u in USAGE:
        price_in, price_out = PRICES.get(u["model"], PRICES["claude-sonnet-5-5"])
        cost = u["input"] / 1e6 * price_in + u["output"] / 1e6 * price_out + u["searches"] * SEARCH_PRICE
        s = steps.setdefault(u["step"], {"calls": 0, "input": 0, "output": 0, "searches": 0, "usd": 0.0, "model": u["model"]})
        s["calls"] += 1
        s["input"] += u["input"]
        s["output"] += u["output"]
        s["searches"] += u["searches"]
        s["usd"] = round(s["usd"] + cost, 4)
        total += cost
    return {"steps": steps, "estimated_usd": round(total, 4)}


def complete(prompt: str, *, step: str = "extract", client=None, tools=None, max_tokens: int | None = None) -> str:
    """Send one prompt and return the text of the answer."""
    client = client or get_client()
    model = MODELS[step]
    limit = max_tokens or LIMITS[step]
    first = [{"role": "user", "content": prompt}]
    messages, response, retried = first, None, False
    for _ in range(6):
        kwargs = {"model": model, "max_tokens": limit, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        if EFFORT.get(step):
            kwargs["output_config"] = {"effort": EFFORT[step]}
        response = client.messages.create(**kwargs)
        _record(step, model, response)
        reason = getattr(response, "stop_reason", None)
        # A long web-search turn can pause. Send the partial turn back to continue it.
        if reason == "pause_turn":
            messages = [first[0], {"role": "assistant", "content": response.content}]
            continue
        # A cut-off answer is never used, even if it happens to parse. Try once more with twice the room.
        if reason == "max_tokens":
            if retried or limit >= CEILING:
                raise LLMCutOff(f"The {step} answer was cut off at {limit} output tokens.")
            retried, limit, messages = True, min(limit * 2, CEILING), first
            continue
        if reason == "refusal":
            raise LLMRefused(f"The model declined the {step} request.")
        break
    return "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text")


def parse_json(text: str):
    """Read a JSON object out of a model answer, tolerating a code fence or a stray sentence."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("The model answer held no JSON object.")


def ask_json(prompt: str, **kwargs):
    return parse_json(complete(prompt, **kwargs))
