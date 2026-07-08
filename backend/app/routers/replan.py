"""Live mid-flight replan endpoint.

Accepts an NL instruction + current mission state and returns:
- parsed action list
- route diff (added stops, removed stops, modified legs)
- updated trajectory GPS points for map overlay
"""
from __future__ import annotations

from fastapi import APIRouter

from app.geo.locations import load_locations
from app.llm.nl_mission_parser import parse as nl_parse

router = APIRouter(prefix="/api", tags=["replan"])

_CATALOG = {r[0]: (r[1], r[2]) for r in load_locations()}


@router.post("/replan")
async def replan(req: dict) -> dict:
    """
    Input:
      instruction: str  -- NL instruction
      current_route: list[str]  -- current ordered list of location names
      session_id: str  -- optional
    Output:
      actions: parsed action list
      route_diff: {added: [], removed: [], rerouted: bool}
      new_route: list[str]
      new_trajectory_gps: list[[lat, lon]]
    """
    instruction = req.get("instruction", "")
    current_route: list[str] = req.get("current_route", [])
    all_labels = list(_CATALOG.keys())

    parse_result = await nl_parse(instruction, all_labels, phase="midflight")
    actions = parse_result.get("actions", [])

    added: list[str] = []
    removed: list[str] = []
    rerouted = False
    new_route = list(current_route)

    for act in actions:
        atype = act.get("type")
        loc = act.get("location")
        if atype == "ADD_STOP" and loc and loc not in new_route:
            # Insert waypoint before the last delivery
            insert_at = max(1, len(new_route) - 1)
            new_route.insert(insert_at, loc)
            added.append(loc)
        elif atype == "REMOVE_STOP" and loc and loc in new_route:
            new_route.remove(loc)
            removed.append(loc)
        elif atype == "REROUTE":
            rerouted = True
            if loc and loc not in new_route:
                new_route.insert(1, loc)
                added.append(loc)
        elif atype == "DELIVER" and loc and loc not in new_route:
            new_route.append(loc)
            added.append(loc)
        elif atype == "PICKUP" and loc and loc not in new_route:
            insert_at = max(1, len(new_route) - 1)
            new_route.insert(insert_at, loc)
            added.append(loc)
        elif atype == "EMERGENCY_RETURN":
            # Return to depot immediately
            depot = new_route[0] if new_route else None
            new_route = [depot] if depot else []
            rerouted = True

    new_traj_gps = [
        list(_CATALOG[loc]) for loc in new_route if loc in _CATALOG
    ]

    return {
        "instruction": instruction,
        "parse_result": parse_result,
        "route_diff": {"added": added, "removed": removed, "rerouted": rerouted},
        "new_route": new_route,
        "new_trajectory_gps": new_traj_gps,
    }
