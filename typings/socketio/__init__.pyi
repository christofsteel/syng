from typing import Any, Awaitable
from typing import Callable
from typing import Optional
from typing import TypeVar, TypeAlias

Handler: TypeAlias = Callable[[str], Awaitable[Any]]
DictHandler: TypeAlias = Callable[[str, dict[str, Any]], Awaitable[Any]]
ClientHandler = TypeVar("ClientHandler", bound=Callable[[dict[str, Any]], Any] | Callable[[], Any])

class _session_context_manager:
    async def __aenter__(self) -> dict[str, Any]: ...
    async def __aexit__(self, *args: list[Any]) -> None: ...

class AsyncServer:
    def __init__(
        self,
        cors_allowed_origins: str,
        logger: bool,
        engineio_logger: bool,
        json: Any,
    ): ...
    async def emit(
        self,
        message: str,
        body: Any = None,
        room: Optional[str] = None,
    ) -> None: ...
    def session(self, sid: str) -> _session_context_manager: ...
    def on(
        self, event: str, handler: Optional[Handler | DictHandler] = None
    ) -> Callable[[Handler | DictHandler], Handler | DictHandler]: ...
    async def enter_room(self, sid: str, room: str) -> None: ...
    async def leave_room(self, sid: str, room: str) -> None: ...
    def attach(self, app: Any) -> None: ...
    async def disconnect(self, sid: str) -> None: ...
    def instrument(self, auth: dict[str, str]) -> None: ...

class AsyncClient:
    def __init__(self, json: Any = None): ...
    def on(
        self, event: str, handler: Optional[Callable[..., Any]] = None
    ) -> Callable[[ClientHandler], ClientHandler]: ...
    async def wait(self) -> None: ...
    async def connect(self, server: str) -> None: ...
    async def disconnect(self) -> None: ...
    async def emit(self, message: str, data: Any = None) -> None: ...
