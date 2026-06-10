from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from app.api import api_router
from app.db import Base, engine
from app import models  # noqa: F401
from app.observability import shutdown_langfuse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        shutdown_langfuse()


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)

INBOX_PATH = Path(__file__).resolve().parent / "static" / "inbox.html"
NEW_TICKET_PATH = Path(__file__).resolve().parent / "static" / "new_ticket.html"
TICKET_PATH = Path(__file__).resolve().parent / "static" / "ticket.html"


@app.get("/", include_in_schema=False)
def inbox() -> FileResponse:
    return FileResponse(INBOX_PATH)


@app.get("/tickets/new", include_in_schema=False)
def new_ticket() -> FileResponse:
    return FileResponse(NEW_TICKET_PATH)


@app.get("/tickets/{ticket_id}", include_in_schema=False)
def ticket(ticket_id: int) -> FileResponse:
    return FileResponse(TICKET_PATH)
