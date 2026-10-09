import asyncio
import logging

log = logging.getLogger("atena.redalert")

PERIOD = 1.0
RED = [255, 0, 0]
KEEP = ("brightness", "rgb_color", "color_temp_kelvin", "hs_color", "xy_color", "effect")
UNUSABLE = ("unavailable", "unknown")


async def _call(service: str, entities: list[str], data: dict | None = None) -> None:
    from features.home_assistant.home import brain
    if entities:
        await brain._call({"type": "call_service", "domain": "light", "service": service, "service_data": data or {},
                           "target": {"entity_id": entities}}, 10)


def snapshot() -> dict[str, dict]:
    from features.home_assistant.home import brain
    if brain.status != "online":
        return {}
    return {eid: {"on": st.get("state") == "on", **{k: v for k, v in (st.get("attrs") or {}).items() if k in KEEP}}
            for eid, st in brain.states.items() if eid.startswith("light.") and st.get("state") not in UNUSABLE}


async def flash(entities: list[str], stop: asyncio.Event, seconds: float) -> int:
    cycles, deadline = 0, asyncio.get_running_loop().time() + seconds
    while not stop.is_set() and asyncio.get_running_loop().time() < deadline:
        await _call("turn_on", entities, {"rgb_color": RED, "brightness": 255})
        await _wait(stop, PERIOD)
        if stop.is_set():
            break
        await _call("turn_off", entities)
        await _wait(stop, PERIOD)
        cycles += 1
    return cycles


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), seconds)
    except asyncio.TimeoutError:
        return


def _restore_data(state: dict) -> dict:
    data = {k: state[k] for k in ("brightness",) if state.get(k) is not None}
    for key in ("rgb_color", "color_temp_kelvin", "hs_color", "xy_color"):
        if state.get(key) is not None:
            data[key] = state[key]
            break
    return data


async def restore(saved: dict[str, dict]) -> None:
    off = [eid for eid, st in saved.items() if not st["on"]]
    await _call("turn_off", off)
    for eid, st in saved.items():
        if st["on"]:
            await _call("turn_on", [eid], _restore_data(st))
