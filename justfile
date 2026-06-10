set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

server:
    uv run alembic upgrade head
    uv run -m main

agent ticket="":
    uv run -m app.agents.main_agent_invocation {{ticket}}

eval:
    uv run -m eval.langfuse.webhook.main_agent_experiment

tests:
    uv run -m unittest discover -s tests

migrate:
    uv run alembic upgrade head

migration message:
    uv run alembic revision --autogenerate -m "{{message}}"

migration-current:
    uv run alembic current
