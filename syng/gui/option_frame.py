"""Windget, that hold options depending on the types of a configuration object."""

import os
from collections.abc import Callable
from dataclasses import asdict, fields
from datetime import datetime
from enum import Enum
from functools import partial
from types import NoneType, UnionType
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
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

from syng.config import Config


class OptionFrame(QWidget):
    """Widget, holding a configuration object and building a form for that object.

    It supports adding rows to the form depending on the type of a configuration object. And updates
    these configuration values continuously.

    Attributes:
        config: Configuration object
    """

    config: Config

    def add_rows_from_config(self, config: Config) -> None:
        """Add rows for each option in config.

        Use metadata["desc"] for the text in the label, skip if metadata["hidden"] is True.
        The type of the input field is determined by the annotated type in the configuration object.

        Args:
            config: Configuration object

        """
        config_types = get_type_hints(config.__class__)
        values = config.__dict__

        for field in fields(config):
            name = field.name
            description: str = field.metadata.get("desc", "")
            semantic: str | None = field.metadata.get("semantic", None)
            hidden: bool = field.metadata.get("hidden", False)
            if hidden:
                continue

            field_type = config_types[name]
            value = values[name]
            if get_origin(field_type) in (Union, UnionType):
                args = get_args(field_type)
                if NoneType in args:
                    parts = [ty for ty in args if ty is not NoneType]
                    if len(parts) == 1:
                        field_type = parts[0]

            self.add_option(field_type, name, description, value, semantic)

    def add_option[T](
        self, ty: type[T], name: str, description: str, value: T, semantic: str | None
    ) -> None:
        """Add a row to the form, depending on the type of an option.

        The following types are supported:
            - bool
            - int
            - str (with semantics: "password", "folder", "file" or None)
            - list[str]
            - datetime (result can be None)
            - enums

        Args:
            ty: The type for which to add a row
            name: The attribute name in the config object (for the update callback)
            description: Label for the inputfield
            value: Initial value
            semantic: Semantic specification of the type (see above)

        """
        if ty is bool:
            self.add_bool_option(name, description, value=cast(bool, value))
        elif ty is int:
            self.add_int_option(name, description, value=cast(int, value))
        elif ty is str:
            if semantic == "password":
                self.add_string_option(name, description, value=cast(str, value), is_password=True)
            elif semantic == "folder":
                self.add_folder_option(name, description, value=cast(str, value))
            elif semantic == "file":
                self.add_file_option(name, description, value=cast(str, value))
            elif semantic is None:
                self.add_string_option(name, description, value=cast(str, value))
        elif get_origin(ty) is list and get_args(ty) == (str,):
            self.add_list_option(name, description, value=cast(list[str], value))
        elif ty is datetime:
            self.add_date_time_option(name, description, cast(datetime | None, value))
        elif issubclass(ty, Enum) and hasattr(value, "value"):
            values = [a.value for a in ty.__members__.values()]
            self.add_choose_option(name, description, values, value.value, ty)

    def set_string_config_field(self, name: str, value: str) -> None:
        """Set a string field of the configuration object, if it exists.

        Strips the value of whitespaces.
        If the object does not have the attribute, nothing happens.

        Args:
            name: name of the attribute
            value: value to set

        """
        self.set_config_field(name, value.strip())

    def set_config_field(self, name: str, value: Any) -> None:
        """Set a field of the configuration object, if it exists.

        If the object does not have the attribute, nothing happens.

        Args:
            name: name of the attribute
            value: value to set

        """
        if hasattr(self.config, name):
            setattr(self.config, name, value)

    def add_bool_option(self, name: str, description: str, value: bool = False) -> None:
        """Add a checkbox for a boolean option.

        Also add a listener to update the corresponding attribute when this value is changed.

        Args:
            name: Name of the attribute
            description: Text of the label
            value: initial Value

        """
        label = QLabel(description, self)

        self.bool_options[name] = QCheckBox(self)
        self.bool_options[name].setChecked(value)
        self.form_layout.addRow(label, self.bool_options[name])
        self.rows[name] = (label, self.bool_options[name])
        self.bool_options[name].checkStateChanged.connect(
            lambda state: self.set_config_field(name, state == Qt.CheckState.Checked)
        )

    def add_string_option(
        self,
        name: str,
        description: str,
        value: str | None = "",
        callback: Callable[..., None] | None = None,
        is_password: bool = False,
    ) -> None:
        """Add an input field for a string option.

        Also add a listener to update the corresponding attribute when this value is changed.

        Args:
            name: Name of the attribute
            description: Text of the label
            value: initial Value
            callback: Addional callback
            is_password: If true, input field is a password field

        """
        if value is None:
            value = ""

        label = QLabel(description, self)

        self.string_options[name] = QLineEdit(self)
        self.string_options[name].textChanged.connect(partial(self.set_string_config_field, name))
        if is_password:
            self.string_options[name].setEchoMode(QLineEdit.EchoMode.Password)
            action = self.string_options[name].addAction(
                QIcon(":/icons/eye_strike.svg"),
                QLineEdit.ActionPosition.TrailingPosition,
            )

            if action is not None:

                def toggle_visibility() -> None:
                    self.string_options[name].setEchoMode(
                        QLineEdit.EchoMode.Normal
                        if self.string_options[name].echoMode() == QLineEdit.EchoMode.Password
                        else QLineEdit.EchoMode.Password
                    )
                    if self.string_options[name].echoMode() == QLineEdit.EchoMode.Password:
                        action.setIcon(QIcon(":/icons/eye_strike.svg"))
                    else:
                        action.setIcon(QIcon(":/icons/eye_clear.svg"))

                action.triggered.connect(toggle_visibility)

        self.string_options[name].insert(value)
        self.form_layout.addRow(label, self.string_options[name])
        self.rows[name] = (label, self.string_options[name])
        if callback is not None:
            self.string_options[name].textChanged.connect(callback)

    def line_edit_setter(self, line: QLineEdit, name: str | None) -> None:
        """Set the text of a QLineEdit.

        If name is None, nothing happens.

        Args:
            line: The QLineEdit
            name: The test to set, or None.
        """
        if name:
            line.setText(name)

    def add_file_option(
        self,
        name: str,
        description: str,
        value: str | None = "",
        callback: Callable[..., None] | None = None,
    ) -> None:
        """Add an input field for a file option.

        Also add a button to open a "File open"-dialog and add a listener to update the
        corresponding attribute when this value is changed.

        Args:
            name: Name of the attribute
            description: Text of the label
            value: initial Value
            callback: Addional callback

        """
        if value is None:
            value = ""

        label = QLabel(description, self)
        file_layout = QHBoxLayout()
        file_name_widget = QLineEdit(value, self)
        file_button = QPushButton(QIcon.fromTheme("document-open"), "", self)

        file_button.clicked.connect(
            lambda: self.line_edit_setter(
                file_name_widget,
                QFileDialog.getOpenFileName(
                    self, "Select File", dir=os.path.dirname(file_name_widget.text())
                )[0],
            )
        )

        if callback is not None:
            file_name_widget.textChanged.connect(callback)

        file_layout.addWidget(file_name_widget)
        file_layout.addWidget(file_button)

        self.string_options[name] = file_name_widget
        self.string_options[name].textChanged.connect(partial(self.set_string_config_field, name))
        self.rows[name] = (label, file_name_widget)
        self.form_layout.addRow(label, file_layout)

    def add_folder_option(
        self,
        name: str,
        description: str,
        value: str | None = "",
        callback: Callable[..., None] | None = None,
    ) -> None:
        """Add an input field for a folder option.

        Also add a button to open a "Folder open"-dialog and add a listener to update the
        corresponding attribute when this value is changed.

        Args:
            name: Name of the attribute
            description: Text of the label
            value: initial Value
            callback: Addional callback

        """
        if value is None:
            value = ""

        label = QLabel(description, self)
        folder_layout = QHBoxLayout()
        folder_name_widget = QLineEdit(value, self)
        folder_button = QPushButton(QIcon.fromTheme("folder-open"), "", self)

        folder_button.clicked.connect(
            lambda: self.line_edit_setter(
                folder_name_widget,
                QFileDialog.getExistingDirectory(
                    self, "Select Folder", dir=folder_name_widget.text()
                ),
            )
        )

        if callback is not None:
            folder_name_widget.textChanged.connect(callback)

        folder_layout.addWidget(folder_name_widget)
        folder_layout.addWidget(folder_button)

        self.string_options[name] = folder_name_widget
        self.string_options[name].textChanged.connect(partial(self.set_string_config_field, name))
        self.rows[name] = (label, folder_name_widget)
        self.form_layout.addRow(label, folder_layout)

    def add_int_option(
        self,
        name: str,
        description: str,
        value: int | None = 0,
        callback: Callable[..., None] | None = None,
    ) -> None:
        """Add an number spinner for a integer option.

        Also add a listener to update the corresponding attribute when this value is changed.

        Args:
            name: Name of the attribute
            description: Text of the label
            value: initial Value
            callback: Addional callback

        """
        if value is None:
            value = 0

        label = QLabel(description, self)

        self.int_options[name] = QSpinBox(self)
        self.int_options[name].textChanged.connect(
            lambda value: self.set_config_field(name, int(value))
        )
        self.int_options[name].setMaximum(9999)
        self.int_options[name].setValue(value)
        self.form_layout.addRow(label, self.int_options[name])
        self.rows[name] = (label, self.int_options[name])
        if callback is not None:
            self.int_options[name].textChanged.connect(callback)

    def update_model_list(self, name: str) -> None:
        """Update a list attribute of the config with the values in the corresponding list widget.

        If the config dows not has the attribute, nothing happens.

        Args:
            name: name of the attribute

        """
        if hasattr(self.config, name):
            options = [option.text().strip() for option in self.list_options[name]]
            setattr(self.config, name, options)

    def del_list_element(
        self,
        name: str,
        element: QLineEdit,
        line: QWidget,
        layout: QVBoxLayout,
    ) -> None:
        """Remove an element of a list widget.

        Updates the underlying configuration.

        Args:
            name: name of the attribute
            element: The lineedit-element to remove
            line: The line to remove (includes the remove button)
            layout: the parent layout to remove from

        """
        self.list_options[name].remove(element)

        layout.removeWidget(line)
        line.deleteLater()
        self.update_model_list(name)

    def add_list_element(
        self,
        name: str,
        layout: QVBoxLayout,
        init: str,
        callback: Callable[..., None] | None,
    ) -> None:
        """Add a row in a list widget.

        Args:
            name: Name of the attribute
            layout: The layout to add the rows
            init: initial value of the index
            callback: additional callbacks

        """
        input_and_minus = QWidget()
        input_and_minus_layout = QHBoxLayout(input_and_minus)
        input_and_minus.setLayout(input_and_minus_layout)

        input_and_minus_layout.setContentsMargins(0, 0, 0, 0)

        input_field = QLineEdit(input_and_minus)
        input_field.setText(init)
        input_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        input_and_minus_layout.addWidget(input_field)
        if callback is not None:
            input_field.textChanged.connect(callback)
        input_field.textChanged.connect(lambda _: self.update_model_list(name))

        minus_button = QPushButton(QIcon.fromTheme("list-remove"), "", input_and_minus)
        minus_button.clicked.connect(
            partial(self.del_list_element, name, input_field, input_and_minus, layout)
        )
        minus_button.setFixedWidth(40)
        minus_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        input_and_minus_layout.addWidget(minus_button)

        layout.insertWidget(layout.count() - 1, input_and_minus)

        self.list_options[name].append(input_field)

    def add_list_option(
        self,
        name: str,
        description: str,
        value: list[str],
        callback: Callable[..., None] | None = None,
    ) -> None:
        """Adds a list widget for a list[str] option.

        The widget consists of multiple rows (one for each entry in the value list).
        Each row has a line edit for the value at the index, and a button to remove the value from
        the list. At the end sits a plus button to add another row.

        Everytime something changes in the widget, the underlying configuration is updated.

        Args:
            name: Name of the attribute
            description: Text of the label
            value: initial value
            callback: additional callback

        """
        label = QLabel(description, self)

        container_layout = QVBoxLayout()

        self.form_layout.addRow(label, container_layout)
        self.rows[name] = (label, container_layout)

        self.list_options[name] = []
        for v in value:
            self.add_list_element(name, container_layout, v, callback)
        plus_button = QPushButton(QIcon.fromTheme("list-add"), "", self)
        plus_button.clicked.connect(
            partial(self.add_list_element, name, container_layout, "", callback)
        )
        plus_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        container_layout.addWidget(plus_button)

    def add_choose_option(
        self,
        name: str,
        description: str,
        values: list[Any],
        value: str = "",
        enum: type[Enum] | None = None,
    ) -> None:
        """Add a combobox for an enum option.

        Also add a listener to update the corresponding attribute when this value is changed.

        Args:
            name: Name of the attribute
            description: Text of the label
            values: possible Values
            value: initial Value
            enum: The enum type represented.

        """

        def change_choose_callback(value: str) -> None:
            if enum is None:
                return
            try:
                enum_value = enum(value)
            except ValueError:
                enum_value = enum(int(value))

            self.set_config_field(name, enum_value)

        label = QLabel(description, self)

        self.choose_options[name] = QComboBox(self)
        self.choose_options[name].addItems([str(v) for v in values])
        self.choose_options[name].setCurrentText(str(value))
        self.choose_options[name].currentTextChanged.connect(change_choose_callback)
        self.form_layout.addRow(label, self.choose_options[name])
        self.rows[name] = (label, self.choose_options[name])

    def add_date_time_option(
        self, name: str, description: str, value: str | datetime | None
    ) -> None:
        """Add a DateTimeEdit for datetime option.

        Also includes checkbox to disable, value is then None.
        Also add a listener to update the corresponding attribute when this value is changed.

        If the value is None, it initializes with the current time.

        Args:
            name: Name of the attribute
            description: Text of the label
            value: initial Value

        Raises:
            ValueError: but catches it directly....

        """

        def enabled_slot(date_time_widget: QDateTimeEdit, value: Qt.CheckState) -> None:
            if value == Qt.CheckState.Checked:
                date_time = cast(datetime, date_time_widget.dateTime().toPython())
                self.set_config_field(name, date_time)
            else:
                self.set_config_field(name, None)

        if isinstance(value, datetime):
            value = value.isoformat()

        label = QLabel(description, self)
        date_time_layout = QHBoxLayout()
        date_time_widget = QDateTimeEdit(self)
        date_time_enabled = QCheckBox("Enabled", self)
        date_time_enabled.stateChanged.connect(
            lambda: date_time_widget.setEnabled(date_time_enabled.isChecked())
        )
        date_time_enabled.checkStateChanged.connect(partial(enabled_slot, date_time_widget))
        date_time_widget.dateTimeChanged.connect(
            lambda qt_value: self.set_config_field(name, qt_value.toPython())
        )

        self.date_time_options[name] = (date_time_widget, date_time_enabled)
        date_time_widget.setCalendarPopup(True)
        try:
            if value is None:
                raise ValueError
            date_time_widget.setDateTime(QDateTime.fromString(value, Qt.DateFormat.ISODate))
            date_time_enabled.setChecked(True)
        except (TypeError, ValueError):
            date_time_widget.setDateTime(QDateTime.currentDateTime())
            date_time_widget.setEnabled(False)
            date_time_enabled.setChecked(False)

        date_time_layout.addWidget(date_time_widget)
        date_time_layout.addWidget(date_time_enabled)

        self.form_layout.addRow(label, date_time_layout)
        self.rows[name] = (label, date_time_layout)

    def __init__(self, parent: QWidget | None, config: Config) -> None:
        """Initialize the widget.

        Sets the configuration object, and adds rows for each configration option.

        Args:
            config: The configuration object
            parent: Qt-Parent object

        """
        super().__init__(parent)
        self.form_layout = QFormLayout(self)
        self.setLayout(self.form_layout)
        self.string_options: dict[str, QLineEdit] = {}
        self.int_options: dict[str, QSpinBox] = {}
        self.choose_options: dict[str, QComboBox] = {}
        self.bool_options: dict[str, QCheckBox] = {}
        self.list_options: dict[str, list[QLineEdit]] = {}
        self.date_time_options: dict[str, tuple[QDateTimeEdit, QCheckBox]] = {}
        self.rows: dict[str, tuple[QLabel, QWidget | QLayout]] = {}

        self.config = config
        self.add_rows_from_config(config)

    @property
    def option_names(self) -> set[str]:
        """Names of all registered options.

        Returns:
            All option names.

        """
        return set(
            self.string_options.keys()
            | self.int_options.keys()
            | self.choose_options.keys()
            | self.bool_options.keys()
            | self.list_options.keys()
            | self.date_time_options.keys()
        )

    def load_config(self, config: Config) -> None:
        """Load and apply options to the form.

        Args:
            config: Cofiguration object with values.

        """
        config_dict = asdict(config)
        for name, textbox in self.string_options.items():
            textbox.setText(config_dict[name])

        for name, spinner in self.int_options.items():
            try:
                spinner.setValue(config_dict[name])
            except ValueError:
                spinner.setValue(0)

        for name, optionmenu in self.choose_options.items():
            optionmenu.setCurrentText(str(config_dict[name].value))

        for name, checkbox in self.bool_options.items():
            checkbox.setChecked(config_dict[name])

        for name, textboxes in self.list_options.items():
            for i, textbox in enumerate(textboxes):
                textbox.setText(config_dict[name][i])

        for name, (picker, checkbox) in self.date_time_options.items():
            if config_dict[name] is not None:
                picker.setDateTime(QDateTime.fromString(config_dict[name], Qt.DateFormat.ISODate))
                checkbox.setChecked(True)
            else:
                picker.setDateTime(QDateTime.currentDateTime())
                picker.setEnabled(False)
                checkbox.setChecked(False)
