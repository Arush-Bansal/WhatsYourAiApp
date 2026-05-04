import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.routes.root import router as root_router
from app.routes.webhook import router as webhook_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=30.0) as client:
        app.state.http = client
        yield


app = FastAPI(lifespan=lifespan, title="WhatsApp webhook")
app.include_router(root_router)
app.include_router(webhook_router)

__all__ = ["app"]
