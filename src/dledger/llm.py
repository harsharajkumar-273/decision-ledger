"""Tiered Nemotron access through Nebius Token Factory (OpenAI-compatible API).

Tiers:
  NANO   cheap, high volume: bulk extraction
  SUPER  mid: linking and entity dedup
  ULTRA  expensive: verdicts over the few candidates that survive graph queries
"""
from __future__ import annotations

import json
import os
import re
import time
from enum import Enum
from typing import Callable, Optional


class Tier(str, Enum):
    NANO = "nano"
    SUPER = "super"
    ULTRA = "ultra"


_MODEL_ENV = {
    Tier.NANO: "DLEDGER_MODEL_NANO",
    Tier.SUPER: "DLEDGER_MODEL_SUPER",
    Tier.ULTRA: "DLEDGER_MODEL_ULTRA",
}

# Simple usage ledger so the eval can report cost/latency per tier.
USAGE: dict[str, dict[str, float]] = {
    t.value: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0} for t in Tier
}

# Injectable for tests: (tier, system, user) -> raw text
Transport = Callable[[Tier, str, str], str]
_transport: Optional[Transport] = None


def set_transport(fn: Optional[Transport]) -> None:
    global _transport
    _transport = fn


def _client():
    from openai import OpenAI

    key = os.getenv("NEBIUS_API_KEY")
    if not key:
        raise RuntimeError("NEBIUS_API_KEY is not set (see .env.example)")
    base = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
    return OpenAI(base_url=base, api_key=key, timeout=30.0, max_retries=1)


def _model(tier: Tier) -> str:
    m = os.getenv(_MODEL_ENV[tier])
    if not m:
        raise RuntimeError(
            f"{_MODEL_ENV[tier]} is not set. Copy the Nemotron model id for the "
            f"{tier.value} tier from the Token Factory model catalog."
        )
    return m


def chat(tier: Tier, system: str, user: str, temperature: float = 0.1) -> str:
    if _transport is not None:
        return _transport(tier, system, user)
    t0 = time.time()
    resp = _client().chat.completions.create(
        model=_model(tier),
        temperature=temperature,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    u = USAGE[tier.value]
    u["calls"] += 1
    u["seconds"] += time.time() - t0
    if resp.usage:
        u["prompt_tokens"] += resp.usage.prompt_tokens
        u["completion_tokens"] += resp.usage.completion_tokens
    return resp.choices[0].message.content or ""


def chat_json(tier: Tier, system: str, user: str):
    """Call the model and parse JSON out of the reply (tolerates code fences
    and reasoning preambles)."""
    raw = chat(tier, system + "\nReply with JSON only.", user)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.S)
    if fence:
        raw = fence.group(1).strip()
    start = min([i for i in (raw.find("{"), raw.find("[")) if i != -1], default=-1)
    if start > 0:
        raw = raw[start:]
    return json.loads(raw)
