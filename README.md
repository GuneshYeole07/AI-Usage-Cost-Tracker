# ⚡ AI Usage & Cost Tracker

[![CI Pipeline](https://github.com/your-username/ai-usage-cost-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/ai-usage-cost-tracker/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A full-stack, production-grade LLM governance and cost management system built with **FastAPI**, **SQLAlchemy**, **Streamlit**, and **Docker**.

---

## 🎯 Problem Statement: Why This Project?

Provider-native dashboards (OpenAI, Anthropic, Google Cloud Vertex AI) suffer from major governance limitations when operating in real-world production environments:

| Limitation in Provider Dashboards | Solution in AI Usage & Cost Tracker |
| :--- | :--- |
| **No Feature Attribution**: Bills are grouped by API key or organization, leaving teams blind to which product feature (`chatbot`, `summarizer`, `rag-search`, `evals`) incurred the cost. | **Tag-Based Cost Attribution**: Every request is tagged by product feature/use-case, providing fine-grained ROI and unit economics. |
| **No Proactive Budget Enforcement**: Alerts are typically delayed and organization-wide, offering no per-feature limits. | **Multi-Tier Budget Governance**: Enforces monthly spending limits per tag with automated status evaluation: `OK` (<80%), `WARNING` (80–100%), and `EXCEEDED` (>100%). |
| **No Anomaly Spike Detection**: Runaway loops or prompt injection exploits go unnoticed until the end-of-month bill arrives. | **Rule-Based Statistical Anomaly Detection**: Compares current daily spend against a trailing 7-day baseline to instantly detect and flag >2.5x surges without black-box ML. |
| **Multi-Provider Silos**: Fragmented dashboards across disparate vendors without unified unit economics. | **Unified Multi-Provider Ingestion**: Aggregates token consumption, pricing, and latency across **8 major AI providers** (OpenAI, Anthropic, Google Gemini, DeepSeek, Mistral AI, Groq, Cohere, and Together AI). |

---

## 🏗️ Architecture & System Design

```
                     +-----------------------------------+
                     |        Streamlit Dashboard        |
                     |  - Spend Overview & Charts        |
                     |  - Feature Tag Attribution        |
                     |  - Monthly Budget Health Gauges   |
                     |  - Anomaly Alert Feed             |
                     +-----------------+-----------------+
                                       |
                                HTTP REST / JSON
                                       |
                     +-----------------v-----------------+
                     |         FastAPI Backend           |
                     |  - Request Validation (Pydantic)  |
                     |  - Structured Python Logging      |
                     |  - Statistical Anomaly Engine     |
                     |  - Database Migrations (Alembic)  |
                     +-----------------+-----------------+
                                       |
                              SQLAlchemy ORM
                                       |
                     +-----------------v-----------------+
                     |         SQLite Database           |
                     |   `usage_logs`  |   `budgets`     |
                     +-----------------------------------+
```

---

## 🚀 Key Features

### 1. API Usage Logging (`/log` & `/usage`)
- Records provider, model name, input/output tokens, cost in USD, and feature tag.
- Multidimensional querying with filtering by provider, tag, date range, and pagination.

### 2. Feature-Level Cost Attribution (`/costs/by-tag`)
- Computes aggregate spend, total request count, token breakdown, and average cost-per-request grouped by tag.

### 3. Monthly Budget Limits & Health Monitoring (`/budgets` & `/budgets/status`)
- Set and update monthly budgets per feature tag.
- Real-time spend tracking evaluated against calendar month bounds with automated health classification (`ok`, `warning`, `exceeded`).

### 4. Explainable Statistical Anomaly Detection (`/alerts`)
- Computes trailing 7-day daily average baseline:
  $$\text{Baseline} = \frac{\sum_{d=1}^{7} \text{Cost}_{d}}{7}$$
- Compares today's spend against the baseline. Flags an anomaly when:
  $$\text{Cost}_{\text{today}} > 2.5 \times \text{Baseline} \quad (\text{with } \text{Cost}_{\text{today}} \ge \$0.05)$$

### 5. Interactive Streamlit Dashboard
- **Executive Overview**: Total spend, token totals, request counts, provider share donut chart, daily spend stack chart.
- **Cost by Tag**: Comparative bar charts and token distribution visualizations.
- **Budgets & Governance**: Color-coded progress indicators and real-time budget creation form.
- **Anomaly Alerts**: Visual surge alert cards with root-cause metrics.
- **Live Simulator**: Test and record custom requests interactively.
- **Idempotent Data Seeder**: One-click demo data population that safely cleans and reseeds representative multi-day traffic.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, FastAPI, Pydantic v2, Pydantic-Settings, Uvicorn
- **Database & ORM**: SQLite (file-based), SQLAlchemy 2.0, Alembic
- **Frontend**: Streamlit, Plotly, Pandas
- **Testing & Quality**: Pytest, Pytest-Asyncio, HTTPX, Ruff
- **DevOps**: Docker, Docker Compose, GitHub Actions CI

---

## 📦 Quick Start (Local Installation)

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/your-username/ai-usage-cost-tracker.git
cd ai-usage-cost-tracker

python -m venv .venv
# On Linux/macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
# Copy example environment configuration
cp .env.example .env
```

### 4. Run Database Migrations & Seed Demo Data

```bash
# Run schema migrations via Alembic
alembic upgrade head

# Seed realistic 14-day sample traffic (idempotent)
python scripts/seed.py
```

### 5. Start Backend & Dashboard

In Terminal 1 (Backend):
```bash
uvicorn app.main:app --reload --port 8000
```
*API docs available at: `http://localhost:8000/docs`*

In Terminal 2 (Streamlit Dashboard):
```bash
streamlit run dashboard/app.py
```
*Dashboard available at: `http://localhost:8501`*

---

## 🐳 Running with Docker & Docker Compose

Run both services with health checks and persistent volume storage in a single command:

```bash
# Build and launch services
docker compose up --build

# In a separate terminal or once launched, seed demo data:
docker compose exec backend python -c "from scripts.seed import seed_demo_data; seed_demo_data()"
```

- **Dashboard UI**: [http://localhost:8501](http://localhost:8501)
- **FastAPI Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Backend Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

To stop the containers:
```bash
docker compose down
```

---

## 🧪 Testing & Linting

Run the test suite with Pytest:
```bash
pytest -v
```

Run code quality and style checks with Ruff:
```bash
ruff check .
```

---

## 📖 API Documentation & Reference

| Method | Endpoint | Description | Sample Query / Body |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service health & DB connectivity check | — |
| `POST` | `/log` | Log an individual LLM API call | `{"provider":"openai","model_name":"gpt-4o","tokens_in":1200,"tokens_out":350,"cost":0.00725,"tag":"chatbot"}` |
| `GET` | `/usage` | Query historical logs with filters | `?provider=openai&tag=chatbot&limit=50` |
| `GET` | `/costs/by-tag` | Aggregated cost and token breakdown by tag | `?start_date=2026-08-01T00:00:00Z` |
| `POST` | `/budgets` | Set or update monthly budget for a tag | `{"tag":"chatbot","monthly_limit":75.0}` |
| `GET` | `/budgets/status` | Current month spend vs budget limits | — |
| `GET` | `/alerts` | Active statistical cost anomalies (>2.5x) | — |

---

## 💡 Production-Readiness Highlights

- **Alembic Schema Migrations**: Schema evolution is strictly versioned in `alembic/versions/`.
- **Defensive Input Validation**: Pydantic models validate non-negative numbers, positive budget limits, normalized strings, and valid date bounds.
- **Idempotent Data Seeding**: `scripts/seed.py` cleanly flushes and seeds multi-day traffic with pre-configured OK, Warning, Exceeded budgets, and an anomaly spike for live demoing.
- **Resilient Containerization**: Multi-stage Docker builds with automated healthchecks on both services.
- **Automated CI**: GitHub Actions workflow tests on Python 3.10, 3.11, and 3.12 with zero linting warnings.

---

## 🔮 Roadmap / Future Enhancements

- **PostgreSQL Adapter**: Connection pooling via asyncpg for high-throughput concurrency.
- **Python Middleware Wrapper SDK**: `@track_cost(tag="...")` decorator for automatic interception of OpenAI/Gemini/Anthropic client calls.
- **Webhook Integrations**: Automated Slack / PagerDuty / Email notifications when budgets reach warning or exceeded thresholds.
- **Token Streaming Interceptor**: Chunk-by-chunk token counter for server-sent event (SSE) streaming responses.
