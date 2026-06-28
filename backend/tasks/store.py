"""
TaskStore – in-memory store for task results + stats.
Thread-safe enough for single-worker FastAPI with asyncio.
"""

from collections import defaultdict
from typing import List
import threading


class TaskStore:
    def __init__(self, max_size: int = 10_000):
        self._tasks: List[dict] = []
        self._max_size = max_size
        self._lock = threading.Lock()

    def add(self, task) -> None:
        record = task.model_dump()
        with self._lock:
            self._tasks.append(record)
            if len(self._tasks) > self._max_size:
                self._tasks = self._tasks[-self._max_size:]

    def recent(self, n: int = 50) -> List[dict]:
        with self._lock:
            return list(reversed(self._tasks[-n:]))

    def count(self) -> int:
        return len(self._tasks)

    def compute_stats(self) -> dict:
        with self._lock:
            tasks = list(self._tasks)

        if not tasks:
            return {
                "total_tasks": 0,
                "local_tasks": 0,
                "remote_tasks": 0,
                "escalated_tasks": 0,
                "local_pct": 0.0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "total_saved_usd": 0.0,
                "avg_latency_ms": 0.0,
                "avg_confidence": 0.0,
                "token_efficiency_score": 0.0,
                "complexity_distribution": {},
            }

        total = len(tasks)
        local_tasks  = sum(1 for t in tasks if t["route"] == "local")
        remote_tasks = total - local_tasks
        escalated    = sum(1 for t in tasks if t["escalated"])

        total_tokens  = sum(t["tokens_used"] for t in tasks)
        total_cost    = sum(t["cost_usd"] for t in tasks)
        total_saved   = sum(t["tokens_saved"] for t in tasks)
        avg_latency   = sum(t["latency_ms"] for t in tasks) / total
        avg_confidence = sum(t["confidence"] for t in tasks) / total

        complexity_dist: dict = defaultdict(int)
        for t in tasks:
            complexity_dist[t["complexity_label"]] += 1

        # Token efficiency score:
        # 100 = perfect (all trivial tasks went local, all expert tasks went remote)
        # Penalise remote use on low-complexity tasks and local use on high-complexity tasks
        efficiency_points = 0
        for t in tasks:
            c = t["complexity_score"]
            went_local = t["route"] == "local"
            if c <= 2 and went_local:
                efficiency_points += 10
            elif c <= 2 and not went_local:
                efficiency_points += 3   # wasted credits
            elif c >= 4 and not went_local:
                efficiency_points += 10
            elif c >= 4 and went_local:
                efficiency_points += 4   # risky – accuracy may suffer
            else:
                efficiency_points += 7   # moderate – acceptable either way

        max_points = total * 10
        efficiency_score = round((efficiency_points / max_points) * 100, 1) if max_points else 0.0

        return {
            "total_tasks": total,
            "local_tasks": local_tasks,
            "remote_tasks": remote_tasks,
            "escalated_tasks": escalated,
            "local_pct": round(local_tasks / total * 100, 1),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "total_saved_usd": round(total_saved, 6),
            "avg_latency_ms": round(avg_latency, 1),
            "avg_confidence": round(avg_confidence, 3),
            "token_efficiency_score": efficiency_score,
            "complexity_distribution": dict(complexity_dist),
        }
