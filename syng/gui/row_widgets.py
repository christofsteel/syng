"""Configuration rows for forms."""

from __future__ import annotations

import os
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import partial
from typing import (
    get_args,
    get_origin,
    overload,
    override,
)

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class Boolean:
    """Wrapper for boolean types.

    This is needed, because bool is a subtype of int. This class is not.
    """

    value: bool


type SupportedBaseType = Boolean | int | str | datetime | list[str]
type SupportedType[T: Enum] = SupportedBaseType | T
type MkInputWidget[T: SupportedBaseType | Enum] = Callable[[T], InputWidget[T]]
type MkSupportedInputWidget[T: Enum] = (
    MkInputWidget[bool]
    | MkInputWidget[int]
    | MkInputWidget[str]
    | MkInputWidget[datetime]
    | MkInputWidget[list[str]]
    | MkInputWidget[T]
)


@overload
def get_input_widget(ty: type[Boolean], semantic: str | None) -> MkInputWidget[bool]: ...
@overload
def get_input_widget(ty: type[int], semantic: str | None) -> MkInputWidget[int]: ...
@overload
def get_input_widget(ty: type[str], semantic: str | None) -> MkInputWidget[str]: ...
@overload
def get_input_widget(ty: type[datetime], semantic: str | None) -> MkInputWidget[datetime]: ...
@overload
def get_input_widget(ty: type[list[str]], semantic: str | None) -> MkInputWidget[list[str]]: ...


def get_input_widget[T: Enum](
    ty: type[SupportedType[T]], semantic: str | None
) -> MkSupportedInputWidget[T]:
    """Get the appropriate Input Widget for a type and semantic.

    TypeVar:
        T: Generic Type for enum support

    Args:
        ty: The type of the input
        semantic: A special semantic for the type

    Returns:
        A builder for an input widget for the type and semantic

    Raises:
        TypeError: if the type is not a supported type

    """
    if ty is Boolean:
        return CheckBox
    elif ty is int:
        return SpinBox
    elif ty is str:
        match semantic:
            case "password":
                return PasswordLineEdit
            case "folder":
                return FolderInputWidget
            case "file":
                return FileInputWidget
            case _:
                return LineEdit
    elif ty is datetime:
        return DateTimeEdit
    elif get_origin(ty) is list and get_args(ty) == (str,):
        return StrListInputWidget
    elif issubclass(ty, Enum):
        return partial(ComboBox, ty)
    raise TypeError(f"Type {ty} is not supported.")


def get_fallback[T: Enum](ty: type[SupportedType[T]]) -> SupportedType[T]:
    """Get a fallback value for a type.

    Args:
        ty: type

    Returns:
        A fallback value of the type

    Raises:
        TypeError: if type is not supported

    """
    if ty is datetime:
        return datetime.now()
    elif ty is str:
        return ""
    elif ty is int:
        return 0
    elif get_origin(ty) is list:
        return []
    elif issubclass(ty, Enum):
        return [choice for choice in ty][0]
    elif ty is Boolean:
        return True
    raise TypeError(f"Type {ty} is not supported.")


def make_input_widget[T](ty: type[T], semantic: str | None, value: T) -> InputWidget[T]:
    """Create and instantiate a input widget for the given type and semantic.

    Args:
        ty: The type of the input
        semantic: A special semantic for the type
        value: Initial value of the widget

    Returns:
        A InputWidget for ty and semantic with the value.
    """
    input_widget_builder: MkInputWidget[T] = get_input_widget(ty, semantic)  # type: ignore
    return input_widget_builder(value)


def make_optional_input_widget[T](
    ty: type[T | None], semantic: str | None, value: T | None
) -> InputWidget[T | None]:
    """Create and instantiate a deactivatable input widget for the given type and semantic.

    Args:
        ty: The type of the input
        semantic: A special semantic for the type
        value: Initial value of the widget

    Returns:
        A DeactivatableInputWidget containing a Widget for ty and semantic with the value.
    """
    input_widget_builder: MkInputWidget[T] = get_input_widget(ty, semantic)  # type: ignore
    fallback: T = get_fallback(ty)  # type: ignore
    return partial(DeactivatableInputWidget.wrap, fallback)(input_widget_builder)(value)


