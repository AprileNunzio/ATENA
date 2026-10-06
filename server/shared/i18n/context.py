from contextvars import ContextVar

current_language: ContextVar[str] = ContextVar("current_language", default="en")
