"""
FireworksClient – remote model via Fireworks AI API.
Used for complex tasks that exceed local model capability.

Models (revealed on launch day – these are the defaults per hackathon):
  - accounts/fireworks/models/llama-v3p1-8b-instruct  (fast, cheap)
  - accounts/fireworks/models/llama-v3p1-70b-instruct (quality)
  - accounts/fireworks/models/llama-v3p3-70b-instruct (best)
  - accounts/fireworks/models/mixtral-8x7b-instruct   (MoE, efficient)
"""

import os
import time
import json
import httpx
import tiktoken
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


class FireworksClient:
    BASE_URL = "https://api.fireworks.ai/inference/v1"

    # Model tiers – verified against Fireworks Model Library (July 2026)
    FAST_MODEL    = "accounts/fireworks/models/glm-5p2"
    QUALITY_MODEL = "accounts/fireworks/models/glm-5p2"

    COST_PER_1K = {
        "8b":  0.00014,   # glm-5p2 cached input rate, approximate
        "70b": 0.0014,    # glm-5p2 output rate, approximate
    }

    def __init__(self):
        self.api_key = os.getenv("FIREWORKS_API_KEY", "")
        self._enc = None

    def _tokenizer(self):
        if not self._enc:
            try:
                self._enc = tiktoken.get_encoding("cl100k_base")
            except Exception:
                self._enc = None
        return self._enc

    def _count_tokens(self, text: str) -> int:
        enc = self._tokenizer()
        if enc:
            return len(enc.encode(text))
        # fallback: ~4 chars per token
        return max(1, len(text) // 4)

    def _pick_model(self, decision: RouteDecision) -> tuple[str, str]:
        """Pick model tier based on complexity."""
        if decision.complexity <= 3:
            return self.FAST_MODEL, "8b"
        else:
            return self.QUALITY_MODEL, "70b"

    def _estimate_confidence(self, answer: str) -> float:
        """
        Heuristic confidence from response content.
        Remote model is generally high confidence unless it hedges.
        """
        hedges = [
            "i'm not sure", "i don't know", "i cannot", "i can't",
            "uncertain", "unclear", "it depends", "hard to say",
            "not enough information", "i would need more",
        ]
        answer_lower = answer.lower()
        hedge_count = sum(1 for h in hedges if h in answer_lower)
        base = 0.92
        return max(0.5, base - hedge_count * 0.08)

    async def complete(self, prompt: str, decision: RouteDecision) -> ModelResult:
        model_id, tier = self._pick_model(decision)
        start = time.time()

        prompt_tokens = self._count_tokens(prompt)

        # If no API key, return a demo response (for local dev / demo mode)
        if not self.api_key or self.api_key == "demo":
            return self._demo_response(prompt, model_id, tier, prompt_tokens)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a precise, efficient assistant. "
                        "Answer accurately and concisely. "
                        "Do not pad your response with unnecessary explanations unless asked."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        answer = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})
        total_tokens = usage.get("total_tokens", self._count_tokens(prompt + answer))
        latency = round((time.time() - start) * 1000, 1)

        cost = (total_tokens / 1000) * self.COST_PER_1K[tier]
        # tokens_saved = what would have been used if we'd sent a larger model
        tokens_saved = 0  # remote = no savings vs remote baseline

        return ModelResult(
            answer=answer,
            model_name=f"fireworks/{model_id.split('/')[-1]}",
            tokens_used=total_tokens,
            tokens_saved=tokens_saved,
            cost_usd=round(cost, 6),
            confidence=self._estimate_confidence(answer),
            latency_ms=latency,
        )

    def _demo_response(self, prompt: str, model_id: str, tier: str, prompt_tokens: int) -> ModelResult:
        """Returns a plausible demo answer when no API key is set."""
        fake_answers = {
            "default": f"[DEMO] This is a simulated response for: '{prompt[:60]}...' via {model_id.split('/')[-1]}. Connect FIREWORKS_API_KEY to get real answers.",
        }
        answer = fake_answers["default"]
        total_tokens = prompt_tokens + self._count_tokens(answer)
        cost = (total_tokens / 1000) * self.COST_PER_1K[tier]
        return ModelResult(
            answer=answer,
            model_name=f"fireworks/{model_id.split('/')[-1]} [DEMO]",
            tokens_used=total_tokens,
            tokens_saved=0,
            cost_usd=round(cost, 6),
            confidence=0.85,
            latency_ms=120.0,
        )

    async def stream(self, prompt: str, decision: RouteDecision):
        """
        Stream tokens from Fireworks using OpenAI-compatible SSE.
        Yields {"type": "token", "text": "..."} then {"type": "done", "result": ModelResult}
        """
        model_id, tier = self._pick_model(decision)
        start = time.time()
        prompt_tokens = self._count_tokens(prompt)

        if not self.api_key or self.api_key == "demo":
            result = self._demo_response(prompt, model_id, tier, prompt_tokens)
            for word in result.answer.split(" "):
                yield {"type": "token", "text": word + " "}
            yield {"type": "done", "result": result}
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise, efficient assistant. Answer accurately and concisely.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.2,
            "stream": True,
        }

        full_answer = ""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST", f"{self.BASE_URL}/chat/completions", headers=headers, json=payload
                ) as resp:
                    if resp.status_code != 200:
                        yield {"type": "token", "text": f"[FIREWORKS ERROR {resp.status_code}]"}
                        result = ModelResult(
                            answer=f"[FIREWORKS ERROR {resp.status_code}]",
                            model_name=f"fireworks/{model_id.split('/')[-1]} [ERROR]",
                            tokens_used=prompt_tokens, tokens_saved=0, cost_usd=0.0,
                            confidence=0.3, latency_ms=round((time.time() - start) * 1000, 1),
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
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            full_answer += token
                            yield {"type": "token", "text": token}

            latency = round((time.time() - start) * 1000, 1)
            total_tokens = self._count_tokens(prompt + full_answer)
            cost = (total_tokens / 1000) * self.COST_PER_1K[tier]

            result = ModelResult(
                answer=full_answer.strip(),
                model_name=f"fireworks/{model_id.split('/')[-1]}",
                tokens_used=total_tokens,
                tokens_saved=0,
                cost_usd=round(cost, 6),
                confidence=self._estimate_confidence(full_answer),
                latency_ms=latency,
            )
            yield {"type": "done", "result": result}

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            result = ModelResult(
                answer=f"[FIREWORKS ERROR] Connection failed: {str(e)}",
                model_name=f"fireworks/{model_id.split('/')[-1]} [ERROR]",
                tokens_used=prompt_tokens, tokens_saved=0, cost_usd=0.0,
                confidence=0.3, latency_ms=round((time.time() - start) * 1000, 1),
            )
            yield {"type": "done", "result": result}