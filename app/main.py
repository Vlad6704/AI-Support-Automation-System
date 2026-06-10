import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api import api_router
from app.db import Base, engine
from app.logging_config import configure_logging
from app.observability import shutdown_langfuse

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Application starting")
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        logger.info("Application shutting down")
        shutdown_langfuse()


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)


@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Request failed method=%s path=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            (perf_counter() - started_at) * 1000,
        )
        raise

    logger.info(
        "Request completed method=%s path=%s status_code=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        (perf_counter() - started_at) * 1000,
    )
    return response


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
