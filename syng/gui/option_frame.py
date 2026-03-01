"""Windget, that hold options depending on the types of a configuration object."""

from collections.abc import Callable, MutableMapping
from dataclasses import asdict, fields
from datetime import datetime
from enum import Enum
from functools import partial
from types import NoneType, UnionType
from typing import Any, Union, cast, get_args, get_origin, get_type_hints, reveal_type

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from syng.config import Config
from syng.gui.row_widgets import (
    BoolSetting,
    EnumOption,
    FileSetting,
    FolderSetting,
    IntSetting,
    PasswordSetting,
    RowWidget,
    StringSetting,
    StrListOption,
)


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
        if ty is bool and isinstance(value, bool):
            self.add_bool_option(name, description, value)
        elif ty is int and isinstance(value, int):
            self.add_int_option(name, description, value)
        elif ty is str and isinstance(value, str):
            if semantic == "password":
                self.add_string_option(name, description, value=value, is_password=True)
            elif semantic == "folder":
                self.add_folder_option(name, description, value=value)
            elif semantic == "file":
                self.add_file_option(name, description, value=value)
            elif semantic is None:
                self.add_string_option(name, description, value=value)
        elif get_origin(ty) is list and get_args(ty) == (str,):
            self.add_list_option(name, description, value=cast(list[str], value))
        elif ty is datetime:
            self.add_date_time_option(name, description, cast(datetime | None, value))
        elif issubclass(ty, Enum) and isinstance(value, ty):
            self.add_choose_option(name, description, value, ty)

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
        settings_row = BoolSetting(self, value, description)

        self.options[name] = settings_row
        settings_row.valueChanged.connect(partial(self.set_config_field, name))
        self.form_layout.addRow(*settings_row.to_form_tuple())

    def add_string_option(
        self,
        name: str,
        description: str,
        value: str | None = "",
        callback: Callable[[str], None] | None = None,
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

        if not is_password:
            settings_row = StringSetting(self, value, description)
        else:
            settings_row = PasswordSetting(self, value, description)
        settings_row.valueChanged.connect(partial(self.set_config_field, name))
        if callback is not None:
            settings_row.valueChanged.connect(callback)
        self.options[name] = settings_row
        self.form_layout.addRow(*settings_row.to_form_tuple())

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
        settings_row = FileSetting(self, value, description)
        settings_row.valueChanged.connect(partial(self.set_config_field, name))
        if callback is not None:
            settings_row.valueChanged.connect(callback)
        self.options[name] = settings_row
        self.form_layout.addRow(*settings_row.to_form_tuple())

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
        settings_row = FolderSetting(self, value, description)
        settings_row.valueChanged.connect(partial(self.set_config_field, name))
        if callback is not None:
            settings_row.valueChanged.connect(callback)
        self.options[name] = settings_row
        self.form_layout.addRow(*settings_row.to_form_tuple())

    def add_int_option(
        self,
        name: str,
        description: str,
        value: int | None = 0,
        callback: Callable[[int], None] | None = None,
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

        settings_row = IntSetting(self, value, description)

        self.options[name] = settings_row
        settings_row.valueChanged.connect(partial(self.set_config_field, name))
        self.form_layout.addRow(*settings_row.to_form_tuple())

        if callback is not None:
            settings_row.valueChanged.connect(callback)

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
        if value is None:
            value = []
        settings_row = StrListOption(self, value, description)

        self.options[name] = settings_row
        settings_row.valueChanged.connect(partial(self.set_config_field, name))
        self.form_layout.addRow(*settings_row.to_form_tuple())

        if callback is not None:
            settings_row.valueChanged.connect(callback)

    def add_choose_option[T: Enum](
        self,
        name: str,
        description: str,
        value: T,
        enum: type[T],
    ) -> None:
        """Add a combobox for an enum option.

        Also add a listener to update the corresponding attribute when this value is changed.

        Args:
            name: Name of the attribute
            description: Text of the label
            value: initial Value
            enum: The enum type represented.

        """
        settings_row = EnumOption(self, value, description, enum)

        self.options[name] = settings_row
        settings_row.valueChanged.connect(partial(self.set_config_field, name))
        self.form_layout.addRow(*settings_row.to_form_tuple())

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
        self.options: MutableMapping[str, RowWidget[Any]] = {}

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
            | self.options.keys()
        )

    def load_config(self, config: Config) -> None:
        """Load and apply options to the form.

        Args:
            config: Cofiguration object with values.

        """
        config_dict = asdict(config)

        for name, form_row in self.options.items():
            form_row.set_value(config_dict[name])

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
