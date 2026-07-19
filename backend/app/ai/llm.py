"""ZAI (GLM) LLM client — OpenAI-compatible via the official openai SDK.

ZAI endpoint: https://api.z.ai/api/paas/v4/
Models: glm-4.6, glm-4.5, etc.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

from openai import OpenAI

from ..config import settings

log = logging.getLogger(__name__)


@dataclass
class LLMResult:
    ok: bool
    text: str
    latency_ms: int
    model: str
    error: str = ""


class ZAIClient:
    """Thin wrapper around the OpenAI SDK pointed at the ZAI endpoint."""

    def __init__(self) -> None:
        self.enabled = settings.llm_enabled
        self.model = settings.zai_model
        self._client: OpenAI | None = None
        if self.enabled:
            self._client = OpenAI(
                api_key=settings.zai_api_key,
                base_url=settings.zai_base_url,
                timeout=60.0,
            )

    def chat_json(self, system: str, user: str, temperature: float = 0.4) -> LLMResult:
        """Call the chat endpoint and return raw text. JSON-mode is requested."""
        if not self.enabled or self._client is None:
            return LLMResult(ok=False, text="", latency_ms=0, model=self.model,
                             error="LLM disabled (no ZAI_API_KEY)")
        t0 = time.perf_counter()
        try:
            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            }
            # ZAI supports response_format json_object on glm-4.x; degrade gracefully.
            try:
                kwargs["response_format"] = {"type": "json_object"}
                resp = self._client.chat.completions.create(**kwargs)
            except Exception:
                kwargs.pop("response_format", None)
                resp = self._client.chat.completions.create(**kwargs)
            text = (resp.choices[0].message.content or "").strip()
            ms = int((time.perf_counter() - t0) * 1000)
            return LLMResult(ok=True, text=text, latency_ms=ms, model=self.model)
        except Exception as exc:
            ms = int((time.perf_counter() - t0) * 1000)
            log.warning("ZAI chat failed: %s", exc)
            return LLMResult(ok=False, text="", latency_ms=ms, model=self.model, error=str(exc))


def extract_json(text: str) -> dict | None:
    """Robustly pull a JSON object out of an LLM response (handles fences/text)."""
    if not text:
        return None
    text = text.strip()
    # strip ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    # find the outermost {...}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # try to fix trailing commas
        cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None
