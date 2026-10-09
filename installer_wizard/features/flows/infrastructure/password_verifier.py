import asyncio
from typing import Callable


class PasswordVerifier:
    def __init__(self, authenticate: Callable[[str, str, str], bool]) -> None:
        self.authenticate = authenticate

    async def confirm(self, user: str, password: str, ip: str) -> bool:
        return await asyncio.to_thread(self.authenticate, user, password, ip)
