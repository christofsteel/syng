from types import TracebackType
from typing import Optional
import PyQt6.QtWidgets
from asyncio import BaseEventLoop

class QApplication(PyQt6.QtWidgets.QApplication):
    def __init__(self, argv: list[str]) -> None: ...

class QEventLoop(BaseEventLoop):
    def __init__(self, app: QApplication) -> None: ...
    def __enter__(self) -> None: ...
    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None: ...
