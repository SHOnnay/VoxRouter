# VoxRouter — Hybrid Token-Efficient Routing Agent

> **AMD Developer Hackathon ACT II · Track 1**
> Build an AI agent that completes tasks using the fewest tokens possible.

![VoxRouter Dashboard](https://img.shields.io/badge/track-1%20hybrid%20routing-ED1C24?style=for-the-badge&logo=amd)
![Stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20Ollama%20%7C%20Fireworks%20AI%20%7C%20React-22c55e?style=for-the-badge)
![Containerized](https://img.shields.io/badge/containerized-Docker%20Compose-blue?style=for-the-badge&logo=docker)

---

## What is VoxRouter?

VoxRouter is an intelligent routing agent that processes each task and decides **in real time** whether to use:

- **Local model** via Ollama (AMD ROCm) — zero API cost, sub-100ms for simple tasks
- **Remote model** via Fireworks AI — high capability, reserved for complex tasks

The router maximizes token efficiency while keeping output accuracy above threshold.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        VoxRouter                            │
│                                                             │
│   Task In ──► RouterEngine ──► Complexity 1-5              │
│                   │                                         │
│              ┌────┴────┐                                    │
│           Score ≤2   Score ≥3                               │
│              │           │                                  │
│         Local Model   Remote Model                          │
│         (Ollama/ROCm) (Fireworks AI)                        │
│              │           │                                  │
│         Confidence   Confidence                             │
│         Check < 0.72?    │                                  │
│              │           │                                  │
│         Escalate ────────┘                                  │
│              │                                              │
│          Answer + Metrics ──► Dashboard                     │
└─────────────────────────────────────────────────────────────┘
```

### Routing Logic (4 Layers)

| Layer | Method | Signal |
|-------|--------|--------|
| 1 | Rule patterns | Trivial regex (capital of, yes/no, basic math) |
| 2 | Keyword signals | Complex vocabulary: "implement", "architect", "debug" |
| 3 | Structural analysis | Word count, code blocks, question count, prompt entropy |
| 4 | Confidence escalation | If local confidence < 0.72, escalate to remote |

### Local Models (AMD ROCm via Ollama)

| Complexity | Model | Size | Use Case |
|-----------|-------|------|----------|
| Trivial (1) | `llama3.2:1b` | ~800MB | Single-fact, yes/no, arithmetic |
| Simple (2) | `qwen2.5:3b` | ~1.9GB | Short reasoning, classification |
| Moderate (3) | `phi3.5:3.8b` | ~2.2GB | Summaries, short code |

### Remote Models (Fireworks AI)

| Complexity | Model | Use Case |
|-----------|-------|----------|
| Complex (4) | `mixtral-8x7b-instruct` | Multi-step reasoning |
| Expert (5) | `llama-v3p3-70b-instruct` | System design, proofs |

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- AMD GPU with ROCm support (or CPU fallback)
- Fireworks AI API key ([get one here](https://fireworks.ai))

### 1. Clone and configure

```bash
git clone https://github.com/SHOnnay/voxrouter
cd voxrouter

cp .env.example .env
# Edit .env and set your FIREWORKS_API_KEY
```

### 2. Launch the full stack

```bash
docker compose up --build
```

This will:
- Start Ollama with ROCm GPU support
- Pull the three local models automatically
- Start the FastAPI backend
- Build and serve the React dashboard

### 3. Open the dashboard

```
http://localhost:3000
```

### 4. Try it via API

```bash
# Single task
curl -X POST http://localhost:8000/api/task \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?", "task_type": "factual"}'

# Batch tasks
curl -X POST http://localhost:8000/api/batch \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {"prompt": "Is 17 a prime number?", "task_type": "boolean"},
      {"prompt": "Write a binary search function in Python.", "task_type": "code"}
    ]
  }'

# Stats
curl http://localhost:8000/api/stats
```

---

## Development (no Docker)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Local models (Ollama)

```bash
# Install: https://ollama.ai
ollama serve
ollama pull llama3.2:1b
ollama pull qwen2.5:3b
ollama pull phi3.5:3.8b
```

---

## API Reference

### `POST /api/task`

Route and execute a single task.

```json
{
  "prompt": "string (required)",
  "task_type": "factual | boolean | classification | extraction | reasoning | generation | code | math_proof",
  "force_local": false,
  "force_remote": false
}
```

**Response:**
```json
{
  "task_id": "a3f8c2d1",
  "answer": "Paris",
  "model_used": "local/llama3.2:1b",
  "route": "local",
  "escalated": false,
  "complexity_score": 1,
  "complexity_label": "trivial",
  "tokens_used": 42,
  "tokens_saved": 0.0084,
  "cost_usd": 0.0,
  "latency_ms": 87.3,
  "confidence": 0.91,
  "timestamp": 1719500000.0
}
```

### `POST /api/batch`

Process up to 50 tasks in parallel.

### `GET /api/stats`

Aggregated routing statistics including token efficiency score.

### `GET /api/history?limit=50`

Recent task history.

### `GET /api/stream`

Server-Sent Events live feed of tasks as they complete.

---

## Token Efficiency Score

The efficiency score (0–100) rewards optimal routing:

- ✅ +10 pts: Trivial/simple task → local model
- ✅ +10 pts: Complex/expert task → remote model
- ⚠️ +3 pts: Trivial task → remote model (wasted credits)
- ⚠️ +4 pts: Complex task → local model (risky accuracy)
- ➡️ +7 pts: Moderate task → either model

---

## Project Structure

```
voxrouter/
├── backend/
│   ├── main.py              # FastAPI app, routing endpoints
│   ├── router/
│   │   └── core.py          # RouterEngine (4-layer complexity classifier)
│   ├── models/
│   │   ├── fireworks.py     # Fireworks AI remote client
│   │   └── local.py         # Ollama local client
│   ├── api/
│   │   └── schemas.py       # Pydantic request/response schemas
│   ├── tasks/
│   │   └── store.py         # In-memory task store + stats
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main dashboard
│   │   ├── App.css          # Design system
│   │   ├── lib/api.js       # API client
│   │   └── hooks/useStats.js
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Built With

- **FastAPI** — async Python backend
- **Ollama** — local model runtime with AMD ROCm support
- **Fireworks AI** — remote model API (Llama, Mixtral on AMD hardware)
- **React + Recharts** — live dashboard
- **Docker Compose** — single-command deployment

---

## AMD ACT II · Track 1 Submission

**Team:** SHOnnay  
**Track:** Track 1 — Hybrid Token-Efficient Routing Agent  
**Approach:** Multi-layer complexity classifier + confidence-based escalation  
**Judged on:** Token count and output accuracy
