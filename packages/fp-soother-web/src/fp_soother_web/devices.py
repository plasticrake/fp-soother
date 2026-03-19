"""In-memory registry of live BLE connections to paired soothers.

The web app keeps a persistent connection per paired device (rather than
connecting on-demand per request) so status updates can stream live and
controls feel responsive.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import TYPE_CHECKING, Any

from fp_soother_lib import SootherClient, SootherConnectionError
from fp_soother_util import list_paired_devices, load_paired_device

if TYPE_CHECKING:
    from fastapi import WebSocket

log = logging.getLogger(__name__)


def state_to_dict(state: Any) -> dict[str, Any]:
    """Serialize a SootherState to a JSON-friendly dict."""
    return {
        f.name: getattr(state, f.name)
        for f in dataclasses.fields(state)
        if f.name not in ("raw_state", "_ATTR_MAP")
    }


@dataclasses.dataclass
class ManagedDevice:
    address: str
    client: SootherClient
    connected: bool = False
    connecting: bool = False
    error: str | None = None
    expect_disconnect: bool = False
    websockets: set[WebSocket] = dataclasses.field(default_factory=set)

    def status(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "connected": self.connected,
            "connecting": self.connecting,
            "error": self.error,
            "state": state_to_dict(self.client.state) if self.connected else None,
        }


class DeviceManager:
    """Owns one SootherClient per paired device and broadcasts state changes
    to any subscribed websockets."""

    def __init__(self) -> None:
        self._devices: dict[str, ManagedDevice] = {}

    def get(self, address: str) -> ManagedDevice | None:
        return self._devices.get(address)

    def all(self) -> list[ManagedDevice]:
        return list(self._devices.values())

    def connect_known_devices(self) -> None:
        """Kick off a best-effort connection attempt for every device saved
        in the paired-device store, without blocking app startup. Failures
        are recorded per-device, not raised."""
        for address, (peripheral_type, session_key) in list_paired_devices().items():
            client = SootherClient(
                address, session_key=session_key, peripheral_type=peripheral_type
            )
            self._devices[address] = ManagedDevice(
                address=address, client=client, connecting=True
            )
            asyncio.create_task(self._connect(address, peripheral_type, session_key))

    async def _connect(
        self, address: str, peripheral_type: int, session_key: bytes | None
    ) -> ManagedDevice:
        client = SootherClient(
            address, session_key=session_key, peripheral_type=peripheral_type
        )
        managed = self._devices.get(address)
        if managed is None:
            managed = ManagedDevice(address=address, client=client)
            self._devices[address] = managed
        else:
            managed.client = client
        managed.connecting = True
        try:
            await client.open()
            await client.refresh_state()
            client.on_state_change(
                lambda state, a=address: self._on_state_change(a, state)
            )
            client.on_disconnect(lambda a=address: self._on_disconnect(a))
            managed.connected = True
            managed.error = None
        except SootherConnectionError as exc:
            managed.connected = False
            managed.error = str(exc)
            log.warning("Could not connect to %s: %s", address, exc)
        finally:
            managed.connecting = False
        return managed

    def reconnect(self, address: str) -> ManagedDevice:
        """Kick off a reconnect to an already-paired device using its saved
        session key, without blocking the caller."""
        saved = load_paired_device(address)
        if saved is None:
            raise ValueError(f"{address} is not a paired device.")
        peripheral_type, session_key = saved
        managed = self._devices.get(address)
        if managed is None:
            client = SootherClient(
                address, session_key=session_key, peripheral_type=peripheral_type
            )
            managed = ManagedDevice(address=address, client=client)
            self._devices[address] = managed
        managed.connecting = True
        asyncio.create_task(self._connect(address, peripheral_type, session_key))
        return managed

    def register_paired(self, client: SootherClient) -> ManagedDevice:
        """Register an already-connected, freshly-paired client."""
        managed = ManagedDevice(address=client.address, client=client, connected=True)
        client.on_state_change(
            lambda state, a=client.address: self._on_state_change(a, state)
        )
        client.on_disconnect(lambda a=client.address: self._on_disconnect(a))
        self._devices[client.address] = managed
        return managed

    async def forget(self, address: str) -> None:
        managed = self._devices.pop(address, None)
        if managed is not None and managed.connected:
            managed.expect_disconnect = True
            await managed.client.close()

    async def disconnect_all(self) -> None:
        for managed in self._devices.values():
            if managed.connected:
                managed.expect_disconnect = True
                try:
                    await managed.client.close()
                except SootherConnectionError:
                    pass

    def _on_state_change(self, address: str, state: Any) -> None:
        self._broadcast(address)

    def _on_disconnect(self, address: str) -> None:
        managed = self._devices.get(address)
        if managed is None:
            return
        if managed.expect_disconnect:
            managed.expect_disconnect = False
            return
        self.mark_failed(address, "Device disconnected unexpectedly.")

    def mark_failed(self, address: str, error: str) -> None:
        """Mark a device offline and schedule a reconnect attempt, e.g. after
        an unexpected disconnect or a command/write failure (which doesn't
        always trigger the BLE disconnected callback promptly)."""
        managed = self._devices.get(address)
        if managed is None or managed.connecting:
            return
        managed.connected = False
        managed.error = error
        self._broadcast(address)
        old_client = managed.client
        peripheral_type = old_client.peripheral_type
        session_key = old_client.session_key
        managed.connecting = True
        asyncio.create_task(
            self._reconnect_after_failure(
                address, old_client, peripheral_type, session_key
            )
        )

    async def _reconnect_after_failure(
        self,
        address: str,
        old_client: SootherClient,
        peripheral_type: int,
        session_key: bytes | None,
    ) -> None:
        try:
            await old_client.close()
        except SootherConnectionError:
            pass
        await self._connect(address, peripheral_type, session_key)

    def _broadcast(self, address: str) -> None:
        managed = self._devices.get(address)
        if managed is None or not managed.websockets:
            return
        payload = managed.status()
        for ws in set(managed.websockets):
            asyncio.create_task(_safe_send_json(ws, payload))

    def register_websocket(self, address: str, ws: WebSocket) -> None:
        managed = self._devices.get(address)
        if managed is not None:
            managed.websockets.add(ws)

    def unregister_websocket(self, address: str, ws: WebSocket) -> None:
        managed = self._devices.get(address)
        if managed is not None:
            managed.websockets.discard(ws)


async def _safe_send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    try:
        await ws.send_json(payload)
    except Exception:
        log.debug("Failed to send websocket update", exc_info=True)
