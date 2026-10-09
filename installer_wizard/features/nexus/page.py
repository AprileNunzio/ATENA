import re

from fastapi.responses import Response

from config import WEB_DIR
from pages import ASSET_VERSION

INDEX = WEB_DIR / "nexus" / "index.html"
_ASSET = re.compile(r'((?:src|href)="/static/nexus/[^"?]+)"')
CSP = "; ".join((
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "media-src 'self' blob:",
    "manifest-src 'self'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "require-trusted-types-for 'script'",
    "trusted-types 'none'",
))


def security_headers(https: bool) -> dict[str, str]:
    headers = {
        "Content-Security-Policy": CSP,
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Permissions-Policy": "camera=(), geolocation=(), payment=(), usb=(), microphone=(self)",
    }
    if https:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


def render(https: bool) -> Response:
    html = INDEX.read_text(encoding="utf-8")
    html = _ASSET.sub(lambda m: f'{m.group(1)}?v={ASSET_VERSION}"', html)
    return Response(html, media_type="text/html; charset=utf-8", headers=security_headers(https))
