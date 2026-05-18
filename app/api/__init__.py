from .router import agent_router
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(agent_router)
