import asyncio
from uuid import uuid4

from langsmith import aevaluate
from langchain_core.runnables import RunnableConfig

from app.agents.context import create_stub_agent_context
from app.agents.billing_agent.main import graph


async def target(inputs: dict) -> dict:
    config: RunnableConfig = {
        "configurable": {"thread_id": f"billing_eval_id__{uuid4()}"}
    }
    return await graph.ainvoke(
        {"ticket": inputs["input"]},
        config=config,
        context=create_stub_agent_context(),
    )


async def main():
    experiment_results = await aevaluate(
        target,
        data="end-to-end-billing-1",
    )
    print(experiment_results)


if __name__ == "__main__":
    asyncio.run(main())
