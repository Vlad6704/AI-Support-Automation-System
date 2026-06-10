from fastapi import APIRouter

from app.agents.billing_agent.main import run_billing_agent
from app.schemas import ExecuteAgentRequest

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/execute")
async def execute_agent(request: ExecuteAgentRequest):
    result = run_billing_agent(
        request.ticket,
        thread_id=request.thread_id,
        user_id=request.user_id,
    )

    if result.get("__interrupt__") is not None:
        return {
            "thread_id": request.thread_id,
            "interrupt": result.get("__interrupt__")[0].value,
        }

    return {
        "thread_id": request.thread_id,
        "category": result.get("category"),
        "billing_subcategory": result.get("billing_subcategory"),
        "billing_data": result.get("billing_data"),
        "billing_context": result.get("billing_context"),
        "draft_response": result.get("draft_response"),
    }
