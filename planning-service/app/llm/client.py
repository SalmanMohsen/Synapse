"""vLLM chat-completion client.

Takes an injected openai.AsyncOpenAI client (created once at worker startup,
pointed at vLLM's OpenAI-compatible endpoint) rather than opening a new httpx
connection per call — the client this replaces created a fresh
httpx.AsyncClient() on every single call and never reused the pooled client
worker.py had already set up in ctx.
"""

import json
import logging
from typing import Optional, Type, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClientError(RuntimeError):
    pass


async def get_completion(
    client: AsyncOpenAI,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    response_model: Optional[Type[T]] = None,
    temperature: float = 0.2,
) -> str | T:
    """Send a chat completion request to vLLM.

    If response_model is provided, constrains decoding via vLLM's structured-
    outputs mechanism against the model's JSON schema.

    No retry loop here — retry-with-backoff for hard technical failures
    (vLLM unreachable, timeout) is step 15's explicit scope ("Failure
    handling"), not this call's. This raises immediately on failure; step 15
    wraps callers with the real 1/5/15-minute backoff.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    extra_body = {}
    if response_model is not None:
        # vLLM's current documented mechanism (docs.vllm.ai, "Structured
        # Outputs"): extra_body={"structured_outputs": {"json": schema}}.
        # This supersedes the older extra_body={"guided_json": schema} form,
        # which vLLM is deprecating. NOTE: vLLM's structured-output API has
        # changed more than once across versions — verify this against
        # whatever version actually gets installed; if this 400s, the
        # fallback is trying guided_json instead (same schema, different key).
        extra_body["structured_outputs"] = {"json": response_model.model_json_schema()}

    try:
        completion = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=1500,  # Matches the 4K output budget reservation
            extra_body=extra_body or None,
        )
        content = completion.choices[0].message.content
    except Exception as exc:
        raise LLMClientError(f"LLM call failed: {exc}") from exc

    if response_model is not None:
        try:
            return response_model.model_validate_json(content)
        except Exception as exc:
            # Schema-invalid output despite the structured-output constraint
            # usually means the constraint didn't actually apply (e.g. the
            # extra_body key above isn't the one this vLLM version expects) —
            # worth checking that before assuming it's a model-quality issue.
            raise LLMClientError(
                f"Model output failed schema validation: {exc}. Raw content: {content!r}"
            ) from exc

    return content
