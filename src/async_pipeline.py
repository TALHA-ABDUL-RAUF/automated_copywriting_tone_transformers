"""
async_pipeline.py
------------------
The REAL-TIME path. Used when a person is waiting on the other end
(a live app, a CLI call, a UI). Optimizes for latency, not cost.

Concepts exercised here (mapped to the blueprint slides):
  - "async def / await"      -> non-blocking calls to Groq
  - "The Semaphore Gate"     -> MAX_CONCURRENT_REQUESTS caps in-flight calls
  - "The Activation Curve"   -> tenacity retry with exponential backoff + jitter
  - "asyncio.gather"         -> fan-out to multiple platforms, order preserved
  - Pydantic validation      -> every raw response is parsed & checked before
                                being returned to the caller
"""

import asyncio
import json

from groq import AsyncGroq
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type,
)

from src.config import GROQ_API_KEY, GROQ_MODEL, MAX_CONCURRENT_REQUESTS
from src.prompt_engine import compile_master_prompt
from src.schemas import GenerationRequest, MarketingCopy

_client: AsyncGroq | None = None
_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


def get_client() -> AsyncGroq:
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = AsyncGroq(api_key=GROQ_API_KEY)
    return _client


class GenerationError(Exception):
    """Raised when the model output can't be parsed into MarketingCopy."""


@retry(
    wait=wait_random_exponential(multiplier=1, max=20),
    stop=stop_after_attempt(4),
    retry=retry_if_exception_type((GenerationError, ConnectionError)),
)
async def _call_model(system_prompt: str, user_prompt: str, temperature: float, top_p: float) -> dict:
    client = get_client()
    response = await client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=temperature,
        top_p=top_p,
        max_tokens=500,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = response.choices[0].message.content

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        # Trigger a retry via tenacity rather than silently returning garbage.
        raise GenerationError(f"Model returned invalid JSON: {exc}") from exc


async def generate_one(request: GenerationRequest) -> MarketingCopy:
    """
    Generate copy for a single (product, platform, tone) combination.
    The semaphore ensures we never exceed MAX_CONCURRENT_REQUESTS calls
    to Groq at once, even if the caller fires many of these concurrently.
    """
    system_prompt, user_prompt = compile_master_prompt(request)

    async with _semaphore:
        payload = await _call_model(
            system_prompt, user_prompt, request.temperature, request.top_p
        )

    copy = MarketingCopy(
        headline=payload.get("headline", ""),
        body=payload.get("body", ""),
        call_to_action=payload.get("call_to_action", ""),
        hashtags=payload.get("hashtags", []),
        platform=request.platform,
        tone=request.tone,
    )
    return copy.finalize()


async def generate_many(requests: list[GenerationRequest]) -> list[MarketingCopy]:
    """
    Fan out N requests concurrently (e.g. one product across 5 platforms)
    and return results IN THE SAME ORDER as the input, via asyncio.gather.
    return_exceptions=True prevents one failing platform from crashing
    the whole batch — we surface a placeholder instead.
    """
    tasks = [generate_one(r) for r in requests]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: list[MarketingCopy] = []
    for req, result in zip(requests, results):
        if isinstance(result, Exception):
            output.append(
                MarketingCopy(
                    headline="[GENERATION FAILED]",
                    body=str(result),
                    call_to_action="",
                    hashtags=[],
                    platform=req.platform,
                    tone=req.tone,
                ).finalize()
            )
        else:
            output.append(result)
    return output
