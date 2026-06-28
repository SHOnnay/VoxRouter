from pydantic import BaseModel, Field
from typing import Optional, List


class TaskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    task_type: Optional[str] = Field(
        None,
        description="Hint for router: factual | classification | boolean | extraction | reasoning | generation | code | math_proof",
    )
    force_local: bool = Field(False, description="Skip escalation – stay local no matter what")
    force_remote: bool = Field(False, description="Skip local – go remote immediately")


class BatchTask(BaseModel):
    prompt: str
    task_type: Optional[str] = None


class BatchRequest(BaseModel):
    tasks: List[BatchTask] = Field(..., max_length=50)


class TaskResponse(BaseModel):
    task_id: str
    prompt: str
    task_type: Optional[str]
    answer: str
    model_used: str
    route: str                    # "local" | "remote"
    escalated: bool
    escalation_reason: Optional[str]
    complexity_score: int         # 1-5
    complexity_label: str         # trivial | simple | moderate | complex | expert
    tokens_used: int
    tokens_saved: float           # USD saved vs always-remote
    cost_usd: float
    latency_ms: float
    confidence: float
    timestamp: float


class StatsResponse(BaseModel):
    total_tasks: int
    local_tasks: int
    remote_tasks: int
    escalated_tasks: int
    local_pct: float
    total_tokens: int
    total_cost_usd: float
    total_saved_usd: float
    avg_latency_ms: float
    avg_confidence: float
    token_efficiency_score: float  # 0-100: higher = better routing
    complexity_distribution: dict
