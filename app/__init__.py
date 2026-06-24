import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.config import LOG_LEVEL
from app.request_logging import RequestLoggingMiddleware
from app.routes.gmail import router as gmail_router
from app.routes.root import router as root_router
from app.routes.slack import router as slack_router
from app.routes.webhook import router as webhook_router

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=30.0) as client:
        app.state.http = client
        yield


app = FastAPI(lifespan=lifespan, title="WhatsApp, Slack & Gmail webhook")
app.add_middleware(RequestLoggingMiddleware)
app.include_router(root_router)
app.include_router(webhook_router)
app.include_router(slack_router)
app.include_router(gmail_router)

__all__ = ["app"]
