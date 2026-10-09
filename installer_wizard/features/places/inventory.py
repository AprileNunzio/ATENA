from features.places.store import store

FIXED = (("server", "Server di Atena", ["shows"]), ("display:kiosk", "Display di Atena", ["shows", "speaks"]),
         ("mic:local", "Microfono di Atena", ["hears"]), ("camera:main", "Webcam di Atena", ["sees"]))
NODE_SENSES = {"phone": ["hears", "speaks", "shows"], "pc": ["hears", "speaks", "shows"], "display": ["shows", "speaks"],
               "satellite": ["hears", "speaks"], "camera": ["sees"]}


def _nodes() -> list[dict]:
    from features.nodes.registry import registry
    rows = []
    for node in registry.data.get("nodes", {}).values():
        rows.append({"key": f"node:{node['id']}", "name": node.get("name") or node["id"], "kind": node.get("type", "other"),
                     "hint": node.get("room", ""), "senses": NODE_SENSES.get(node.get("type", ""), ["hears", "speaks"])})
    return rows


def _cameras() -> list[dict]:
    from features.cameras.cameras import cameras
    return [{"key": f"camera:{c['id']}", "name": c.get("name") or c["id"], "kind": "camera", "hint": c.get("room", ""),
             "senses": ["sees"]} for c in cameras.listing()["cameras"]]


def devices() -> list[dict]:
    rows = [{"key": k, "name": n, "kind": "atena", "hint": "", "senses": s} for k, n, s in FIXED]
    rows += _nodes() + _cameras()
    with store.lock:
        for row in rows:
            placed = store.placements.get(row["key"])
            row["room_id"] = placed.room_id if placed else ""
            if placed and placed.senses:
                row["senses"] = placed.senses
    return rows
