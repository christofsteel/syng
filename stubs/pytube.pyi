from __future__ import annotations
from collections.abc import Iterable
from typing import Any, Callable, Iterator, Optional

class exceptions:
    class PytubeError(Exception): ...

class Channel:
    channel_id: str

    def __init__(self, url: str) -> None:
        pass

class innertube:
    class InnerTube:
        base_url: str
        base_data: dict[str, str]
        base_params: dict[str, str]

        def _call_api(
            self, endpoint: str, params: dict[str, str], data: dict[str, str]
        ) -> dict[str, Any]: ...
        def __init__(self, client: str) -> None: ...

class Stream:
    resolution: str
    is_progressive: bool
    is_adaptive: bool
    abr: str
    def download(
        self,
        output_path: Optional[str] = None,
        filename_prefix: Optional[str] = None,
    ) -> str: ...

class StreamQuery(Iterable[Stream]):
    resolution: str
    def filter(
        self,
        type: Optional[str] = None,
        custom_filter_functions: Optional[
            list[Callable[[StreamQuery], bool]]
        ] = None,
        only_audio: bool = False,
    ) -> StreamQuery: ...
    def __iter__(self) -> Iterator[Stream]: ...

class YouTube:
    def __init__(self, url: str) -> None: ...

    length: int
    title: str
    author: str
    watch_url: str
    streams: StreamQuery

class Search:
    results: Optional[list[YouTube]]

    def __init__(self, query: str) -> None: ...
