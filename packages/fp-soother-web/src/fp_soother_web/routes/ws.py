"""WebSocket route pushing live device state updates to the browser."""

from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..deps import get_device_manager_ws
from ..devices import DeviceManager

router = APIRouter()


@router.websocket("/ws/devices/{address}")
async def device_state_ws(
    websocket: WebSocket,
    address: str,
    device_manager: DeviceManager = Depends(get_device_manager_ws),
) -> None:
    await websocket.accept()
    managed = device_manager.get(address)
    if managed is None:
        await websocket.close(code=4404, reason="Unknown device")
        return

    device_manager.register_websocket(address, websocket)
    await websocket.send_json(managed.status())
    try:
        while True:
            # No client -> server messages are expected; just keep the
            # connection open until the browser disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        device_manager.unregister_websocket(address, websocket)
