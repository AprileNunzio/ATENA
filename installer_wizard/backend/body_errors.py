import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


async def _malformed(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "Richiesta non valida: il corpo non è JSON UTF-8"}, status_code=400)


def install(app: FastAPI) -> None:
    app.add_exception_handler(json.JSONDecodeError, _malformed)
    app.add_exception_handler(UnicodeDecodeError, _malformed)
