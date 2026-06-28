"""
LocalModelClient – runs a quantized model locally via Ollama or llama-cpp-python.

On the standardized hackathon environment we use Ollama since it:
- Ships as a single binary
- Supports ROCm (AMD GPU) via ROCM backend
- Has a REST API identical to OpenAI's

Supported models (swap on launch day):
  - llama3.2:1b      (~800MB, trivial tasks)
  - llama3.2:3b      (~2GB, simple tasks)
  - phi3.5:3.8b      (~2.2GB, good reasoning/token ratio)
  - qwen2.5:3b       (~1.9GB, strong on code + multilingual)
"""

import os
import time
import httpx
import tiktoken
from dataclasses import dataclass

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


class LocalModelClient:
    OLLAMA_BASE = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    # Model selection by complexity tier
    MODELS = {
        1: "llama3.2:1b",    # trivial
        2: "qwen2.5:3b",     # simple
        3: "phi3.5:3.8b",    # moderate (edge of local capability)
    }

    # Cost of remote equivalent (for savings calculation)
    REMOTE_COST_PER_1K = 0.0002

    def __init__(self):
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
        return max(1, len(text) // 4)

    def _pick_model(self, decision: RouteDecision) -> str:
        score = min(decision.complexity, 3)
        return self.MODELS.get(score, self.MODELS[3])

    def _estimate_confidence(self, answer: str, prompt: str) -> float:
        """
        Heuristic confidence for local model output.
        Local models are less reliable → tighter thresholds.
        """
        hedges = [
            "i'm not sure", "i don't know", "i cannot", "i can't be certain",
            "uncertain", "i would need", "hard to say", "it depends",
            "as an ai", "i am unable",
        ]
        answer_lower = answer.lower()

        # Penalise short or empty answers on substantive prompts
        word_count = len(answer.split())
        prompt_words = len(prompt.split())

        base = 0.85

        # Very short answer to a complex prompt = suspicious
        if prompt_words > 20 and word_count < 10:
            base -= 0.25

        # Hedge language
        hedge_count = sum(1 for h in hedges if h in answer_lower)
        base -= hedge_count * 0.10

        # Repetition (local models sometimes loop)
        sentences = [s.strip() for s in answer.split(".") if s.strip()]
        if len(sentences) > 3:
            unique_ratio = len(set(sentences)) / len(sentences)
            if unique_ratio < 0.6:
                base -= 0.20

        return max(0.0, min(1.0, base))

    async def complete(self, prompt: str, decision: RouteDecision) -> ModelResult:
        model = self._pick_model(decision)
        start = time.time()
        prompt_tokens = self._count_tokens(prompt)

        # Check if Ollama is available
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.OLLAMA_BASE}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are a precise, concise assistant. "
                                    "Answer the question directly and accurately. "
                                    "Do not add unnecessary padding or caveats."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 512,
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            answer = data["message"]["content"].strip()
            total_tokens = prompt_tokens + self._count_tokens(answer)
            latency = round((time.time() - start) * 1000, 1)

        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            # Ollama not available → fallback demo response
            answer = (
                f"[LOCAL DEMO] Ollama not running. Start with: `ollama serve` "
                f"and pull `{model}`. Would have answered: '{prompt[:80]}'"
            )
            total_tokens = prompt_tokens + self._count_tokens(answer)
            latency = 0.0

        # Tokens saved = cost of doing this on remote instead
        tokens_saved_cost = (total_tokens / 1000) * self.REMOTE_COST_PER_1K

        return ModelResult(
            answer=answer,
            model_name=f"local/{model}",
            tokens_used=total_tokens,
            tokens_saved=round(tokens_saved_cost * 10000) / 10000,  # in USD
            cost_usd=0.0,  # local = free
            confidence=self._estimate_confidence(answer, prompt),
            latency_ms=latency,
        )
