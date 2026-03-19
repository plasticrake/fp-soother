"""FastAPI dependency helpers shared across routers."""

from __future__ import annotations

from fastapi import Request, WebSocket

from .devices import DeviceManager


def get_device_manager(request: Request) -> DeviceManager:
    return request.app.state.device_manager


def get_device_manager_ws(websocket: WebSocket) -> DeviceManager:
    return websocket.app.state.device_manager
