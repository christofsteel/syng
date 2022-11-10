from __future__ import annotations
import asyncio
from typing import Callable, Awaitable

from ..entry import Entry
from ..result import Result


def async_in_thread(func: Callable) -> Awaitable:
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)

    return wrapper


class Source:
    async def get_entry(self, performer: str, ident: int | str) -> Entry:
        pass

    async def search(self, query: str) -> list[Result]:
        pass

    async def buffer(self, ident: int | str) -> None:
        pass

    async def play(self, ident: str) -> None:
        pass

    async def skip_current(self) -> None:
        pass
