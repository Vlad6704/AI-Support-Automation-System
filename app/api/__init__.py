from .router import agent_router, conversations_router, experiments_router
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(agent_router)
api_router.include_router(conversations_router)
api_router.include_router(experiments_router)
