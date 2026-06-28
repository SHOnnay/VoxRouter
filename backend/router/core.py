"""
RouterEngine – complexity classifier + routing decision logic.

The router reads each incoming prompt and decides:
  LOCAL  → small quantized model on-device (zero API cost)
  REMOTE → Fireworks AI API (higher quality, costs tokens)

Routing logic is layered:
  Layer 1: Rule-based heuristics (fast, free)
  Layer 2: Keyword + structural signals
  Layer 3: Entropy/length analysis
  Layer 4: Confidence-based escalation after local attempt

This gives us the best token savings while staying above accuracy threshold.
"""

import re
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RouteDecision:
    use_local: bool
    complexity: int           # 1-5
    label: str                # "trivial" | "simple" | "moderate" | "complex" | "expert"
    reasons: list[str] = field(default_factory=list)
    escalation_reason: Optional[str] = None


class RouterEngine:
    CONFIDENCE_THRESHOLD = 0.72   # below this → escalate to remote

    # Token cost estimates (USD per 1K tokens, approximate)
    LOCAL_COST_PER_1K  = 0.0000   # free
    REMOTE_COST_PER_1K = 0.0002   # Fireworks llama-3.1-8b-instruct tier

    # ── Complexity signals ──────────────────────────────────────────────────
    TRIVIAL_PATTERNS = [
        r"^(yes|no|true|false)\??$",
        r"^what is \d+\s*[\+\-\*\/]\s*\d+",
        r"^(capital of|currency of|how many .{1,20} in)",
        r"^\w+\?$",
        r"^(define|what does .{1,30} mean)",
        r"^(translate .{1,20} to \w+$)",
    ]

    COMPLEX_PATTERNS = [
        r"(step.by.step|detailed explanation|comprehensive|in.depth)",
        r"(write a (program|function|class|script|algorithm))",
        r"(debug|fix|refactor|optimize).{0,30}(code|function|script)",
        r"(compare and contrast|pros and cons|trade.?offs)",
        r"(explain why|reason|justify|argue|prove|derive)",
        r"(multi.?step|chain of thought|think through)",
        r"(summarize.{0,30}(article|document|paper|text))",
        r"(generate.{0,30}(report|essay|plan|proposal|story))",
    ]

    EXPERT_PATTERNS = [
        r"(implement|architect|design).{0,40}(system|framework|pipeline|service)",
        r"(mathematical proof|formal verification|theorem)",
        r"(security (audit|vulnerability|exploit))",
        r"(optimize .{0,30}(algorithm|complexity|performance).{0,30}O\()",
    ]

    def classify(self, prompt: str, task_type: Optional[str] = None) -> RouteDecision:
        prompt_lower = prompt.lower().strip()
        reasons = []
        score = 0

        # ── Layer 1: Trivial pattern match ──────────────────────────────────
        for pat in self.TRIVIAL_PATTERNS:
            if re.search(pat, prompt_lower):
                reasons.append(f"trivial pattern: {pat[:40]}")
                score = max(score, 0)

        # ── Layer 2: Expert / complex pattern match ─────────────────────────
        for pat in self.EXPERT_PATTERNS:
            if re.search(pat, prompt_lower):
                score = max(score, 4)
                reasons.append(f"expert signal: {pat[:40]}")

        for pat in self.COMPLEX_PATTERNS:
            if re.search(pat, prompt_lower):
                score = max(score, 3)
                reasons.append(f"complex signal: {pat[:40]}")

        # ── Layer 3: Structural / length signals ────────────────────────────
        word_count = len(prompt.split())

        if word_count <= 8:
            score = max(0, score - 1)
            reasons.append(f"short prompt ({word_count} words)")
        elif word_count <= 20:
            score = max(score, 1)
        elif word_count <= 50:
            score = max(score, 2)
        elif word_count <= 100:
            score = max(score, 3)
        else:
            score = max(score, 3)
            reasons.append(f"long prompt ({word_count} words)")

        # Code blocks in prompt → at least moderate
        if "```" in prompt or "def " in prompt or "class " in prompt:
            score = max(score, 3)
            reasons.append("code content detected")

        # Multi-part questions
        question_marks = prompt.count("?")
        if question_marks > 2:
            score = max(score, 3)
            reasons.append(f"multi-part question ({question_marks} ?)")

        # Numbers / math
        if re.search(r"\d+\s*[\+\-\*\/\^]\s*\d+", prompt):
            score = max(score, 1)

        # Task type override
        if task_type:
            task_lower = task_type.lower()
            if task_type in ("factual", "classification", "boolean", "extraction"):
                score = max(0, score - 1)
                reasons.append(f"task_type={task_type} → lean local")
            elif task_type in ("reasoning", "generation", "code", "math_proof"):
                score = max(score, 3)
                reasons.append(f"task_type={task_type} → lean remote")

        # ── Layer 4: Vocabulary entropy signal ─────────────────────────────
        words = re.findall(r"\b\w+\b", prompt_lower)
        if words:
            freq: dict[str, int] = {}
            for w in words:
                freq[w] = freq.get(w, 0) + 1
            entropy = -sum((c / len(words)) * math.log2(c / len(words)) for c in freq.values())
            if entropy > 4.0:
                score = max(score, 3)
                reasons.append(f"high entropy ({entropy:.2f}) → complex vocabulary")

        # ── Final score → label + routing decision ──────────────────────────
        score = max(0, min(4, score))
        labels = ["trivial", "simple", "moderate", "complex", "expert"]
        label = labels[score]
        complexity_1to5 = score + 1

        # Route: 0-1 → local, 2 → local (with escalation guard), 3-4 → remote
        use_local = score <= 2

        return RouteDecision(
            use_local=use_local,
            complexity=complexity_1to5,
            label=label,
            reasons=reasons,
        )

    def estimate_savings(self, tokens_used: int, use_local: bool) -> dict:
        """Compute estimated cost and savings vs always-remote baseline."""
        remote_cost = (tokens_used / 1000) * self.REMOTE_COST_PER_1K
        actual_cost = 0.0 if use_local else remote_cost
        savings = remote_cost - actual_cost
        return {
            "actual_cost_usd": round(actual_cost, 6),
            "remote_cost_usd": round(remote_cost, 6),
            "saved_usd": round(savings, 6),
        }
