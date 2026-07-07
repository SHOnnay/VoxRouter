"""
VoxRouter – Hybrid Token-Efficient Routing Agent
AMD Developer Hackathon ACT II – Track 1
"""
from dotenv import load_dotenv
load_dotenv()
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
from models.gemini import GeminiClient
from api.schemas import TaskRequest, TaskResponse, BatchRequest, StatsResponse
from tasks.store import TaskStore
from benchmark.runner import BenchmarkRunner
from benchmark.suite import SUITE

# ── Startup / Shutdown ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.task_store = TaskStore()
    app.state.router = RouterEngine()
    app.state.local = LocalModelClient()

    # Auto-select remote provider: Fireworks → Gemini → demo
    fireworks = FireworksClient()
    gemini    = GeminiClient()

    import os
    provider = os.getenv("REMOTE_PROVIDER", "auto").lower()

    if provider == "gemini" or (provider == "auto" and not os.getenv("FIREWORKS_API_KEY") and os.getenv("GEMINI_API_KEY")):
        app.state.fireworks = gemini
        print(f"🤖 Remote provider: Gemini 2.5 Flash")
    else:
        app.state.fireworks = fireworks
        print(f"🤖 Remote provider: Fireworks AI")

    app.state.benchmark_store = {}
    app.state.benchmark_progress = {}
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


# ── Streaming Endpoint ────────────────────────────────────────────────────────
@app.get("/api/task/stream")
async def stream_task(prompt: str, task_type: str = None):
    """
    Route a task and stream the answer as tokens arrive (SSE).
    Same routing logic as /api/task, but the response streams live
    instead of waiting for the full generation to finish.
    """
    store: TaskStore = app.state.task_store
    router: RouterEngine = app.state.router
    fireworks: FireworksClient = app.state.fireworks
    local: LocalModelClient = app.state.local

    task_id = str(uuid.uuid4())[:8]
    start_ts = time.time()
    route_decision = router.classify(prompt, task_type)

    async def event_generator():
        # Send the routing decision immediately so the UI can show it before tokens arrive
        yield f"data: {json.dumps({'type': 'route', 'task_id': task_id, 'complexity_score': route_decision.complexity, 'complexity_label': route_decision.label, 'route': 'local' if route_decision.use_local else 'remote'})}\n\n"

        final_result = None
        escalated = False

        if route_decision.use_local:
            # Buffer local stream so we can check confidence before committing to "local" in the UI
            buffered_tokens = []
            async for chunk in local.stream(prompt, route_decision):
                if chunk["type"] == "token":
                    buffered_tokens.append(chunk["text"])
                elif chunk["type"] == "done":
                    final_result = chunk["result"]

            if final_result and final_result.confidence < router.CONFIDENCE_THRESHOLD:
                # Escalate — discard local buffer, stream remote instead
                escalated = True
                route_decision.use_local = False
                route_decision.escalation_reason = f"Low confidence ({final_result.confidence:.2f}) → escalating to remote"
                yield f"data: {json.dumps({'type': 'escalate', 'reason': route_decision.escalation_reason})}\n\n"

                async for chunk in fireworks.stream(prompt, route_decision):
                    if chunk["type"] == "token":
                        yield f"data: {json.dumps({'type': 'token', 'text': chunk['text']})}\n\n"
                    elif chunk["type"] == "done":
                        final_result = chunk["result"]
                        final_result.escalated = True
            else:
                # Confidence was fine — replay the buffered local tokens to the client
                for text in buffered_tokens:
                    yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"
                if final_result:
                    final_result.escalated = False
        else:
            async for chunk in fireworks.stream(prompt, route_decision):
                if chunk["type"] == "token":
                    yield f"data: {json.dumps({'type': 'token', 'text': chunk['text']})}\n\n"
                elif chunk["type"] == "done":
                    final_result = chunk["result"]
                    final_result.escalated = False

        if not final_result:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No result generated'})}\n\n"
            return

        elapsed = round((time.time() - start_ts) * 1000, 1)
        actual_route = "local" if (route_decision.use_local and not final_result.escalated) else "remote"

        task_record = TaskResponse(
            task_id=task_id,
            prompt=prompt,
            task_type=task_type,
            answer=final_result.answer,
            model_used=final_result.model_name,
            route=actual_route,
            escalated=final_result.escalated,
            escalation_reason=route_decision.escalation_reason,
            complexity_score=route_decision.complexity,
            complexity_label=route_decision.label,
            tokens_used=final_result.tokens_used,
            tokens_saved=final_result.tokens_saved,
            cost_usd=final_result.cost_usd,
            latency_ms=elapsed,
            confidence=final_result.confidence,
            timestamp=time.time(),
        )
        store.add(task_record)

        yield f"data: {json.dumps({'type': 'done', 'task': task_record.model_dump()})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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


