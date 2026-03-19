"""FastAPI application factory for the Soother web UI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .devices import DeviceManager
from .routes import actions, pages, ws

BASE_DIR = Path(__file__).parent


def create_app() -> FastAPI:
    device_manager = DeviceManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        device_manager.connect_known_devices()
        try:
            yield
        finally:
            await device_manager.disconnect_all()

    app = FastAPI(title="Soother", lifespan=lifespan)
    app.state.device_manager = device_manager

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    app.include_router(pages.router)
    app.include_router(actions.router)
    app.include_router(ws.router)

    return app
