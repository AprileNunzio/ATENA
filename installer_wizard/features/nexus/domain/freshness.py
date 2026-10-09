from dataclasses import dataclass

FRESH_SECONDS = 7 * 86400


@dataclass(frozen=True)
class Record:
    fingerprint: str
    first_seen: float = 0.0
    changed_at: float = 0.0

    def as_dict(self) -> dict:
        return {"fingerprint": self.fingerprint, "first_seen": self.first_seen, "changed_at": self.changed_at}


def restore(raw) -> dict[str, Record]:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for fid, rec in raw.items():
        if isinstance(fid, str) and isinstance(rec, dict) and isinstance(rec.get("fingerprint"), str):
            out[fid] = Record(rec["fingerprint"], float(rec.get("first_seen") or 0), float(rec.get("changed_at") or 0))
    return out


def reconcile(previous: dict[str, Record], current: dict[str, str], now: float) -> dict[str, Record]:
    baseline = not previous
    result = {}
    for fid, fingerprint in current.items():
        known = previous.get(fid)
        if known is None:
            result[fid] = Record(fingerprint, 0.0 if baseline else now, 0.0)
        elif known.fingerprint != fingerprint:
            result[fid] = Record(fingerprint, known.first_seen, now)
        else:
            result[fid] = known
    return result


def badge(record: Record | None, now: float) -> dict:
    if record is None:
        return {"badge": "", "since": 0}
    if record.first_seen and now - record.first_seen < FRESH_SECONDS:
        return {"badge": "new", "since": record.first_seen}
    if record.changed_at and now - record.changed_at < FRESH_SECONDS:
        return {"badge": "updated", "since": record.changed_at}
    return {"badge": "", "since": 0}
