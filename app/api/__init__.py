from .router import (
    agent_router,
    business_metrics_router,
    conversations_router,
    draft_reviews_router,
    experiments_router,
)
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(agent_router)
api_router.include_router(business_metrics_router)
api_router.include_router(conversations_router)
api_router.include_router(draft_reviews_router)
api_router.include_router(experiments_router)
