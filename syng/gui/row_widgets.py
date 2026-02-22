"""Configuration rows for forms."""

from abc import abstractmethod
from collections.abc import Callable
from typing import override
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QLineEdit, QWidget


class RowWidget[T](QWidget):
    value: T
    _label: QLabel
    _input_widget: QWidget

    def __init__(
        self,
        parent: QWidget,
        initial_value: T,
        description: str,
    ) -> None:
        super().__init__(parent)
        self.value = initial_value
        self._label = QLabel(description, self)

    @override
    def setVisible(self, visible: bool, /) -> None:
        super().setVisible(visible)
        self._label.setVisible(visible)
        self._input_widget.setVisible(visible)

    def to_form_tuple(self) -> tuple[QLabel, QWidget]:
        return self._label, self._input_widget

    @abstractmethod
    def add_change_callback_raw(self, callback: Callable[[T], None]) -> None: ...

    @abstractmethod
    def set_value(self, value: T) -> None: ...
    @abstractmethod
    def get_value_raw(self) -> T: ...

    def get_value(self) -> T:
        return self._preprocess(self.get_value_raw())

    def add_change_callback(self, callback: Callable[[T], None]) -> None:
        self.add_change_callback_raw(lambda value: callback(self._preprocess(value)))

    def _preprocess(self, value: T) -> T:
        return value


class StringSetting(RowWidget[str]):
    _input_widget: QLineEdit

    def add_change_callback_raw(self, callback: Callable[[str], None]) -> None:
        self._input_widget.textChanged.connect(callback)

    def _preprocess(self, value: str) -> str:
        return value.strip()

    def set_value(self, value: str) -> None:
        self._input_widget.setText(value)

    def get_value(self) -> str:
        return self._input_widget.text()

    def __init__(
        self,
        parent: QWidget,
        initial_value: str,
        description: str,
    ) -> None:
        super().__init__(parent, initial_value, description)
        self._input_widget = QLineEdit(self)
        self._input_widget.insert(initial_value)


class PasswordSetting(StringSetting):
    def toggle_visibility(self) -> None:
        self._input_widget.setEchoMode(
            QLineEdit.EchoMode.Normal
            if self._input_widget.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password
        )
        if self._input_widget.echoMode() == QLineEdit.EchoMode.Password:
            self.visibility_action.setIcon(QIcon(":/icons/eye_strike.svg"))
        else:
            self.visibility_action.setIcon(QIcon(":/icons/eye_clear.svg"))

    def __init__(
        self,
        parent: QWidget,
        initial_value: str,
        description: str,
    ) -> None:
        super().__init__(parent, initial_value, description)
        self._input_widget.setEchoMode(QLineEdit.EchoMode.Password)
        self.visibility_action = self._input_widget.addAction(
            QIcon(":/icons/eye_strike.svg"),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self.visibility_action.triggered.connect(self.toggle_visibility)
