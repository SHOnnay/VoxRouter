"""
GeminiClient – remote model via Google Gemini 2.5 Flash API.
Used as fallback when FIREWORKS_API_KEY is not set,
or can be forced via REMOTE_PROVIDER=gemini env var.
"""

import os
import time
import json
import asyncio
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

    # Gemini 2.5 Flash pricing (per 1K tokens, approximate)
    COST_INPUT_PER_1K  = 0.000075
    COST_OUTPUT_PER_1K = 0.0003

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

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
            resp = None
            for attempt in range(3):
                resp = await client.post(url, json=payload)
                if resp.status_code != 503:
                    break
                await asyncio.sleep(1.5 * (attempt + 1))   # backoff: 1.5s, 3s

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
                    answer=f"[GEMINI ERROR {resp.status_code}] {error_body}. Gemini's servers may be temporarily overloaded — try again in a moment.",
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

    async def stream(self, prompt: str, decision: RouteDecision):
        """
        Stream tokens from Gemini using the streamGenerateContent SSE endpoint.
        Yields {"type": "token", "text": "..."} then {"type": "done", "result": ModelResult}
        """
        start = time.time()
        prompt_tokens = self._count_tokens(prompt)

        if not self.api_key or self.api_key == "demo":
            result = self._demo_response(prompt, prompt_tokens)
            for word in result.answer.split(" "):
                yield {"type": "token", "text": word + " "}
            yield {"type": "done", "result": result}
            return

        url = f"{self.BASE_URL}/{self.MODEL}:streamGenerateContent?alt=sse&key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}], "role": "user"}],
            "systemInstruction": {
                "parts": [{
                    "text": (
                        "You are a precise, efficient assistant. "
                        "Answer accurately and concisely."
                    )
                }]
            },
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192},
        }

        full_answer = ""
        output_tokens_est = 0

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        yield {"type": "token", "text": f"[GEMINI ERROR {resp.status_code}] Streaming failed, try again."}
                        result = ModelResult(
                            answer=f"[GEMINI ERROR {resp.status_code}]",
                            model_name=f"gemini/{self.MODEL} [ERROR]",
                            tokens_used=prompt_tokens,
                            tokens_saved=0,
                            cost_usd=0.0,
                            confidence=0.3,
                            latency_ms=round((time.time() - start) * 1000, 1),
                        )
                        yield {"type": "done", "result": result}
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        candidates = chunk.get("candidates", [])
                        if not candidates:
                            continue
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            token = part.get("text", "")
                            if token:
                                full_answer += token
                                yield {"type": "token", "text": token}

            latency = round((time.time() - start) * 1000, 1)
            output_tokens_est = self._count_tokens(full_answer)
            total_tokens = prompt_tokens + output_tokens_est
            cost = (
                (prompt_tokens / 1000) * self.COST_INPUT_PER_1K +
                (output_tokens_est / 1000) * self.COST_OUTPUT_PER_1K
            )

            result = ModelResult(
                answer=full_answer.strip(),
                model_name=f"gemini/{self.MODEL}",
                tokens_used=total_tokens,
                tokens_saved=0,
                cost_usd=round(cost, 6),
                confidence=self._estimate_confidence(full_answer),
                latency_ms=latency,
            )
            yield {"type": "done", "result": result}

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            result = ModelResult(
                answer=f"[GEMINI ERROR] Connection failed: {str(e)}",
                model_name=f"gemini/{self.MODEL} [ERROR]",
                tokens_used=prompt_tokens,
                tokens_saved=0,
                cost_usd=0.0,
                confidence=0.3,
                latency_ms=round((time.time() - start) * 1000, 1),
            )
            yield {"type": "done", "result": result}