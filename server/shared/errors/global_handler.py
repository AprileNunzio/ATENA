import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from server.shared.errors.domain_errors import AtenaBaseException

logger = logging.getLogger("atena.error_handler")

def register_global_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AtenaBaseException)
    async def handle_atena_exception(request: Request, exc: AtenaBaseException) -> JSONResponse:
        status_map = {
            "UNAUTHORIZED": 401,
            "BIOMETRIC_REJECTED": 403,
            "ENTITY_NOT_FOUND": 404,
            "AGENT_EXECUTION_FAILURE": 502,
            "SANDBOX_VIOLATION": 400
        }
        status_code = status_map.get(exc.code, 500)
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "error",
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "path": str(request.url)
            }
        )

    @app.exception_handler(Exception)
    async def handle_generic_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception at %s", request.url)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unhandled internal fault occurred in Atena runtime",
                "path": str(request.url)
            }
        )
