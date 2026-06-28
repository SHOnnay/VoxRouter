# VoxRouter — Hybrid Token-Efficient Routing Agent

> Route every AI task to the cheapest model that can handle it.  
> Local when possible. Remote when necessary. Always efficient.

![Dashboard](./docs/dashboard.png)

![Stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20Ollama%20%7C%20Fireworks%20AI%20%7C%20React-22c55e?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-blue?style=for-the-badge)
![Containerized](https://img.shields.io/badge/containerized-Docker%20Compose-blue?style=for-the-badge&logo=docker)

---

## What is VoxRouter?

VoxRouter is an intelligent routing middleware that processes each task and decides **in real time** whether to use:

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

## Development (without Docker)

### Backend

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env
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
# Install from https://ollama.ai
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

| Decision | Points |
|----------|--------|
| Trivial/simple task → local | +10 |
| Complex/expert task → remote | +10 |
| Trivial task → remote (wasted) | +3 |
| Complex task → local (risky) | +4 |
| Moderate task → either | +7 |

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

## Roadmap

- [ ] Benchmark mode — 50-task eval suite with VoxRouter Score
- [ ] Streaming — real-time token streaming to dashboard
- [ ] SDK — `pip install voxrouter` drop-in routing layer
- [ ] Budget enforcement — aggressive local routing as token budget depletes
- [ ] Multi-agent chain — break expert tasks into routed subtasks

---

## Built With

- [FastAPI](https://fastapi.tiangolo.com) — async Python backend
- [Ollama](https://ollama.ai) — local model runtime with AMD ROCm support
- [Fireworks AI](https://fireworks.ai) — remote model API
- [React](https://react.dev) + [Recharts](https://recharts.org) — live dashboard
- [Docker Compose](https://docs.docker.com/compose) — single-command deployment
