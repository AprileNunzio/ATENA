from typing import Callable, Awaitable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from server.core.security_guard.token_provider import token_provider
from server.shared.errors.domain_errors import UnauthorizedException

class ZeroTrustMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = {
        "/",
        "/web",
        "/health",
        "/docs",
        "/openapi.json",
        "/api/v1/auth/exchange",
        "/api/v1/stream/reasoning",
        "/api/v1/onboarding/profile",
        "/api/v1/onboarding/setup",
        "/api/v1/memory/cache/stats",
        "/api/v1/memory/cache/clear",
    }

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if (
            path in self.EXEMPT_PATHS
            or path.startswith("/static")
            or path.startswith("/web")
            or path.startswith("/api/v1/stream")
            or path.startswith("/api/v1/onboarding")
            or path.startswith("/api/v1/weather")
            or path.startswith("/api/v1/presence")
            or path.startswith("/api/v1/system")
            or path.startswith("/api/v1/privacy")
            or path.startswith("/api/v1/cognitive")
            or path.startswith("/api/v1/i18n")
            or request.method == "OPTIONS"
        ):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "status": "error",
                    "code": "MISSING_CREDENTIALS",
                    "message": "Authorization header missing or invalid format"
                }
            )

        token = auth_header.replace("Bearer ", "").strip()
        try:
            token_claims = token_provider.verify_token(token)
            request.state.user = token_claims
        except UnauthorizedException as exc:
            return JSONResponse(
                status_code=401,
                content={
                    "status": "error",
                    "code": exc.code,
                    "message": exc.message
                }
            )

        return await call_next(request)
