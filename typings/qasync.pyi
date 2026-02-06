from asyncio import BaseEventLoop
from types import TracebackType

import PyQt6.QtWidgets

class QApplication(PyQt6.QtWidgets.QApplication):
    def __init__(self, argv: list[str]) -> None: ...

class QEventLoop(BaseEventLoop):
    def __init__(self, app: QApplication) -> None: ...
    def __enter__(self) -> None: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
