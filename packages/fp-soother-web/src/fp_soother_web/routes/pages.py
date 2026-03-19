"""HTML page routes: dashboard, device detail, scan."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fp_soother_lib import scan as ble_scan
from fp_soother_util import list_presets

from ..controls import (
    COLOR_OPTIONS,
    CONTROLS,
    PRESET_SLOTS,
    SECTIONS,
    STAR_SEQUENCE_CUSTOM,
    TABS,
    TOGGLES,
)
from ..deps import get_device_manager
from ..devices import DeviceManager
from . import templates

router = APIRouter()

DeviceManagerDep = Annotated[DeviceManager, Depends(get_device_manager)]


@router.get("/")
async def index(request: Request, device_manager: DeviceManagerDep) -> object:
    devices = [managed.status() for managed in device_manager.all()]
    return templates.TemplateResponse(request, "index.html", {"devices": devices})


@router.get("/devices/{address}")
async def device_detail(
    request: Request,
    address: str,
    device_manager: DeviceManagerDep,
) -> object:
    managed = device_manager.get(address)
    return templates.TemplateResponse(
        request,
        "device.html",
        {
            "device": managed.status() if managed else None,
            "controls": CONTROLS,
            "toggles": TOGGLES,
            "sections": SECTIONS,
            "tabs": TABS,
            "color_options": COLOR_OPTIONS,
            "star_sequence_custom": STAR_SEQUENCE_CUSTOM,
            "preset_slots": PRESET_SLOTS,
            "presets": list_presets(address) if managed else {},
        },
    )


@router.get("/devices/{address}/card")
async def device_card(
    request: Request,
    address: str,
    device_manager: DeviceManagerDep,
) -> object:
    managed = device_manager.get(address)
    return templates.TemplateResponse(
        request,
        "_device_card.html",
        {
            "device": managed.status()
            if managed
            else {
                "address": address,
                "connected": False,
                "connecting": False,
                "error": "Unknown device",
            }
        },
    )


@router.get("/scan")
async def scan_page(request: Request) -> object:
    return templates.TemplateResponse(request, "scan.html", {"results": None})


@router.post("/scan")
async def scan_action(request: Request) -> object:
    found = await ble_scan(timeout=10.0)
    results = [
        {"address": device.address, "name": device.name, "rssi": adv.rssi}
        for device, adv in found
    ]
    return templates.TemplateResponse(request, "scan.html", {"results": results})
