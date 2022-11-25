from __future__ import annotations
import shlex
import asyncio
from typing import Callable, Awaitable
import os.path

from ..entry import Entry
from ..result import Result


def async_in_thread(func: Callable) -> Awaitable:
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)

    return wrapper


class Source:
    async def get_entry(self, performer: str, ident: str) -> Entry:
        raise NotImplementedError

    async def search(self, result_future: asyncio.Future, query: str) -> None:
        raise NotImplementedError

    async def buffer(self, entry: Entry) -> dict:
        return {}

    async def play(self, entry: Entry) -> None:
        raise NotImplementedError

    async def skip_current(self, entry: Entry) -> None:
        pass

    async def init_server(self) -> None:
        pass

    async def init_client(self) -> None:
        pass

    def filter_data_by_query(self, query: str, data: list[str]) -> list[str]:
        def contains_all_words(words: list[str], element: str) -> bool:
            for word in words:
                if not word.lower() in os.path.basename(element).lower():
                    return False
            return True

        splitquery = shlex.split(query)
        return [element for element in data if contains_all_words(splitquery, element)]

    async def get_config(self) -> dict:
        raise NotImplementedError

    def add_to_config(self, config) -> None:
        pass


available_sources = {}
