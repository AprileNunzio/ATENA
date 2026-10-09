from config import env_get
from state import store

from features.authz.heard import heard
from features.authz.principal import ANONYMOUS, Principal, Strength

SESSION_DEVICES = ("admin", "remote")
FACE_MIN_DEFAULT = 0.6


def face_min() -> float:
    try:
        return min(max(float(env_get("ATENA_AUTHZ_FACE_MIN", str(FACE_MIN_DEFAULT))), 0.3), 0.99)
    except ValueError:
        return FACE_MIN_DEFAULT


def voice_strong() -> float:
    from features.ear.voiceprint import margin, match_base
    return match_base() + margin()


def _profile(slug: str) -> dict | None:
    from features.people import people
    return people.load(slug) if slug else None


def _owner() -> dict | None:
    from features.people import people
    return next((p for p in people.all_profiles(light=True) if p.get("role") == "owner"), None)


def faces() -> list[dict]:
    people = store.presence.get("people", []) if isinstance(store.presence, dict) else []
    live = []
    for p in people:
        state = ((p.get("liveness") or {}).get("state") or "") if isinstance(p.get("liveness"), dict) else ""
        if p.get("known") and p.get("slug") and float(p.get("confidence") or 0.0) >= face_min() and state != "spoof":
            live.append({"slug": p["slug"], "live": state == "live"})
    return live


def strangers() -> int:
    people = store.presence.get("people", []) if isinstance(store.presence, dict) else []
    return sum(1 for p in people if not p.get("known"))


def _principal(profile: dict, strength: Strength, factors: tuple[str, ...]) -> Principal:
    return Principal(slug=profile["slug"], role=str(profile.get("role") or "guest"), strength=strength,
                     factors=factors, override=str(profile.get("authorization") or ""))


def for_session() -> Principal:
    owner = _owner()
    if not owner:
        return Principal(slug="", role="owner", strength=Strength.STRONG, factors=("session",))
    return _principal(owner, Strength.STRONG, ("session",))


def for_request(device: str, speaker: str, text: str) -> Principal:
    if device in SESSION_DEVICES:
        return for_session()
    seen = faces()
    proof = heard.verify(speaker, text)
    if proof:
        profile = _profile(proof.slug)
        if not profile:
            return ANONYMOUS
        face = next((f for f in seen if f["slug"] == proof.slug), None)
        if face and face["live"]:
            return _principal(profile, Strength.STRONG, ("voice", "face"))
        if face or proof.score >= voice_strong():
            return _principal(profile, Strength.SINGLE, ("voice", "face") if face else ("voice",))
        return _principal(profile, Strength.WEAK, ("voice",))
    if len(seen) == 1 and strangers() == 0:
        profile = _profile(seen[0]["slug"])
        if profile:
            return _principal(profile, Strength.SINGLE if seen[0]["live"] else Strength.WEAK, ("face",))
    return ANONYMOUS
