import os
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from functools import partial
from typing import Any, cast, get_args, get_origin

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
    def add_option[T](
        self, ty: type[T], name: str, description: str, value: T, semantic: str | None
    ) -> None:
        if ty is bool and isinstance(value, bool):
            self.add_bool_option(name, description, value=value)
        elif ty is int and isinstance(value, int):
            self.add_int_option(name, description, value=value)
        elif ty is str and isinstance(value, str):
            if semantic == "password":
                self.add_string_option(name, description, value=value, is_password=True)
            elif semantic == "folder":
                self.add_folder_option(name, description, value=value)
            elif semantic == "file":
                self.add_file_option(name, description, value=value)
            elif semantic is None:
                self.add_string_option(name, description, value=value)
        elif get_origin(ty) is list and get_args(ty) == (str,) and isinstance(value, list):
            self.add_list_option(name, description, value=value)
        elif ty is datetime and (value is None or isinstance(value, str)):
            self.add_date_time_option(name, description, value)
        elif issubclass(ty, Enum) and hasattr(value, "value"):
            values = [a.value for a in ty.__members__.values()]
            self.add_choose_option(name, description, values, value.value, ty)

    def set_config_field(self, name: str, value: Any) -> None:
        if hasattr(self.config, name):
            setattr(self.config, name, value)
            print(self.config)

    def add_bool_option(self, name: str, description: str, value: bool = False) -> None:
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
        if value is None:
            value = ""

        label = QLabel(description, self)

        self.string_options[name] = QLineEdit(self)
        self.string_options[name].textChanged.connect(partial(self.set_config_field, name))
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

    def path_setter(self, line: QLineEdit, name: str | None) -> None:
        if name:
            line.setText(name)

    def add_file_option(
        self,
        name: str,
        description: str,
        value: str | None = "",
        callback: Callable[..., None] | None = None,
    ) -> None:
        if value is None:
            value = ""

        label = QLabel(description, self)
        file_layout = QHBoxLayout()
        file_name_widget = QLineEdit(value, self)
        file_button = QPushButton(QIcon.fromTheme("document-open"), "", self)

        file_button.clicked.connect(
            lambda: self.path_setter(
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
        self.string_options[name].textChanged.connect(partial(self.set_config_field, name))
        self.rows[name] = (label, file_name_widget)
        self.form_layout.addRow(label, file_layout)

    def add_folder_option(
        self,
        name: str,
        description: str,
        value: str | None = "",
        callback: Callable[..., None] | None = None,
    ) -> None:
        if value is None:
            value = ""

        label = QLabel(description, self)
        folder_layout = QHBoxLayout()
        folder_name_widget = QLineEdit(value, self)
        folder_button = QPushButton(QIcon.fromTheme("folder-open"), "", self)

        folder_button.clicked.connect(
            lambda: self.path_setter(
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
        self.string_options[name].textChanged.connect(partial(self.set_config_field, name))
        self.rows[name] = (label, folder_name_widget)
        self.form_layout.addRow(label, folder_layout)

    def add_int_option(
        self,
        name: str,
        description: str,
        value: int | None = 0,
        callback: Callable[..., None] | None = None,
    ) -> None:
        if value is None:
            value = 0

        label = QLabel(description, self)

        self.int_options[name] = QSpinBox(self)
        self.int_options[name].textChanged.connect(partial(self.set_config_field, name))
        self.int_options[name].setMaximum(9999)
        self.int_options[name].setValue(value)
        self.form_layout.addRow(label, self.int_options[name])
        self.rows[name] = (label, self.int_options[name])
        if callback is not None:
            self.int_options[name].textChanged.connect(callback)

    def update_model_list(self, name: str) -> None:
        options = [option.text().strip() for option in self.list_options[name]]
        self.set_config_field(name, options)

    def del_list_element(
        self,
        name: str,
        element: QLineEdit,
        line: QWidget,
        layout: QVBoxLayout,
    ) -> None:
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

    def add_date_time_option(self, name: str, description: str, value: str | None) -> None:
        def enabled_slot(date_time_widget: QDateTimeEdit, value: Qt.CheckState) -> None:
            if value == Qt.CheckState.Checked:
                date_time = date_time_widget.dateTime().toPython()
                self.set_config_field(name, date_time)
            else:
                self.set_config_field(name, None)

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

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
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

    @property
    def option_names(self) -> set[str]:
        return set(
            self.string_options.keys()
            | self.int_options.keys()
            | self.choose_options.keys()
            | self.bool_options.keys()
            | self.list_options.keys()
            | self.date_time_options.keys()
        )

    def get_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {}
        for name, textbox in self.string_options.items():
            config[name] = textbox.text().strip()

        for name, spinner in self.int_options.items():
            config[name] = spinner.value()

        for name, optionmenu in self.choose_options.items():
            config[name] = optionmenu.currentText().strip()

        for name, checkbox in self.bool_options.items():
            config[name] = checkbox.isChecked()

        for name, textboxes in self.list_options.items():
            config[name] = []
            for textbox in textboxes:
                config[name].append(textbox.text().strip())

        for name, (picker, checkbox) in self.date_time_options.items():
            if not checkbox.isChecked():
                config[name] = None
                continue
            try:
                config[name] = cast(datetime, picker.dateTime().toPython()).isoformat()
            except ValueError:
                config[name] = None

        return config

    def load_config(self, config: dict[str, Any]) -> None:
        for name, textbox in self.string_options.items():
            textbox.setText(config[name])

        for name, spinner in self.int_options.items():
            try:
                spinner.setValue(config[name])
            except ValueError:
                spinner.setValue(0)

        for name, optionmenu in self.choose_options.items():
            optionmenu.setCurrentText(str(config[name]))

        for name, checkbox in self.bool_options.items():
            checkbox.setChecked(config[name])

        for name, textboxes in self.list_options.items():
            for i, textbox in enumerate(textboxes):
                textbox.setText(config[name][i])

        for name, (picker, checkbox) in self.date_time_options.items():
            if config[name] is not None:
                picker.setDateTime(QDateTime.fromString(config[name], Qt.DateFormat.ISODate))
                checkbox.setChecked(True)
            else:
                picker.setDateTime(QDateTime.currentDateTime())
                picker.setEnabled(False)
                checkbox.setChecked(False)
