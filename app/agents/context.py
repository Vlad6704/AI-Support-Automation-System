from dataclasses import dataclass

from app.repositories import (
    AgentRepository,
    DatabaseAgentRepository,
    StubAgentRepository,
)


@dataclass(frozen=True)
class AgentContext:
    repository: AgentRepository


def create_stub_agent_context(world: str = "world_1") -> AgentContext:
    return AgentContext(
        repository=StubAgentRepository(world),
    )


def create_database_agent_context() -> AgentContext:
    return AgentContext(
        repository=DatabaseAgentRepository(),
    )
