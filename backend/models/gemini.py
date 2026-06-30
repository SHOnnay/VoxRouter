"""
GeminiClient – remote model via Google Gemini 2.5 Flash API.
Used as fallback when FIREWORKS_API_KEY is not set,
or can be forced via REMOTE_PROVIDER=gemini env var.
"""

import os
import time
import httpx
from dataclasses import dataclass
from typing import Optional

from router.core import RouteDecision


@dataclass
class ModelResult:
    answer: str
    model_name: str
    tokens_used: int
    tokens_saved: int
    cost_usd: float
    confidence: float
    escalated: bool = False
    latency_ms: float = 0.0


class GeminiClient:
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    MODEL = "gemini-2.5-flash"

    # Gemini 2.5 Flash pricing (per 1K tokens, approximate)
    COST_INPUT_PER_1K  = 0.000075
    COST_OUTPUT_PER_1K = 0.0003

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")

    def _count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _estimate_confidence(self, answer: str) -> float:
        hedges = [
            "i'm not sure", "i don't know", "i cannot", "i can't",
            "uncertain", "unclear", "it depends", "hard to say",
            "not enough information", "i would need more",
        ]
        answer_lower = answer.lower()
        hedge_count = sum(1 for h in hedges if h in answer_lower)
        return max(0.5, 0.92 - hedge_count * 0.08)

    async def complete(self, prompt: str, decision: RouteDecision) -> ModelResult:
        start = time.time()
        prompt_tokens = self._count_tokens(prompt)

        if not self.api_key or self.api_key == "demo":
            return self._demo_response(prompt, prompt_tokens)

        url = f"{self.BASE_URL}/{self.MODEL}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}],
                    "role": "user",
                }
            ],
            "systemInstruction": {
                "parts": [{
                    "text": (
                        "You are a precise, efficient assistant. "
                        "Answer accurately and concisely. "
                        "Do not pad your response with unnecessary explanations unless asked."
                    )
                }]
            },
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 8192,
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)

            if resp.status_code == 429:
                error_body = resp.json().get("error", {}).get("message", "Rate limit exceeded")
                return ModelResult(
                    answer=f"[RATE LIMITED] Gemini quota exceeded: {error_body}. Falling back to demo mode — try again later or switch GEMINI_API_KEY.",
                    model_name=f"gemini/{self.MODEL} [RATE LIMITED]",
                    tokens_used=self._count_tokens(prompt),
                    tokens_saved=0,
                    cost_usd=0.0,
                    confidence=0.5,
                    latency_ms=round((time.time() - start) * 1000, 1),
                )

            if resp.status_code != 200:
                error_body = resp.json().get("error", {}).get("message", resp.text[:200])
                return ModelResult(
                    answer=f"[GEMINI ERROR {resp.status_code}] {error_body}",
                    model_name=f"gemini/{self.MODEL} [ERROR]",
                    tokens_used=self._count_tokens(prompt),
                    tokens_saved=0,
                    cost_usd=0.0,
                    confidence=0.3,
                    latency_ms=round((time.time() - start) * 1000, 1),
                )

            data = resp.json()

        candidate = data["candidates"][0]
        answer = candidate["content"]["parts"][0]["text"].strip()

        # Warn if truncated
        finish_reason = candidate.get("finishReason", "")
        if finish_reason == "MAX_TOKENS":
            answer += "\n\n[Response truncated — increase maxOutputTokens]"

        usage = data.get("usageMetadata", {})
        input_tokens  = usage.get("promptTokenCount", prompt_tokens)
        output_tokens = usage.get("candidatesTokenCount", self._count_tokens(answer))
        total_tokens  = input_tokens + output_tokens
        latency = round((time.time() - start) * 1000, 1)

        cost = (
            (input_tokens / 1000) * self.COST_INPUT_PER_1K +
            (output_tokens / 1000) * self.COST_OUTPUT_PER_1K
        )

        return ModelResult(
            answer=answer,
            model_name=f"gemini/{self.MODEL}",
            tokens_used=total_tokens,
            tokens_saved=0,
            cost_usd=round(cost, 6),
            confidence=self._estimate_confidence(answer),
            latency_ms=latency,
        )

    def _demo_response(self, prompt: str, prompt_tokens: int) -> ModelResult:
        answer = (
            f"[DEMO] Simulated Gemini 2.5 Flash response for: '{prompt[:60]}'. "
            f"Set GEMINI_API_KEY to get real answers."
        )
        total_tokens = prompt_tokens + self._count_tokens(answer)
        cost = (total_tokens / 1000) * self.COST_OUTPUT_PER_1K
        return ModelResult(
            answer=answer,
            model_name=f"gemini/{self.MODEL} [DEMO]",
            tokens_used=total_tokens,
            tokens_saved=0,
            cost_usd=round(cost, 6),
            confidence=0.85,
            latency_ms=80.0,
        )