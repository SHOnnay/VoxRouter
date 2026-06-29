"""
Scorer — evaluates benchmark results on two axes:
  1. Accuracy: did the model answer correctly?
  2. Routing correctness: did the router make the right call?

VoxRouter Score = (accuracy_pct * 0.5) + (routing_pct * 0.3) + (token_savings_pct * 0.2)
"""

from typing import List, Dict


def score_answer(answer: str, ground_truth: str, method: str) -> bool:
    """Check if an answer is correct given the scoring method."""
    answer_lower = answer.lower().strip()
    truth_lower = ground_truth.lower().strip()

    if method == "exact":
        return answer_lower == truth_lower

    elif method == "contains":
        return truth_lower in answer_lower

    elif method == "code_runs":
        # For code tasks we just check it contains a function/class definition
        return "def " in answer_lower or "class " in answer_lower or "#include" in answer_lower

    elif method == "semantic":
        # Fallback to contains for now
        return truth_lower in answer_lower

    return False


def compute_voxrouter_score(results: List[Dict]) -> Dict:
    """
    Compute the VoxRouter Score from benchmark results.

    VoxRouter Score = (accuracy * 0.5) + (routing_accuracy * 0.3) + (token_savings * 0.2)

    - accuracy:         % of tasks answered correctly
    - routing_accuracy: % of tasks routed as expected (local vs remote)
    - token_savings:    % of tokens saved vs always-remote baseline
    """
    if not results:
        return _empty_score()

    total = len(results)

    # ── Accuracy ──────────────────────────────────────────────────────────
    correct = sum(1 for r in results if r.get("answer_correct", False))
    accuracy_pct = (correct / total) * 100

    # ── Routing accuracy ──────────────────────────────────────────────────
    route_correct = sum(1 for r in results if r.get("route_correct", False))
    routing_pct = (route_correct / total) * 100

    # ── Token savings ─────────────────────────────────────────────────────
    # Baseline: every task goes to remote (use avg remote token count)
    REMOTE_TOKEN_ESTIMATE = 200   # conservative avg tokens if all went remote
    baseline_tokens = total * REMOTE_TOKEN_ESTIMATE
    actual_tokens = sum(r.get("tokens_used", REMOTE_TOKEN_ESTIMATE) for r in results)
    token_savings_pct = max(0, ((baseline_tokens - actual_tokens) / baseline_tokens) * 100)

    # ── VoxRouter Score ───────────────────────────────────────────────────
    voxrouter_score = (
        (accuracy_pct * 0.5) +
        (routing_pct * 0.3) +
        (token_savings_pct * 0.2)
    )

    # ── Per-tier breakdown ────────────────────────────────────────────────
    tiers = ["trivial", "simple", "moderate", "complex", "expert"]
    tier_breakdown = {}
    for tier in tiers:
        tier_results = [r for r in results if r.get("tier") == tier]
        if tier_results:
            t_correct = sum(1 for r in tier_results if r.get("answer_correct", False))
            t_route = sum(1 for r in tier_results if r.get("route_correct", False))
            t_tokens = sum(r.get("tokens_used", 0) for r in tier_results)
            tier_breakdown[tier] = {
                "total": len(tier_results),
                "accuracy_pct": round((t_correct / len(tier_results)) * 100, 1),
                "routing_pct": round((t_route / len(tier_results)) * 100, 1),
                "total_tokens": t_tokens,
                "avg_tokens": round(t_tokens / len(tier_results), 1),
            }

    # ── Local vs remote split ─────────────────────────────────────────────
    local_count  = sum(1 for r in results if r.get("route") == "local")
    remote_count = total - local_count
    escalated    = sum(1 for r in results if r.get("escalated", False))

    return {
        "voxrouter_score": round(voxrouter_score, 2),
        "accuracy_pct": round(accuracy_pct, 1),
        "routing_pct": round(routing_pct, 1),
        "token_savings_pct": round(token_savings_pct, 1),
        "total_tasks": total,
        "correct_answers": correct,
        "correct_routes": route_correct,
        "local_tasks": local_count,
        "remote_tasks": remote_count,
        "escalated_tasks": escalated,
        "actual_tokens": actual_tokens,
        "baseline_tokens": baseline_tokens,
        "tokens_saved": baseline_tokens - actual_tokens,
        "tier_breakdown": tier_breakdown,
    }


def _empty_score() -> Dict:
    return {
        "voxrouter_score": 0.0,
        "accuracy_pct": 0.0,
        "routing_pct": 0.0,
        "token_savings_pct": 0.0,
        "total_tasks": 0,
        "correct_answers": 0,
        "correct_routes": 0,
        "local_tasks": 0,
        "remote_tasks": 0,
        "escalated_tasks": 0,
        "actual_tokens": 0,
        "baseline_tokens": 0,
        "tokens_saved": 0,
        "tier_breakdown": {},
    }