class InputWidget[T](QWidget):
    """Parentclass for widgets, that store Configuration data.

    Attributes:
        value: The current value of the data

    Signals:
        valueChanged: Triggers each time, the data is changed.
    """

    value: T
    valueChanged: Signal

    def __init__(self, initial_value: T, parent: QWidget | None = None) -> None:
        """Construct the InputWidget.

        Args:
            initial_value: Value, stored by the InputWidget
            parent: Qt-parent object
        """
        super().__init__()
        self.setParent(parent)
        self.value = initial_value

    @abstractmethod
    def set_widget_value(self, value: T) -> None:
        """Set the value of the internal Widget.

        Args:
            value: The value to set

        """

    def set_value(self, value: T) -> None:
        """Set the internal value.

        Also updates the widget value.
        """
        self.value = value
        self.set_widget_value(value)


class SimpleInputWidget[T](InputWidget[T]):
    """Parentclass for InputWidgets, that hold exactly one QWidget."""

    _input_widget: QWidget

    @override
    def __init__(self, widget: QWidget, initial_value: T, parent: QWidget | None = None) -> None:
        super().__init__(initial_value, parent)
        self._input_widget = widget
        layout = QStackedLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        if layout:
            layout.addWidget(widget)
        widget.setParent(self)


class LineEdit(SimpleInputWidget[str]):
    """InputWidget for string values.

    Encapsules a QLineEdit.
    """

    valueChanged = Signal(str)
    _input_widget: QLineEdit

    @override
    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__(QLineEdit(value), value, parent)
        self._input_widget.textChanged.connect(self.valueChanged.emit)

    @override
    def set_widget_value(self, value: str) -> None:
        self._input_widget.setText(value)


class PushButton(SimpleInputWidget[None]):
    """InputWidget that triggers with no data.

    Encapsules a QPushButton.
    """

    valueChanged = Signal()
    _input_widget: QPushButton

    @override
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(QPushButton(), None, parent)
        self._input_widget.clicked.connect(lambda: self.valueChanged.emit())

    @override
    def set_widget_value(self, value: None) -> None:
        pass

    def set_icon(self, icon: QIcon) -> None:
        """Set the icon of the Button.

        Args:
            icon: The icon to set.
        """
        self._input_widget.setIcon(icon)


