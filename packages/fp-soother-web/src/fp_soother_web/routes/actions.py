"""HTMX action routes: pair, forget, and per-field device controls."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fp_soother_lib import SootherClient, SootherCommandError, SootherConnectionError
from fp_soother_util import (
    forget_paired_device,
    load_preset,
    save_paired_device,
    save_preset,
)

from ..controls import COLOR_OPTIONS, CONTROLS, PRESET_FIELDS, PRESET_SLOTS, TOGGLES
from ..deps import get_device_manager
from ..devices import DeviceManager
from . import templates

router = APIRouter()

DeviceManagerDep = Annotated[DeviceManager, Depends(get_device_manager)]


@router.post("/devices/pair")
async def pair_device(
    request: Request,
    address: Annotated[str, Form()],
    device_manager: DeviceManagerDep,
) -> object:
    client = SootherClient(address)
    try:
        await client.pair()
        await client.refresh_state()
    except (SootherConnectionError, SootherCommandError) as exc:
        return templates.TemplateResponse(
            request, "scan.html", {"results": None, "error": str(exc)}
        )
    if client.session_key is not None:
        save_paired_device(client.address, client.peripheral_type, client.session_key)
    device_manager.register_paired(client)
    return Response(status_code=204, headers={"HX-Redirect": f"/devices/{address}"})


@router.post("/devices/{address}/forget")
async def forget_device(
    address: str,
    device_manager: DeviceManagerDep,
) -> object:
    await device_manager.forget(address)
    forget_paired_device(address)
    return Response(status_code=204, headers={"HX-Redirect": "/"})


@router.post("/devices/{address}/reconnect")
async def reconnect_device(
    request: Request,
    address: str,
    device_manager: DeviceManagerDep,
) -> object:
    try:
        managed = device_manager.reconnect(address)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "_device_card.html",
        {"device": managed.status()},
    )


@router.post("/devices/{address}/toggle/music")
async def toggle_music(
    address: str,
    value: Annotated[str, Form()],
    device_manager: DeviceManagerDep,
) -> object:
    """Music & Sound's off/on affect different fields per App.md: off stops
    the sound (sound_mode=0), on resumes playback (play_mode=1) rather than
    picking a new sound."""
    managed = device_manager.get(address)
    if managed is None or not managed.connected:
        raise HTTPException(status_code=409, detail="Device is not connected.")

    turning_on = value in ("1", "true", "on", "True")
    try:
        if turning_on:
            await managed.client.set_play(True)
        else:
            await managed.client.set_sound_mode(0)
    except (SootherCommandError, SootherConnectionError) as exc:
        device_manager.mark_failed(address, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(status_code=204, headers={"HX-Redirect": f"/devices/{address}"})


@router.post("/devices/{address}/toggle/{field}")
async def toggle_control(
    address: str,
    field: str,
    value: Annotated[str, Form()],
    device_manager: DeviceManagerDep,
) -> object:
    toggle = TOGGLES.get(field)
    if toggle is None:
        raise HTTPException(status_code=404, detail=f"Unknown toggle: {field}")
    managed = device_manager.get(address)
    if managed is None or not managed.connected:
        raise HTTPException(status_code=409, detail="Device is not connected.")

    turning_on = value in ("1", "true", "on", "True")
    if not turning_on:
        target = toggle.off_value
    elif toggle.restore_field is not None:
        target = (
            getattr(managed.client.state, toggle.restore_field) or toggle.default_on
        )
    else:
        target = toggle.default_on

    setter = getattr(managed.client, CONTROLS[toggle.field].setter)
    try:
        await setter(target)
    except (SootherCommandError, SootherConnectionError) as exc:
        device_manager.mark_failed(address, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Sub-controls show/hide based on the new state, so refresh the whole page.
    return Response(status_code=204, headers={"HX-Redirect": f"/devices/{address}"})


@router.post("/devices/{address}/custom-colors")
async def set_custom_colors(
    request: Request,
    address: str,
    color0: Annotated[str, Form()],
    color1: Annotated[str, Form()],
    color2: Annotated[str, Form()],
    device_manager: DeviceManagerDep,
) -> object:
    managed = device_manager.get(address)
    if managed is None or not managed.connected:
        raise HTTPException(status_code=409, detail="Device is not connected.")

    allowed = {opt.value for opt in COLOR_OPTIONS}
    values = [int(color0), int(color1), int(color2)]
    if not all(v in allowed for v in values):
        raise HTTPException(
            status_code=422, detail=f"Custom colors must each be one of {allowed}."
        )
    try:
        await managed.client.set_star_projection_custom_colors(*values)
    except (SootherCommandError, SootherConnectionError) as exc:
        device_manager.mark_failed(address, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return templates.TemplateResponse(
        request,
        "_state_panel.html",
        {"device": managed.status(), "controls": CONTROLS},
    )


@router.post("/devices/{address}/presets/{slot}/save")
async def save_preset_route(
    address: str,
    slot: int,
    device_manager: DeviceManagerDep,
) -> object:
    if slot not in PRESET_SLOTS:
        raise HTTPException(status_code=404, detail=f"Unknown preset slot: {slot}")
    managed = device_manager.get(address)
    if managed is None or not managed.connected:
        raise HTTPException(status_code=409, detail="Device is not connected.")

    values = {field: getattr(managed.client.state, field) for field in PRESET_FIELDS}
    save_preset(address, slot, values)
    return Response(status_code=204, headers={"HX-Redirect": f"/devices/{address}"})


@router.post("/devices/{address}/presets/{slot}/send")
async def send_preset_route(
    address: str,
    slot: int,
    device_manager: DeviceManagerDep,
) -> object:
    if slot not in PRESET_SLOTS:
        raise HTTPException(status_code=404, detail=f"Unknown preset slot: {slot}")
    managed = device_manager.get(address)
    if managed is None or not managed.connected:
        raise HTTPException(status_code=409, detail="Device is not connected.")

    values = load_preset(address, slot)
    if values is None:
        raise HTTPException(status_code=404, detail=f"No preset saved in slot {slot}.")
    try:
        await managed.client.send_preset(**values)
    except (SootherCommandError, SootherConnectionError) as exc:
        device_manager.mark_failed(address, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(status_code=204, headers={"HX-Redirect": f"/devices/{address}"})


@router.post("/devices/{address}/control/{field}")
async def set_control(
    request: Request,
    address: str,
    field: str,
    value: Annotated[str, Form()],
    device_manager: DeviceManagerDep,
) -> object:
    control = CONTROLS.get(field)
    if control is None:
        raise HTTPException(status_code=404, detail=f"Unknown control: {field}")
    managed = device_manager.get(address)
    if managed is None or not managed.connected:
        raise HTTPException(status_code=409, detail="Device is not connected.")

    setter = getattr(managed.client, control.setter)
    try:
        if control.kind == "bool":
            await setter(value in ("1", "true", "on", "True"))
        else:
            level = int(value)
            if control.kind == "select":
                allowed = {opt.value for opt in control.options}
                if level not in allowed:
                    raise HTTPException(
                        status_code=422, detail=f"{field} must be one of {allowed}."
                    )
            elif not (control.minimum <= level <= control.maximum):
                raise HTTPException(
                    status_code=422,
                    detail=f"{field} must be between {control.minimum} and {control.maximum}.",
                )
            await setter(level)
    except (SootherCommandError, SootherConnectionError) as exc:
        device_manager.mark_failed(address, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if control.kind == "bool":
        # Bool controls (play/nightlight) show or hide other controls, so
        # refresh the whole page rather than just the status partial.
        return Response(status_code=204, headers={"HX-Redirect": f"/devices/{address}"})

    return templates.TemplateResponse(
        request,
        "_state_panel.html",
        {"device": managed.status(), "controls": CONTROLS},
    )
