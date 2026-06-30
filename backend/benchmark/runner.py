"""
BenchmarkRunner — orchestrates the full 50-task eval suite.
Runs tasks in parallel batches, scores each result, returns full report.
"""

import asyncio
import time
from typing import List, Dict, Optional, Callable

from benchmark.suite import SUITE
from benchmark.scorer import score_answer, compute_voxrouter_score


class BenchmarkRunner:
    def __init__(self, router, local_client, fireworks_client):
        self.router = router
        self.local = local_client
        self.fireworks = fireworks_client

    async def run(
        self,
        task_ids: Optional[List[str]] = None,
        concurrency: int = 2,
        progress_callback: Optional[Callable] = None,
    ) -> Dict:
        tasks = SUITE if not task_ids else [t for t in SUITE if t["id"] in task_ids]
        start_ts = time.time()

        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(task, index):
            async with semaphore:
                # Small stagger between remote-bound tasks to avoid bursting rate limits
                if index > 0:
                    await asyncio.sleep(0.3)
                result = await self._run_task(task)
                if progress_callback:
                    try:
                        await progress_callback(result)
                    except Exception:
                        pass
                return result

        results = await asyncio.gather(*[run_one(t, i) for i, t in enumerate(tasks)], return_exceptions=True)

        # Filter out exceptions — treat them as errors
        clean_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                clean_results.append({
                    **tasks[i],
                    "answer": f"ERROR: {str(r)}",
                    "route": "error",
                    "escalated": False,
                    "tokens_used": 0,
                    "cost_usd": 0.0,
                    "latency_ms": 0.0,
                    "confidence": 0.0,
                    "answer_correct": False,
                    "route_correct": False,
                    "error": str(r),
                })
            else:
                clean_results.append(r)

        elapsed = round(time.time() - start_ts, 2)
        score = compute_voxrouter_score(clean_results)
        score["elapsed_seconds"] = elapsed
        score["results"] = clean_results

        return score

    async def _run_task(self, task: Dict) -> Dict:
        start = time.time()

        # Route decision
        decision = self.router.classify(task["prompt"], task["task_type"])

        try:
            if decision.use_local:
                model_result = await self.local.complete(task["prompt"], decision)
                model_result.escalated = False
                if model_result.confidence < self.router.CONFIDENCE_THRESHOLD:
                    decision.use_local = False
                    decision.escalation_reason = f"Low confidence ({model_result.confidence:.2f})"
                    model_result = await self.fireworks.complete(task["prompt"], decision)
                    model_result.escalated = True
            else:
                model_result = await self.fireworks.complete(task["prompt"], decision)
                model_result.escalated = False

        except Exception as e:
            return {
                **task,
                "answer": f"ERROR: {str(e)}",
                "route": "error",
                "escalated": False,
                "tokens_used": 0,
                "cost_usd": 0.0,
                "latency_ms": 0.0,
                "confidence": 0.0,
                "answer_correct": False,
                "route_correct": False,
                "error": str(e),
            }

        actual_route = "local" if (decision.use_local and not model_result.escalated) else "remote"
        latency = round((time.time() - start) * 1000, 1)

        # Skip accuracy scoring for demo responses or transient API failures —
        # only score routing for these, since the answer was never actually generated
        is_demo = any(marker in model_result.answer for marker in (
            "[DEMO]", "[LOCAL DEMO]", "[RATE LIMITED]", "[GEMINI ERROR", "ERROR:"
        ))
        if is_demo:
            answer_correct = None   # None = not scored (demo mode)
        else:
            answer_correct = score_answer(
                model_result.answer,
                task["ground_truth"],
                task["score_method"],
            )

        route_correct = actual_route == task["expected_route"]

        return {
            "id": task["id"],
            "tier": task["tier"],
            "prompt": task["prompt"],
            "task_type": task["task_type"],
            "answer": model_result.answer,
            "ground_truth": task["ground_truth"],
            "model_used": model_result.model_name,
            "route": actual_route,
            "expected_route": task["expected_route"],
            "escalated": model_result.escalated,
            "escalation_reason": decision.escalation_reason,
            "complexity_score": decision.complexity,
            "complexity_label": decision.label,
            "tokens_used": model_result.tokens_used,
            "cost_usd": model_result.cost_usd,
            "latency_ms": latency,
            "confidence": model_result.confidence,
            "answer_correct": answer_correct,
            "route_correct": route_correct,
            "is_demo": is_demo,
        }