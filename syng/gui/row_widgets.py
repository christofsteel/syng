"""Configuration rows for forms."""

from __future__ import annotations

import os
from abc import abstractmethod
from functools import partial
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
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
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


class RowWidgetWithLayout[T](RowWidget[T]):
    """Base class for a RowWidget, that has a QLayout on the left."""

    _layout: QLayout

    @override
    def to_form_tuple(self) -> tuple[QLabel, QLayout]:
        return self._label, self._layout


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


class SettingWithDialogButton(RowWidgetWithLayout[str]):
    """Settings row for string values with a button.

    The left side consists of a horizontal layout with a line edit and a button.
    """

    valueChanged: Signal = Signal(str)

    _input_widget: QLineEdit
    _open_dialog_button: QPushButton

    @override
    def set_value(self, value: str) -> None:
        self._input_widget.setText(value)

    def line_edit_setter(self, value: str | None) -> None:
        """Set the text of a QLineEdit.

        If name is None, nothing happens.

        Args:
            value: The text to set, or None.
        """
        if value:
            self._input_widget.setText(value)

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


class StrListElement(QWidget):
    """Element for a StrListWidget.

    Contains a LineEdit for the value and a delete button

    Signals:
      valueChanged: Emits, when the containing value is change, contains the text as data
      deleteButtonClicked: Emits, when the delete button is clicked, contains the widget as data

    """

    input_field: QLineEdit
    minus_button: QPushButton
    valueChanged: Signal = Signal(str)
    deleteButtonClicked: Signal = Signal(QWidget)

    def button_clicked(self) -> None:
        """Emit the deleteButtonClicked signal."""
        self.deleteButtonClicked.emit(self)

    def __init__(self, parent: QWidget, initial_value: str) -> None:
        """Initializes the element with a line edit and a delete button.

        Args:
            parent: Qt parent widget
            initial_value: initial value of the widget

        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        self.input_field = QLineEdit(self)
        self.input_field.setText(initial_value)
        self.input_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.input_field)
        self.input_field.textChanged.connect(lambda value: self.valueChanged.emit(value.strip()))

        self.minus_button = QPushButton(QIcon.fromTheme("list-remove"), "", self)
        self.minus_button.setFixedWidth(40)
        self.minus_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.minus_button)
        self.minus_button.clicked.connect(self.button_clicked)


class StrListWidget(QWidget):
    """Widget, that holds list of strings.

    Contains a StrListElement for each value. Updates its model automatically.

    Signals:
        valueChanged: emits the value each time it is changed.

    """

    valueChanged: Signal = Signal(list)
    _layout: QVBoxLayout
    _values: list[str]

    def set_values(self, values: list[str]) -> None:
        """Set and replace all values.

        Args:
            values: new values
        """
        while self._layout.count() >= 1:
            row = self._layout.itemAt(0)
            if row is not None:
                widget = row.widget()
                if widget is not None and isinstance(widget, StrListElement):
                    self.remove_value(widget)

        for value in values:
            self.append_value(value)

    def append_value(self, value: str) -> None:
        """Add a new empty at the end of the widget.

        Also adds a new value to the internal list

        Args:
            value: The value to add

        """
        index = self._layout.count() - 1
        entry = StrListElement(self, value)
        entry.deleteButtonClicked.connect(self.remove_value)
        entry.input_field.textChanged.connect(partial(self.update_value, entry))
        self._layout.insertWidget(index, entry)
        self._values.append(value)
        self.valueChanged.emit(self._values)

    def update_value(self, widget: StrListElement, value: str) -> None:
        """Updates the internal value for a row.

        This is called, when the row emits, that its value has changed.

        Args:
            widget: The widget, that has triggered this callback
            value: The value of the widget

        """
        index = self._layout.indexOf(widget)
        self._values[index] = value
        self.valueChanged.emit(self._values)

    def remove_value(self, widget: StrListElement) -> None:
        """Remove a row and its value.

        This is called, when the row emits, that its delete button has been clicked.

        Args:
            widget: Row widget to remove

        """
        index = self._layout.indexOf(widget)
        self._layout.removeWidget(widget)
        widget.deleteLater()

        del self._values[index]
        self.valueChanged.emit(self._values)

    def __init__(self, parent: QWidget, initial_values: list[str]) -> None:
        """Initialize the widget and connect all signals.

        Args:
            parent: Qt parent widget
            initial_values: list of initial values

        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self._layout = layout
        self._values = []
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        plus_button = QPushButton(QIcon.fromTheme("list-add"), "", self)
        plus_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        plus_button.clicked.connect(lambda _: self.append_value(""))
        layout.addWidget(plus_button)

        for value in initial_values:
            self.append_value(value)


class StrListOption(RowWidget[list[str]]):
    """Settings row with a list of strings.

    Signals:
        valueChanged: emits, when some of its values has been changed.

    """

    valueChanged: Signal = Signal(list)
    _input_widget: StrListWidget

    @override
    def set_value(self, value: list[str]) -> None:
        self._input_widget.set_values(value)

    def __init__(self, parent: QWidget, initial_value: list[str], description: str) -> None:
        """Initializes the row.

        Args:
            parent: Qt parent widget
            initial_value: initial value of the widget
            description: text of the label

        """
        super().__init__(parent, initial_value, description)
        self._input_widget = StrListWidget(self, initial_value)
        self._input_widget.valueChanged.connect(self.valueChanged.emit)
