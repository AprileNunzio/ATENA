def thin(path: list, limit: int = 400) -> list:
    if len(path) <= limit:
        return [[round(a, 5), round(b, 5)] for a, b in path]
    step = len(path) / limit
    out = [path[int(i * step)] for i in range(limit)] + [path[-1]]
    return [[round(a, 5), round(b, 5)] for a, b in out]


def decode(encoded: str) -> list:
    points, index, lat, lon = [], 0, 0, 0
    while index < len(encoded):
        values = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            values.append(~(result >> 1) if result & 1 else result >> 1)
        lat += values[0]
        lon += values[1]
        points.append([lat / 1e5, lon / 1e5])
    return points


def osrm_text(st: dict) -> str:
    man = st.get("maneuver", {})
    kind, mod, name = man.get("type", ""), man.get("modifier", ""), st.get("name", "")
    side = {"left": "a sinistra", "right": "a destra", "slight left": "leggermente a sinistra",
            "slight right": "leggermente a destra", "sharp left": "tutto a sinistra", "sharp right": "tutto a destra",
            "straight": "dritto", "uturn": "con un'inversione"}.get(mod, "")
    on = f" su {name}" if name else ""
    if kind == "depart":
        return f"Parti{on}"
    if kind == "arrive":
        return "Sei arrivato a destinazione"
    if kind in ("roundabout", "rotary"):
        return f"Alla rotonda prendi la {man.get('exit', 1)}ª uscita{on}"
    if kind in ("turn", "end of road", "fork", "on ramp", "off ramp") and side:
        return f"Svolta {side}{on}" if kind != "on ramp" else f"Entra {side}{on}"
    if kind == "merge":
        return f"Immettiti{on}"
    if kind in ("continue", "new name") and name:
        return f"Continua{on}"
    return ""
