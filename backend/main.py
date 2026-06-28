"""
VoxRouter – Hybrid Token-Efficient Routing Agent
AMD Developer Hackathon ACT II – Track 1
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
import asyncio
import json
import time
import uuid

from router.core import RouterEngine
from models.fireworks import FireworksClient
from models.local import LocalModelClient
from api.schemas import TaskRequest, TaskResponse, BatchRequest, StatsResponse
from tasks.store import TaskStore

# ── Startup / Shutdown ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.task_store = TaskStore()
    app.state.router = RouterEngine()
    app.state.fireworks = FireworksClient()
    app.state.local = LocalModelClient()
    print("✅ VoxRouter ready")
    yield
    print("👋 VoxRouter shutting down")

app = FastAPI(
    title="VoxRouter",
    description="Hybrid Token-Efficient Routing Agent for AMD Hackathon ACT II",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Core Routing Endpoint ─────────────────────────────────────────────────────
@app.post("/api/task", response_model=TaskResponse)
async def process_task(req: TaskRequest):
    """
    Main entry point. Routes each task to local or remote model
    based on complexity analysis and token budget.
    """
    store: TaskStore = app.state.task_store
    router: RouterEngine = app.state.router
    fireworks: FireworksClient = app.state.fireworks
    local: LocalModelClient = app.state.local

    task_id = str(uuid.uuid4())[:8]
    start_ts = time.time()

    # 1. Classify complexity
    route_decision = router.classify(req.prompt, req.task_type)

    # 2. Execute on chosen model
    if route_decision.use_local:
        result = await local.complete(req.prompt, route_decision)
        # 3. Confidence check – escalate if too uncertain
        if result.confidence < router.CONFIDENCE_THRESHOLD and not req.force_local:
            route_decision.use_local = False
            route_decision.escalation_reason = f"Low confidence ({result.confidence:.2f}) → escalating to remote"
            result = await fireworks.complete(req.prompt, route_decision)
            result.escalated = True
    else:
        result = await fireworks.complete(req.prompt, route_decision)
        result.escalated = False

    elapsed = round((time.time() - start_ts) * 1000, 1)

    task_record = TaskResponse(
        task_id=task_id,
        prompt=req.prompt,
        task_type=req.task_type,
        answer=result.answer,
        model_used=result.model_name,
        route="local" if route_decision.use_local and not result.escalated else "remote",
        escalated=result.escalated,
        escalation_reason=route_decision.escalation_reason,
        complexity_score=route_decision.complexity,
        complexity_label=route_decision.label,
        tokens_used=result.tokens_used,
        tokens_saved=result.tokens_saved,
        cost_usd=result.cost_usd,
        latency_ms=elapsed,
        confidence=result.confidence,
        timestamp=time.time(),
    )

    store.add(task_record)
    return task_record


# ── Batch Endpoint ────────────────────────────────────────────────────────────
@app.post("/api/batch")
async def process_batch(req: BatchRequest):
    """Process multiple tasks in parallel – used for hackathon eval runs."""
    tasks = [
        process_task(TaskRequest(prompt=t.prompt, task_type=t.task_type))
        for t in req.tasks
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        "results": [r if not isinstance(r, Exception) else {"error": str(r)} for r in results],
        "total": len(results),
        "succeeded": sum(1 for r in results if not isinstance(r, Exception)),
    }


# ── Stats Endpoint ────────────────────────────────────────────────────────────
@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    store: TaskStore = app.state.task_store
    return store.compute_stats()


# ── History Endpoint ──────────────────────────────────────────────────────────
@app.get("/api/history")
async def get_history(limit: int = 50):
    store: TaskStore = app.state.task_store
    return {"tasks": store.recent(limit)}


# ── SSE Live Feed ─────────────────────────────────────────────────────────────
@app.get("/api/stream")
async def stream_events():
    """Server-Sent Events for live dashboard updates."""
    store: TaskStore = app.state.task_store

    async def event_generator():
        last_count = 0
        while True:
            current = store.count()
            if current > last_count:
                tasks = store.recent(current - last_count)
                for t in tasks:
                    yield f"data: {json.dumps(t)}\n\n"
                last_count = current
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
