from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from app.api import api_router
from app.db import Base, engine
from app import models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
