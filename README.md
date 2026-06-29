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
- **Remote model** via Fireworks AI **or** Google Gemini — high capability, reserved for complex tasks

The remote provider is selectable with the `REMOTE_PROVIDER` env var (`fireworks` or `gemini`).

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

### Remote Models

Select the provider with `REMOTE_PROVIDER` (`fireworks` or `gemini`).

**Fireworks AI**

| Complexity | Model | Use Case |
|-----------|-------|----------|
| Complex (4) | `mixtral-8x7b-instruct` | Multi-step reasoning |
| Expert (5) | `llama-v3p3-70b-instruct` | System design, proofs |

**Google Gemini** (`REMOTE_PROVIDER=gemini`)

| Complexity | Model | Use Case |
|-----------|-------|----------|
| Complex / Expert (4–5) | `gemini-2.5-flash` | Multi-step reasoning, system design, proofs |

> **Heads up — free-tier quota.** On the Gemini free tier, `gemini-2.5-flash` is
> capped at **20 requests/day** per project. The 50-task benchmark sends ~30 tasks
> to the remote model, so a single benchmark run will exhaust the free quota and
> subsequent calls return HTTP 429. See [Remote Provider & Quota](#remote-provider--quota)
> and [Troubleshooting](#troubleshooting).

---

## Remote Provider & Quota

VoxRouter talks to whichever remote provider you set in `REMOTE_PROVIDER`:

| Provider | Env var | Get a key |
|----------|---------|-----------|
| Fireworks AI | `FIREWORKS_API_KEY` | https://fireworks.ai |
| Google Gemini | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

Set either key to `demo` to run that provider in offline demo mode (simulated responses, no network call).

### Gemini free-tier limits

| Model | Free-tier requests/day | Notes |
|-------|------------------------|-------|
| `gemini-2.5-flash` | ~20 | Low cap; a single benchmark run exhausts it |
| `gemini-2.5-flash-lite` | much higher | Good free-tier choice for the benchmark |
| `gemini-2.0-flash` | much higher | Alternative with a larger free daily cap |

To run the full benchmark on the free tier without hitting 429s, either:

1. **Switch model** — set `MODEL = "gemini-2.5-flash-lite"` in `backend/models/gemini.py`, or
2. **Enable billing** on your Google Cloud project (Tier 1) to lift the daily cap on `gemini-2.5-flash`.

> A valid Gemini API key starts with `AIza...`. Short-lived `AQ.*` tokens are
> ephemeral auth tokens, not API keys, and will expire.

### Resilient remote calls

The Gemini client (`backend/models/gemini.py`) is hardened so a bad remote response
never crashes the `/api/task` endpoint:

- API errors (invalid key, quota, bad request) return a readable `[REMOTE ERROR] ...`
  result instead of raising an unhandled exception (which would surface as HTTP 500).
- `429` rate-limit responses are retried with backoff using Gemini's suggested
  `retryDelay`; a persistent quota cap degrades gracefully.
- Thinking is disabled (`thinkingConfig.thinkingBudget = 0`) so the full
  `maxOutputTokens` budget goes to the answer rather than being consumed by
  internal reasoning tokens (which otherwise causes empty `MAX_TOKENS` responses).

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- AMD GPU with ROCm support (or CPU fallback)
- A remote provider API key — Fireworks AI ([get one](https://fireworks.ai)) **or** Google Gemini ([get one](https://aistudio.google.com/apikey))

### 1. Clone and configure

```bash
git clone https://github.com/SHOnnay/voxrouter
cd voxrouter

cp .env.example .env
# Edit .env and set your remote provider + key:
#   REMOTE_PROVIDER=fireworks   ->  set FIREWORKS_API_KEY
#   REMOTE_PROVIDER=gemini      ->  set GEMINI_API_KEY (from aistudio.google.com/apikey)
# Set the key to "demo" to run without a real key.
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

## Troubleshooting

**Submitting a task returns "Internal Server Error" (HTTP 500)**

This almost always means the *remote* model call failed and the error wasn't handled.
Local (trivial/simple) tasks keep working; only tasks that route remote fail. Most common cause:

- **Gemini quota exceeded (HTTP 429).** The free tier allows only ~20 requests/day for
  `gemini-2.5-flash`. Confirm by calling the API directly:

  ```bash
  curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$GEMINI_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"contents":[{"parts":[{"text":"hello"}]}]}'
  ```

  - `RESOURCE_EXHAUSTED` / `429` → out of quota. Switch to `gemini-2.5-flash-lite`,
    enable billing, or wait for the daily reset (midnight Pacific).
  - `API key not valid` → use a real `AIza...` key from https://aistudio.google.com/apikey.
  - Returns `candidates` → the key is fine.

With the hardened `backend/models/gemini.py`, these now return a `[REMOTE ERROR] ...`
message in the answer field instead of a 500, so the dashboard stays usable.

**Remote answers come back empty / truncated**

`gemini-2.5-flash` has thinking on by default, and thinking tokens share the
`maxOutputTokens` budget. The client disables thinking (`thinkingBudget = 0`) so the
full budget goes to the answer. Raise `maxOutputTokens` if you need longer outputs.

---

## Built With

- [FastAPI](https://fastapi.tiangolo.com) — async Python backend
- [Ollama](https://ollama.ai) — local model runtime with AMD ROCm support
- [Fireworks AI](https://fireworks.ai) / [Google Gemini](https://ai.google.dev) — remote model APIs
- [React](https://react.dev) + [Recharts](https://recharts.org) — live dashboard
- [Docker Compose](https://docs.docker.com/compose) — single-command deployment
