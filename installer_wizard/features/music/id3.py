import os
import struct
import tempfile
from pathlib import Path

FRAMES = {"title": "TIT2", "artist": "TPE1", "album": "TALB", "album_artist": "TPE2", "genre": "TCON", "year": "TYER",
          "track_no": "TRCK", "disc_no": "TPOS"}
TAG_CHUNKS = (b"id3 ", b"ID3 ")
MAX_TEXT = 1024


def _syncsafe(size: int) -> bytes:
    return bytes(((size >> shift) & 0x7F) for shift in (21, 14, 7, 0))


def _frame(frame_id: str, text: str) -> bytes:
    body = b"\x01" + text[:MAX_TEXT].encode("utf-16")
    return frame_id.encode("ascii") + struct.pack(">I", len(body)) + b"\x00\x00" + body


def build(fields: dict) -> bytes:
    frames = b"".join(_frame(FRAMES[key], str(value)) for key, value in fields.items() if key in FRAMES and str(value).strip())
    return b"ID3\x03\x00\x00" + _syncsafe(len(frames)) + frames


def _chunks(data: bytes):
    offset = 12
    while offset + 8 <= len(data):
        chunk_id, size = data[offset:offset + 4], struct.unpack("<I", data[offset + 4:offset + 8])[0]
        end = offset + 8 + size
        if end > len(data):
            raise ValueError("file WAV troncato")
        yield chunk_id, data[offset:end + (size & 1)]
        offset = end + (size & 1)


def write_wav(path: Path, fields: dict) -> bool:
    data = Path(path).read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("non è un file WAV")
    tag = build(fields)
    kept = b"".join(chunk for chunk_id, chunk in _chunks(data) if chunk_id not in TAG_CHUNKS)
    chunk = b"id3 " + struct.pack("<I", len(tag)) + tag + (b"\x00" if len(tag) & 1 else b"")
    body = b"WAVE" + kept + chunk
    out = b"RIFF" + struct.pack("<I", len(body)) + body
    handle, temp = tempfile.mkstemp(dir=Path(path).parent, prefix=".tag-", suffix=".wav")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(out)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return True
