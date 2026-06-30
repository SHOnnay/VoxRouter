"""
Scorer — evaluates benchmark results on two axes:
  1. Accuracy:         did the model answer correctly? (skipped for demo responses)
  2. Routing accuracy: did the router make the right LOCAL vs REMOTE call?

VoxRouter Score = (accuracy_pct * 0.5) + (routing_pct * 0.3) + (token_savings_pct * 0.2)

Note: In demo mode (no API key), accuracy is not scored — only routing and token savings count.
The score displayed will note if accuracy was partially skipped.
"""

from typing import List, Dict


def score_answer(answer: str, ground_truth: str, method: str) -> bool:
    answer_lower = answer.lower().strip()
    truth_lower  = ground_truth.lower().strip()

    if method == "exact":
        return answer_lower == truth_lower
    elif method == "contains":
        return truth_lower in answer_lower
    elif method == "code_runs":
        return "def " in answer_lower or "class " in answer_lower or "#include" in answer_lower
    elif method == "semantic":
        return truth_lower in answer_lower
    return False


def compute_voxrouter_score(results: List[Dict]) -> Dict:
    if not results:
        return _empty_score()

    total = len(results)

    # ── Routing accuracy (always scored) ─────────────────────────────────
    route_correct  = sum(1 for r in results if r.get("route_correct", False))
    routing_pct    = (route_correct / total) * 100

    # ── Accuracy (only scored for non-demo results) ───────────────────────
    scored_results = [r for r in results if r.get("answer_correct") is not None]
    if scored_results:
        correct      = sum(1 for r in scored_results if r.get("answer_correct", False))
        accuracy_pct = (correct / len(scored_results)) * 100
    else:
        correct      = 0
        accuracy_pct = 0.0

    demo_count = sum(1 for r in results if r.get("is_demo", False))
    demo_mode  = demo_count > 0

    # ── Token savings ─────────────────────────────────────────────────────
    REMOTE_TOKEN_ESTIMATE = 200
    baseline_tokens = total * REMOTE_TOKEN_ESTIMATE
    actual_tokens   = sum(r.get("tokens_used", REMOTE_TOKEN_ESTIMATE) for r in results)
    token_savings_pct = max(0, ((baseline_tokens - actual_tokens) / baseline_tokens) * 100)

    # ── VoxRouter Score ───────────────────────────────────────────────────
    # In demo mode: weight shifts — routing + savings matter more
    if demo_mode and not scored_results:
        voxrouter_score = (routing_pct * 0.6) + (token_savings_pct * 0.4)
    else:
        voxrouter_score = (
            (accuracy_pct   * 0.5) +
            (routing_pct    * 0.3) +
            (token_savings_pct * 0.2)
        )

    # ── Per-tier breakdown ────────────────────────────────────────────────
    tiers = ["trivial", "simple", "moderate", "complex", "expert"]
    tier_breakdown = {}
    for tier in tiers:
        tier_results = [r for r in results if r.get("tier") == tier]
        if not tier_results:
            continue
        t_scored  = [r for r in tier_results if r.get("answer_correct") is not None]
        t_correct = sum(1 for r in t_scored if r.get("answer_correct", False))
        t_route   = sum(1 for r in tier_results if r.get("route_correct", False))
        t_tokens  = sum(r.get("tokens_used", 0) for r in tier_results)
        tier_breakdown[tier] = {
            "total":        len(tier_results),
            "accuracy_pct": round((t_correct / len(t_scored)) * 100, 1) if t_scored else None,
            "routing_pct":  round((t_route / len(tier_results)) * 100, 1),
            "total_tokens": t_tokens,
            "avg_tokens":   round(t_tokens / len(tier_results), 1),
            "demo_tasks":   sum(1 for r in tier_results if r.get("is_demo", False)),
        }

    local_count  = sum(1 for r in results if r.get("route") == "local")
    remote_count = total - local_count
    escalated    = sum(1 for r in results if r.get("escalated", False))
    errors       = sum(1 for r in results if r.get("route") == "error")

    return {
        "voxrouter_score":    round(voxrouter_score, 2),
        "accuracy_pct":       round(accuracy_pct, 1),
        "routing_pct":        round(routing_pct, 1),
        "token_savings_pct":  round(token_savings_pct, 1),
        "total_tasks":        total,
        "scored_tasks":       len(scored_results),
        "demo_tasks":         demo_count,
        "correct_answers":    correct,
        "correct_routes":     route_correct,
        "local_tasks":        local_count,
        "remote_tasks":       remote_count,
        "escalated_tasks":    escalated,
        "error_tasks":        errors,
        "actual_tokens":      actual_tokens,
        "baseline_tokens":    baseline_tokens,
        "tokens_saved":       baseline_tokens - actual_tokens,
        "demo_mode":          demo_mode,
        "tier_breakdown":     tier_breakdown,
    }


def _empty_score() -> Dict:
    return {
        "voxrouter_score": 0.0, "accuracy_pct": 0.0, "routing_pct": 0.0,
        "token_savings_pct": 0.0, "total_tasks": 0, "scored_tasks": 0,
        "demo_tasks": 0, "correct_answers": 0, "correct_routes": 0,
        "local_tasks": 0, "remote_tasks": 0, "escalated_tasks": 0,
        "error_tasks": 0, "actual_tokens": 0, "baseline_tokens": 0,
        "tokens_saved": 0, "demo_mode": False, "tier_breakdown": {},
    }
