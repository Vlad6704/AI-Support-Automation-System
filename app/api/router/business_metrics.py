from typing import Annotated

from fastapi import APIRouter, Query

from app.api.providers import AgentBusinessMetricsServiceProvider
from app.schemas import AgentBusinessMetrics

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/agent-business", response_model=AgentBusinessMetrics)
def get_agent_business_metrics(
    service: AgentBusinessMetricsServiceProvider,
    manual_handling_baseline_minutes: Annotated[float, Query(ge=0)] = 15,
) -> AgentBusinessMetrics:
    return service.get_metrics(
        manual_handling_baseline_minutes=manual_handling_baseline_minutes,
    )