class SplitInputWidget[T, U, V](InputWidget[V]):
    """Parentclass for InputWidgets with two InputWidgets.

    Generic Variable:
        T: Value type of the left InputWidget
        U: Value type of the right InputWidget
        V: Value type of the combined InputWidget

    Attributes:
        left_widget: InputWidget on the left
        right_widget: InputWidget on the right
    """

    left_widget: InputWidget[T]
    right_widget: InputWidget[U]

    @override
    def __init__(
        self,
        left_widget: InputWidget[T],
        right_widget: InputWidget[U],
        initial_value: V,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(initial_value, parent)

        self.left_widget = left_widget
        self.right_widget = right_widget
        self.setParent(parent)

        self.left_widget.setParent(self)
        self.right_widget.setParent(self)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        layout.addWidget(left_widget)
        layout.addWidget(right_widget)


class SplitInputWidgetLeft[T](SplitInputWidget[T, None, T]):
    """Parentclass for InputWidgets with two widgets, where the data comes from the left widget."""

    @override
    def __init__(
        self,
        left_widget: InputWidget[T],
        right_widget: InputWidget[None],
        initial_value: T,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(left_widget, right_widget, initial_value, parent)
        self.left_widget.valueChanged.connect(self.valueChanged.emit)

    @override
    def set_widget_value(self, value: T) -> None:
        self.left_widget.set_widget_value(value)


class LineButtonInputWidget(SplitInputWidgetLeft[str]):
    """Parentclass for InputWidgets with a QLineEdit and a QPushButton."""

    valueChanged = Signal(str)
    left_widget: LineEdit
    right_widget: PushButton

    @override
    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__(LineEdit(value), PushButton(), value, parent)
        self.left_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.right_widget.setFixedWidth(40)
        self.right_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    def set_button_icon(self, icon: QIcon) -> None:
        """Set the icon of the button.

        Args:
            icon: The icon to set
        """
        self.right_widget.set_icon(icon)

    def line_edit_setter(self, value: str | None) -> None:
        """Set the text of a QLineEdit.

        If name is None, nothing happens.

        Args:
            value: The text to set, or None.
        """
        if value:
            self.set_value(value)


class FileInputWidget(LineButtonInputWidget):
    """InputWidget for string values, that represent a file path.

    Encapsules a QLineEdit and a QPushButton, that opens a QFileDialog for a file.
    """

    @override
    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__(value, parent)
        self.set_button_icon(QIcon.fromTheme("document-open"))
        self.right_widget.valueChanged.connect(
            lambda: self.line_edit_setter(
                QFileDialog.getOpenFileName(self, "Select File", dir=os.path.dirname(self.value))[
                    0
                ],
            )
        )


class FolderInputWidget(LineButtonInputWidget):
    """InputWidget for string values, that represent a folder path.

    Encapsules a QLineEdit and a QPushButton, that opens a QFileDialog for a directory.
    """

    @override
    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__(value, parent)
        self.set_button_icon(QIcon.fromTheme("folder-open"))
        self.right_widget.valueChanged.connect(
            lambda: self.line_edit_setter(
                QFileDialog.getExistingDirectory(
                    self, "Select Folder", dir=os.path.dirname(self.value)
                )
            )
        )


class PasswordLineEdit(LineEdit):
    """InputWidget for string values, that can be hidden.

    Adds a clickable Icon to the parent line edit, to hide and show the contents.
    """

    @override
    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__(value, parent)
        self._input_widget.setEchoMode(QLineEdit.EchoMode.Password)
        self.visibility_action = self._input_widget.addAction(
            QIcon(":/icons/eye_strike.svg"),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self.visibility_action.triggered.connect(self.toggle_visibility)

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


class CheckBox(SimpleInputWidget[bool]):
    """InputWidget for Boolean values.

    Encapsules a QCheckbox.
    """

    valueChanged = Signal(bool)
    _input_widget: QCheckBox

    @override
    def __init__(self, value: bool, parent: QWidget | None = None) -> None:
        super().__init__(QCheckBox(), value, parent)
        self._input_widget.setChecked(value)
        self._input_widget.checkStateChanged.connect(
            lambda state: self.valueChanged.emit(state == Qt.CheckState.Checked)
        )

    @override
    def set_widget_value(self, value: bool) -> None:
        self._input_widget.setChecked(value)


class SpinBox(SimpleInputWidget[int]):
    """InputWidget for integer values.

    Encapsules a QSpinBox
    """

    valueChanged = Signal(int)
    _input_widget: QSpinBox

    @override
    def __init__(self, value: int, parent: QWidget | None = None) -> None:
        super().__init__(QSpinBox(value=value), value, parent)
        self._input_widget.setParent(self)
        self._input_widget.textChanged.connect(lambda text: self.valueChanged.emit(int(text)))

    @override
    def set_widget_value(self, value: int) -> None:
        self._input_widget.setValue(value)


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
    _input_widget: InputWidget[T]

    def __init__(
        self,
        initial_value: T,
        description: str,
        input_widget: InputWidget[T],
        parent: QWidget,
    ) -> None:
        """Initialize the row.

        Args:
            initial_value: initial value of the widget
            description: The description text
            input_widget: The widget on the right
            parent: Qt parent widget

        """
        super().__init__(parent)
        self.value = initial_value
        self._label = QLabel(description, self)
        self.valueChanged.connect(self._set_internal_value)
        self._input_widget = input_widget
        self._input_widget.valueChanged.connect(self.valueChanged.emit)
        self._input_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

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

    def set_value(self, value: T) -> None:
        """Set the value of the input widget.

        Args:
            value: new value
        """
        self._input_widget.set_value(value)

    def _set_internal_value(self, value: T) -> None:
        """Update the internal value.

        Args:
            value: new value
        """
        self.value = value


def make_row[T](
    signal: Signal,
    description: str,
    input_widget: InputWidget[T],
    parent: QWidget,
) -> RowWidget[T]:
    """Create a settings row for a given input widget.

    We need this work around, to enable the Qt-Signals.

    Args:
        signal: The Qt-Signal type to emit, if the value has changed.
        description: The text on the description label.
        input_widget: The input widget on the right.
        parent: The Qt-parent object.

    Returns:
        A row containing a description label on the right and the input widget on the left.

    """

    class SettingsRow(RowWidget[T]):
        valueChanged = signal

        def __init__(self) -> None:
            super().__init__(input_widget.value, description, input_widget, parent)
            self._input_widget.setParent(self)

    return SettingsRow()


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

    def __init__(self, initial_values: list[str], parent: QWidget | None = None) -> None:
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


class StrListInputWidget(SimpleInputWidget[list[str]]):
    """InputWidget for a list of strings.

    Encapsules a StrListWidget.
    """

    valueChanged = Signal(list)
    _input_widget: StrListWidget

    @override
    def __init__(self, initial_value: list[str], parent: QWidget | None = None) -> None:
        super().__init__(StrListWidget(initial_value), initial_value, parent)
        self._input_widget.valueChanged.connect(self.valueChanged)

    @override
    def set_widget_value(self, value: list[str]) -> None:
        self._input_widget.set_values(value)


class ComboBox[T: Enum](SimpleInputWidget[T]):
    """InputWidget for values from an Enum.

    Options are presented in a QComboxBox.
    """

    valueChanged = Signal(Enum)
    _input_widget: QComboBox
    _enum: type[T]

    @override
    def __init__(
        self, enum_class: type[T], initial_value: T, parent: QWidget | None = None
    ) -> None:
        super().__init__(QComboBox(), initial_value, parent)
        self._enum = enum_class
        self._input_widget.addItems([str(v.value) for v in enum_class])
        self._input_widget.setCurrentText(str(initial_value.value))
        self._input_widget.currentTextChanged.connect(self.emit_enum)

    def emit_enum(self, value: str) -> None:
        """Try to emit a string into an enum value.

        Identification is done first via the string representation, then via the int
        representation.

        Args:
            value: value as string

        """
        try:
            enum = self._enum(value)
        except ValueError:
            enum = self._enum(int(value))
        self.valueChanged.emit(enum)

    @override
    def set_widget_value(self, value: T) -> None:
        self._input_widget.setCurrentText(str(value.value))


class DeactivatableInputWidget[T](SplitInputWidget[T, bool, T | None]):
    """Encapsules an InputWidget to be deactivatable.

    This creates a widget, consisting of a left InputWidget and a Checkbox on the right. The
    Checkbox enables the left widget. If it is disabled, the value of this widget is None, otherwise
    it is the value of the left widget.

    Attributes:
        left_widget: The encapsulated Widget
        right_widget: Always a Checkbox

    """

    left_widget: InputWidget[T]
    right_widget: CheckBox
    valueChanged = Signal(object)

    @override
    def __init__(
        self, left_widget: InputWidget[T], initial_value: T | None, parent: QWidget | None = None
    ) -> None:
        super().__init__(left_widget, CheckBox(initial_value is not None), initial_value, parent)

        self.left_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.left_widget.valueChanged.connect(self.valueChanged.emit)
        self.left_widget.valueChanged.connect(print)
        self.right_widget._input_widget.setText("Enabled")
        self.right_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.right_widget.valueChanged.connect(self.toggle_enabled)
        if initial_value is None:
            self.left_widget.setEnabled(False)

    def toggle_enabled(self, enabled: bool) -> None:
        """Enable/Disables the encapsulated widget.

        This will trigger a valueChanged.

        Args:
            enabled: If True, enables the widget, otherwise it disables it.
        """
        value = self.left_widget.value if enabled else None
        self.left_widget.setEnabled(enabled)
        if value is not None:
            self.left_widget.set_value(value)
        self.valueChanged.emit(value)

    @staticmethod
    def wrap(
        fallback: T,
        input_widget_builder: Callable[[T], InputWidget[T]],
    ) -> Callable[[T | None], DeactivatableInputWidget[T]]:
        """Transforms a factory function for an input widget to a deactivatable one.

        Args:
            fallback: Value of the internal widget, in case the value is None
            input_widget_builder: Factory function for the internal InputWidget

        Returns:
            Factory function for a deactivatable input widget.

        """

        def wrapped(initial_value: T | None) -> DeactivatableInputWidget[T]:
            value = initial_value if initial_value else fallback
            input_widget = input_widget_builder(value)
            deactivatable_input_widget = DeactivatableInputWidget(input_widget, initial_value, None)
            return deactivatable_input_widget

        return wrapped

    @override
    def set_widget_value(self, value: T | None) -> None:
        if value is None:
            self.left_widget.setEnabled(False)
            self.right_widget.set_widget_value(False)
        else:
            self.left_widget.setEnabled(True)
            self.right_widget.set_widget_value(True)
            self.left_widget.set_widget_value(value)


class DateTimeEdit(SimpleInputWidget[datetime]):
    """InputWidget for a datetime object.

    Encapsules a QDateTimeEdit.
    """

    valueChanged = Signal(datetime)
    _input_widget: QDateTimeEdit

    @override
    def __init__(self, initial_value: datetime | None, parent: QWidget | None = None) -> None:
        super().__init__(
            QDateTimeEdit(
                QDateTime.fromString(
                    (initial_value if initial_value else datetime.now()).isoformat(),
                    Qt.DateFormat.ISODate,
                )
            ),
            initial_value if initial_value else datetime.now(),
            parent,
        )
        self._input_widget.dateTimeChanged.connect(
            lambda value: self.valueChanged.emit(value.toPython())
        )
        self._input_widget.setCalendarPopup(True)

    @override
    def set_widget_value(self, value: datetime) -> None:
        self._input_widget.setDateTime(
            QDateTime.fromString(value.isoformat(), Qt.DateFormat.ISODate)
        )
