import re
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .context import current_language
from .provider import global_translator

class I18nMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._lang_pattern = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        accept_language = request.headers.get("Accept-Language", "")
        lang_to_set = global_translator._config.default_language
        
        if accept_language:
            parts = accept_language.split(",")
            for part in parts:
                lang = part.split(";")[0].strip()
                if self._lang_pattern.match(lang):
                    if lang in global_translator._config.supported_languages:
                        lang_to_set = lang
                        break
                    
                    base_lang = lang.split("-")[0]
                    if base_lang in global_translator._config.supported_languages:
                        lang_to_set = base_lang
                        break
        
        token = current_language.set(lang_to_set)
        try:
            return await call_next(request)
        finally:
            current_language.reset(token)
