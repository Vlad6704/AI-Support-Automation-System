import asyncio
from uuid import uuid4

from langsmith import aevaluate
from langchain_core.runnables import RunnableConfig

from app.agents.context import create_database_agent_context
from app.agents.billing_agent.main import graph
from app.scenario_database import scenario_session_factory
from app.scenarios import world_path


async def target(inputs: dict) -> dict:
    config: RunnableConfig = {
        "configurable": {"thread_id": f"billing_eval_id__{uuid4()}"}
    }
    with scenario_session_factory(world_path("world_1")) as sessions:
        return await graph.ainvoke(
            {"ticket": inputs["input"]},
            config=config,
            context=create_database_agent_context(sessions),
        )


async def main():
    experiment_results = await aevaluate(
        target,
        data="end-to-end-billing-1",
    )
    print(experiment_results)


if __name__ == "__main__":
    asyncio.run(main())
