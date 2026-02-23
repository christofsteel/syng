"""Configuration rows for forms."""

import os
from abc import abstractmethod
from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)


class RowWidget[T](QWidget):
    """Base class for all setting rows.

    A row consists of a Label on the left side with a description and a widget, that contains some
    input widget on the left side holding some value.

    When the widget changes, the value is updated.

    Subclasses should set the ``_input_widget`` and connect its update signal to the valueChanged
    signal.

    Generic Types:
        T: Type of the value

    Signals:
        valueChanged: Emits the containing value every time the widget changes

    """

    value: T
    valueChanged: Signal
    _label: QLabel
    _input_widget: QWidget

    def __init__(
        self,
        parent: QWidget,
        initial_value: T,
        description: str,
    ) -> None:
        """Initialize the row.

        Args:
            parent: Qt parent widget
            initial_value: initial value of the widget
            description: text of the label

        """
        super().__init__(parent)
        self.value = initial_value
        self._label = QLabel(description, self)
        self.valueChanged.connect(self._set_internal_value)

    @override
    def setVisible(self, visible: bool, /) -> None:
        """Set the visibility of the row.

        Args:
            visible: Visibility

        """
        super().setVisible(visible)
        self._label.setVisible(visible)
        self._input_widget.setVisible(visible)

    def to_form_tuple(self) -> tuple[QLabel, QLayout] | tuple[QLabel, QWidget]:
        """Construct a value, that can be insertet into a form.

        Returns:
            Tuple of the label and the right hand side widget.

        """
        return self._label, self._input_widget

    def _set_internal_value(self, value: T) -> None:
        """Update the internal value.

        Args:
            value: new value
        """
        self.value = value

    @abstractmethod
    def set_value(self, value: T) -> None:
        """Set the value of the input widget.

        Args:
            value: new value
        """


class BoolSetting(RowWidget[bool]):
    """Settings row for a Boolean value."""

    _input_widget: QCheckBox
    valueChanged: Signal = Signal(bool)

    def __init__(self, parent: QWidget, initial_value: bool, description: str) -> None:
        """Initialize the row and create a QCheckbox."""
        super().__init__(parent, initial_value, description)
        self._input_widget = QCheckBox(self)
        self._input_widget.setChecked(initial_value)
        self._input_widget.checkStateChanged.connect(
            lambda state: self.valueChanged.emit(state == Qt.CheckState.Checked)
        )

    def set_value(self, value: bool) -> None:
        """Update the value of the QCheckBox."""
        self._input_widget.setChecked(value)


class IntSetting(RowWidget[int]):
    """Settings row for an integer value."""

    _input_widget: QSpinBox
    valueChanged: Signal = Signal(int)

    def __init__(self, parent: QWidget, initial_value: int, description: str) -> None:
        """Initialize the row and create a QSpinBox."""
        super().__init__(parent, initial_value, description)
        self._input_widget = QSpinBox(self, value=initial_value)
        self._input_widget.textChanged.connect(lambda value: self.valueChanged.emit(int(value)))

    def set_value(self, value: int) -> None:
        """Update the value of the QSpinBox."""
        self._input_widget.setValue(value)


class StringSetting(RowWidget[str]):
    """Settings row for an string value."""

    _input_widget: QLineEdit
    valueChanged: Signal = Signal(str)

    def __init__(
        self,
        parent: QWidget,
        initial_value: str,
        description: str,
    ) -> None:
        """Initialize the row and create a QLineEdit."""
        super().__init__(parent, initial_value, description)
        self._input_widget = QLineEdit(initial_value, self)
        self._input_widget.textChanged.connect(lambda value: self.valueChanged.emit(value.strip()))

    def set_value(self, value: str) -> None:
        """Update the value of the QLineEdit."""
        self._input_widget.setText(value)


class PasswordSetting(StringSetting):
    """Settings row for a password value."""

    def toggle_visibility(self) -> None:
        """Toggle the visibility of the contents of the input field."""
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
        """Initialize the row and add a button to hide the contents of the input field."""
        super().__init__(parent, initial_value, description)
        self._input_widget.setEchoMode(QLineEdit.EchoMode.Password)
        self.visibility_action = self._input_widget.addAction(
            QIcon(":/icons/eye_strike.svg"),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self.visibility_action.triggered.connect(self.toggle_visibility)


class SettingWithDialogButton(RowWidget[str]):
    """Settings row for string values with a button.

    The left side consists of a horizontal layout with a line edit and a button.
    """

    valueChanged: Signal = Signal(str)

    _input_widget: QLineEdit
    _open_dialog_button: QPushButton
    _layout: QHBoxLayout

    def line_edit_setter(self, value: str | None) -> None:
        """Set the text of a QLineEdit.

        If name is None, nothing happens.

        Args:
            value: The text to set, or None.
        """
        if value:
            self._input_widget.setText(value)

    def to_form_tuple(self) -> tuple[QLabel, QLayout]:
        """Construct a value, that can be insertet into a form.

        Returns:
            Tuple of the label and the layout containing the QLineEdit and button.

        """
        return (self._label, self._layout)

    def __init__(
        self,
        parent: QWidget,
        initial_value: str,
        description: str,
        button: QPushButton,
    ) -> None:
        """Initialize the row, the layout and the containing widgets."""
        super().__init__(parent, initial_value, description)
        self._layout = QHBoxLayout()
        self._input_widget = QLineEdit(initial_value, self)
        self._open_dialog_button = button

        self._layout.addWidget(self._input_widget)
        self._layout.addWidget(self._open_dialog_button)
        self._input_widget.textChanged.connect(self.valueChanged.emit)


class FileSetting(SettingWithDialogButton):
    """Settings row with a file open dialog."""

    def __init__(self, parent: QWidget, initial_value: str, description: str) -> None:
        """Initialize the row and set the button to open a file open dialog."""
        super().__init__(
            parent,
            initial_value,
            description,
            QPushButton(QIcon.fromTheme("document-open"), ""),
        )
        self._open_dialog_button.clicked.connect(
            lambda: self.line_edit_setter(
                QFileDialog.getOpenFileName(
                    self, "Select File", dir=os.path.dirname(self._input_widget.text())
                )[0],
            )
        )


class FolderSetting(SettingWithDialogButton):
    """Settings row with a folder open dialog."""

    def __init__(self, parent: QWidget, initial_value: str, description: str) -> None:
        """Initialize the row and set the button to open a folder open dialog."""
        super().__init__(
            parent,
            initial_value,
            description,
            QPushButton(QIcon.fromTheme("folder-open"), ""),
        )
        self._open_dialog_button.clicked.connect(
            lambda: self.line_edit_setter(
                QFileDialog.getExistingDirectory(
                    self, "Select Folder", dir=os.path.dirname(self._input_widget.text())
                ),
            )
        )