# ── Benchmark Endpoint ───────────────────────────────────────────────────────
@app.post("/api/benchmark/run")
async def run_benchmark(background_tasks: BackgroundTasks, tier: str = "all"):
    """
    Start a benchmark run. Returns a run_id immediately.
    Poll /api/benchmark/{run_id} for progress and results.
    """
    run_id = str(uuid.uuid4())[:8]
    app.state.benchmark_store[run_id] = {"status": "running", "run_id": run_id}
    app.state.benchmark_progress[run_id] = []

    task_ids = None
    if tier != "all":
        task_ids = [t["id"] for t in SUITE if t["tier"] == tier]

    async def _run():
        runner = BenchmarkRunner(
            app.state.router,
            app.state.local,
            app.state.fireworks,
        )

        async def on_progress(result):
            app.state.benchmark_progress[run_id].append(result)

        try:
            report = await runner.run(
                task_ids=task_ids,
                concurrency=2,
                progress_callback=on_progress,
            )
            app.state.benchmark_store[run_id] = {
                "status": "complete",
                "run_id": run_id,
                **report,
            }
        except Exception as e:
            app.state.benchmark_store[run_id] = {
                "status": "error",
                "run_id": run_id,
                "error": str(e),
            }

    background_tasks.add_task(_run)
    return {"run_id": run_id, "status": "running", "total_tasks": len(task_ids or SUITE)}


@app.get("/api/benchmark/{run_id}")
async def get_benchmark(run_id: str):
    """Get benchmark results or current progress."""
    result = app.state.benchmark_store.get(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    progress = app.state.benchmark_progress.get(run_id, [])
    return {**result, "completed_tasks": len(progress), "progress": progress[-5:]}


@app.get("/api/benchmark/{run_id}/stream")
async def stream_benchmark(run_id: str):
    """SSE stream of benchmark task completions."""
    async def generator():
        last_idx = 0
        while True:
            progress = app.state.benchmark_progress.get(run_id, [])
            store = app.state.benchmark_store.get(run_id, {})

            while last_idx < len(progress):
                yield f"data: {json.dumps({'type': 'task', 'task': progress[last_idx]})}\n\n"
                last_idx += 1

            if store.get("status") in ("complete", "error"):
                yield f"data: {json.dumps({'type': 'complete', 'report': store})}\n\n"
                break

            await asyncio.sleep(0.3)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get("/api/benchmark")
async def list_benchmarks():
    """List all benchmark runs."""
    runs = []
    for run_id, data in app.state.benchmark_store.items():
        runs.append({
            "run_id": run_id,
            "status": data.get("status"),
            "voxrouter_score": data.get("voxrouter_score"),
            "accuracy_pct": data.get("accuracy_pct"),
            "token_savings_pct": data.get("token_savings_pct"),
            "total_tasks": data.get("total_tasks"),
            "elapsed_seconds": data.get("elapsed_seconds"),
        })
    return {"runs": sorted(runs, key=lambda x: x["run_id"], reverse=True)}


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}