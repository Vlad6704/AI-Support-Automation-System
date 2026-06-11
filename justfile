set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

server:
    uv run alembic upgrade head
    uv run -m main

# Start the existing scenario database and preserve its checkpoints.
scenario world="world_1":
    uv run -m app.scenarios start {{world}}

# Reset the scenario database and checkpoints, seed it, then start the server.
scenario-seed-and-run world="world_1":
    uv run -m app.scenarios run {{world}}

# Reset the scenario database and checkpoints, then seed it.
scenario-seed world="world_1":
    uv run -m app.scenarios seed {{world}}

agent ticket="":
    uv run -m app.agents.main_agent_invocation {{ticket}}

eval:
    uv run -m eval.langfuse.webhook.main_agent_experiment

eval-webhook-delivery-logs:
    uv run -m eval.langfuse.webhook.webhook_delivery_logs_agent_experiment

tests:
    uv run -m unittest discover -s tests

type-check:
    uv run --with basedpyright basedpyright

test-worlds:
    uv run -m unittest tests.test_world_schema tests.test_scenario_database

migrate:
    uv run alembic upgrade head

migration message:
    uv run alembic revision --autogenerate -m "{{message}}"

migration-current:
    uv run alembic current
