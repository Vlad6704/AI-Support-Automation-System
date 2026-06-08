# AI Support Automation System

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
