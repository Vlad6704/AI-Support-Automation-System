# AI Support Automation System

## Project Description

AI Support Automation System is a FastAPI-based support automation platform that uses
LangGraph and LangChain agents to triage customer tickets, gather account and
delivery context, and draft support responses. The current automation focuses on
webhook-related support requests, with guardrails, risk-based human review, and
Langfuse observability for tracing and evaluating agent behavior.

The project includes a small static inbox/review interface, SQLAlchemy models and
repositories for support data, reproducible scenario databases for local testing,
and evaluation scripts that exercise agent workflows against seeded support
worlds.

## How to Run

Create a local environment file from the example and set your OpenAI API key:

```powershell
Copy-Item .env.example .env
```

Install dependencies with `uv`:

```powershell
uv sync
```

Run database migrations and start the FastAPI server:

```powershell
just server
```

The application starts at:

```text
http://127.0.0.1:8000
```

For a reproducible seeded scenario, run:

```powershell
just scenario-seed-and-run world_1
```

## Project Structure

- `app/main.py` - FastAPI application entrypoint.
- `app/db.py` - Database configuration and session setup.
- `app/api/router/` - API route handlers.
- `app/agents/` - Agent orchestration and domain-specific agent workflows.
- `app/agents/billing_agent/` - Billing agent graph, state, nodes, and routing conditions.
- `app/agents/tools/` - Tools used by agents, including database access helpers.
- `app/enums/` - Shared enum definitions.
- `app/models/` - Database/domain models.
- `app/repositories/` - Data access and serialization logic.
- `app/observability/` - Observability integrations, including Langfuse.
- `eval/` - Evaluation scripts and test scenarios for agent behavior.
- `support.db` - Local SQLite database used by the app.
- `main.py` - Root-level script entrypoint.
- `pyproject.toml` - Python project metadata and dependencies.
- `uv.lock` - Locked dependency versions managed by `uv`.

## Scenario Databases

JSON files in `scenarios/` are reproducible scenario seeds. Each scenario uses a
dedicated database and checkpoint database under `.scenarios/`.

To reset both databases, seed the scenario, and start the application:

```powershell
just scenario-seed-and-run world_1
```

To reset both databases and only seed the scenario:

```powershell
just scenario-seed world_1
```

To start the server while preserving the existing scenario data and checkpoints:

```powershell
just scenario world_1
```

The seed command prints the generated `DATABASE_URL`, which can be used to run
other commands against the selected scenario database.

You can also provide a JSON path:

```powershell
uv run -m app.scenarios run scenarios/world_1.json
```

Normal development continues to use `support.db` and `checkpoints.db`. Scenario
databases are disposable and are rebuilt only by the scenario seed commands.
