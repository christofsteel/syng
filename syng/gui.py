import asyncio
from io import BytesIO
import sys
import logging
from logging.handlers import QueueListener
from logging.handlers import QueueHandler
import packaging.version

import aiohttp
from queue import Queue
from collections.abc import Callable
from datetime import datetime
import os
from functools import partial
import random
from typing import TYPE_CHECKING, Any, Optional
import secrets
import string
import signal


try:
    if not TYPE_CHECKING:
        from ctypes import windll

        appid = "rocks.syng.Syng.2.3.0"
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
except ImportError:
    pass

os.environ["QT_API"] = "pyqt6"
from qasync import QEventLoop, QApplication
from PyQt6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QTimer,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QCloseEvent, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QTabBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from yaml import dump, load, Loader, Dumper
from qrcode.main import QRCode
import platformdirs

from . import __version__, resources  # noqa
from .client import Client, default_config
from .log import logger
from .entry import Entry

from .sources import available_sources
from .config import (
    BoolOption,
    ChoiceOption,
    FileOption,
    FolderOption,
    IntOption,
    ListStrOption,
    PasswordOption,
    StrOption,
)


class QueueModel(QAbstractListModel):
    def __init__(self, queue: list[Entry]) -> None:
        super().__init__()
        self.queue = queue

    def update(self, queue: list[Entry]) -> None:
        self.queue = queue
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, 0))

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            entry = self.queue[index.row()]
            return f"{entry.title} - {entry.artist} [{entry.album}]\n{entry.performer}"

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.queue)


class QueueView(QListView):
    pass


class OptionFrame(QWidget):
    def add_bool_option(self, name: str, description: str, value: bool = False) -> None:
        label = QLabel(description, self)

        self.bool_options[name] = QCheckBox(self)
        self.bool_options[name].setChecked(value)
        self.form_layout.addRow(label, self.bool_options[name])
        self.rows[name] = (label, self.bool_options[name])

    def add_string_option(
        self,
        name: str,
        description: str,
        value: Optional[str] = "",
        callback: Optional[Callable[..., None]] = None,
        is_password: bool = False,
    ) -> None:
        if value is None:
            value = ""

        label = QLabel(description, self)

        self.string_options[name] = QLineEdit(self)
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

    def path_setter(self, line: QLineEdit, name: Optional[str]) -> None:
        if name:
            line.setText(name)

    def add_file_option(
        self,
        name: str,
        description: str,
        value: Optional[str] = "",
        callback: Optional[Callable[..., None]] = None,
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
                    self, "Select File", directory=os.path.dirname(file_name_widget.text())
                )[0],
            )
        )

        if callback is not None:
            file_name_widget.textChanged.connect(callback)

        file_layout.addWidget(file_name_widget)
        file_layout.addWidget(file_button)

        self.string_options[name] = file_name_widget
        self.rows[name] = (label, file_name_widget)
        self.form_layout.addRow(label, file_layout)

    def add_folder_option(
        self,
        name: str,
        description: str,
        value: Optional[str] = "",
        callback: Optional[Callable[..., None]] = None,
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
                    self, "Select Folder", directory=folder_name_widget.text()
                ),
            )
        )

        if callback is not None:
            folder_name_widget.textChanged.connect(callback)

        folder_layout.addWidget(folder_name_widget)
        folder_layout.addWidget(folder_button)

        self.string_options[name] = folder_name_widget
        self.rows[name] = (label, folder_name_widget)
        self.form_layout.addRow(label, folder_layout)

    def add_int_option(
        self,
        name: str,
        description: str,
        value: Optional[int] = 0,
        callback: Optional[Callable[..., None]] = None,
    ) -> None:
        if value is None:
            value = 0

        label = QLabel(description, self)

        self.int_options[name] = QSpinBox(self)
        self.int_options[name].setMaximum(9999)
        self.int_options[name].setValue(value)
        self.form_layout.addRow(label, self.int_options[name])
        self.rows[name] = (label, self.int_options[name])
        if callback is not None:
            self.int_options[name].textChanged.connect(callback)

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

    def add_list_element(
        self,
        name: str,
        layout: QVBoxLayout,
        init: str,
        callback: Optional[Callable[..., None]],
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
        callback: Optional[Callable[..., None]] = None,
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
        self, name: str, description: str, values: list[str], value: str = ""
    ) -> None:
        label = QLabel(description, self)

        self.choose_options[name] = QComboBox(self)
        self.choose_options[name].addItems(values)
        self.choose_options[name].setCurrentText(str(value))
        self.form_layout.addRow(label, self.choose_options[name])
        self.rows[name] = (label, self.choose_options[name])

    def add_date_time_option(self, name: str, description: str, value: str) -> None:
        label = QLabel(description, self)
        date_time_layout = QHBoxLayout()
        date_time_widget = QDateTimeEdit(self)
        date_time_enabled = QCheckBox("Enabled", self)
        date_time_enabled.stateChanged.connect(
            lambda: date_time_widget.setEnabled(date_time_enabled.isChecked())
        )

        self.date_time_options[name] = (date_time_widget, date_time_enabled)
        date_time_widget.setCalendarPopup(True)
        try:
            date_time_widget.setDateTime(datetime.fromisoformat(value))
            date_time_enabled.setChecked(True)
        except (TypeError, ValueError):
            date_time_widget.setDateTime(datetime.now())
            date_time_widget.setEnabled(False)
            date_time_enabled.setChecked(False)

        date_time_layout.addWidget(date_time_widget)
        date_time_layout.addWidget(date_time_enabled)

        self.form_layout.addRow(label, date_time_layout)
        self.rows[name] = (label, date_time_layout)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
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
                config[name] = picker.dateTime().toPyDateTime().isoformat()
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
                picker.setDateTime(datetime.fromisoformat(config[name]))
                checkbox.setChecked(True)
            else:
                picker.setDateTime(datetime.now())
                picker.setEnabled(False)
                checkbox.setChecked(False)


class SourceTab(OptionFrame):
    def __init__(self, parent: QWidget, source_name: str, config: dict[str, Any]) -> None:
        super().__init__(parent)
        source = available_sources[source_name]
        self.vars: dict[str, str | bool | list[str]] = {}
        for name, option in source.config_schema.items():
            value = config[name] if name in config else option.default
            match option.type:
                case BoolOption():
                    self.add_bool_option(name, option.description, value=value)
                case ListStrOption():
                    self.add_list_option(name, option.description, value=value)
                case StrOption():
                    self.add_string_option(name, option.description, value=value)
                case IntOption():
                    self.add_int_option(name, option.description, value=value)
                case PasswordOption():
                    self.add_string_option(name, option.description, value=value, is_password=True)
                case FolderOption():
                    self.add_folder_option(name, option.description, value=value)
                case FileOption():
                    self.add_file_option(name, option.description, value=value)
                case ChoiceOption(choices):
                    self.add_choose_option(name, option.description, choices, value)


class UIConfig(OptionFrame):
    def __init__(self, parent: QWidget, config: dict[str, Any]):
        super().__init__(parent)

        self.add_int_option(
            "preview_duration", "Preview duration in seconds", int(config["preview_duration"])
        )
        self.add_int_option(
            "next_up_time",
            "Time remaining before Next Up Box is shown",
            int(config["next_up_time"]),
        )
        self.add_int_option("qr_box_size", "QR Code Box Size", int(config["qr_box_size"]))
        self.add_choose_option(
            "qr_position",
            "QR Code Position",
            ["top-left", "top-right", "bottom-left", "bottom-right"],
            config["qr_position"],
        )


class GeneralConfig(OptionFrame):
    def __init__(
        self,
        parent: QWidget,
        config: dict[str, Any],
        callback: Callable[..., None],
    ) -> None:
        super().__init__(parent)

        self.add_string_option("server", "Server", config["server"], callback)
        self.add_string_option("room", "Room", config["room"], callback)
        self.add_string_option("secret", "Admin Password", config["secret"], is_password=True)
        self.add_choose_option(
            "waiting_room_policy",
            "Waiting room policy",
            ["forced", "optional", "none"],
            str(config["waiting_room_policy"]).lower(),
        )
        self.add_bool_option(
            "allow_collab_mode",
            "Allow performers to add collaboration tags",
            config["allow_collab_mode"],
        )
        self.add_date_time_option("last_song", "Last song ends at", config["last_song"])
        self.add_string_option(
            "key", "Key for server (if necessary)", config["key"], is_password=True
        )
        self.add_int_option(
            "buffer_in_advance",
            "Buffer the next songs in advance",
            int(config["buffer_in_advance"]),
        )
        self.add_choose_option(
            "log_level",
            "Log Level",
            ["debug", "info", "warning", "error", "critical"],
            config["log_level"],
        )

        self.simple_options = ["server", "room", "secret"]

        if not config["show_advanced"]:
            for option in self.option_names.difference(self.simple_options):
                self.rows[option][0].setVisible(False)
                widget_or_layout = self.rows[option][1]
                if isinstance(widget_or_layout, QWidget):
                    widget_or_layout.setVisible(False)
                else:
                    for i in range(widget_or_layout.count()):
                        item = widget_or_layout.itemAt(i)
                        widget = item.widget() if item else None
                        if widget:
                            widget.setVisible(False)

    def get_config(self) -> dict[str, Any]:
        config = super().get_config()
        return config


class SyngGui(QMainWindow):
    def closeEvent(self, a0: Optional[QCloseEvent]) -> None:
        if self.client is not None:
            if self.client.player is not None and self.client.player.mpv is not None:
                self.client.player.mpv.terminate()
            self.client.quit_callback()

        self.log_label_handler.cleanup()

        self.destroy()
        sys.exit(0)

    def add_buttons(self, show_advanced: bool) -> None:
        self.buttons_layout = QHBoxLayout()
        self.central_layout.addLayout(self.buttons_layout)

        self.resetbutton = QPushButton("Set Config to Default")
        self.exportbutton = QPushButton("Export Config")
        self.importbutton = QPushButton("Import Config")
        self.buttons_layout.addWidget(self.resetbutton)
        self.buttons_layout.addWidget(self.exportbutton)
        self.buttons_layout.addWidget(self.importbutton)
        self.resetbutton.clicked.connect(self.clear_config)
        self.exportbutton.clicked.connect(self.export_config)
        self.importbutton.clicked.connect(self.import_config)
        if not show_advanced:
            self.resetbutton.hide()
            self.exportbutton.hide()
            self.importbutton.hide()

        self.show_advanced_toggle = QCheckBox("Show Advanced Options")
        self.show_advanced_toggle.setChecked(show_advanced)
        self.show_advanced_toggle.stateChanged.connect(self.toggle_advanced)
        self.buttons_layout.addWidget(self.show_advanced_toggle)

        spacer_item = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.buttons_layout.addItem(spacer_item)

        if os.getenv("SYNG_DEBUG", "0") == "1":
            self.print_background_tasks_button = QPushButton("Print Background Tasks")
            self.print_background_tasks_button.clicked.connect(
                lambda: print(asyncio.all_tasks(self.loop))
            )
            self.buttons_layout.addWidget(self.print_background_tasks_button)

        self.startbutton = QPushButton("Connect")

        self.startbutton.clicked.connect(self.start_syng_client)
        self.buttons_layout.addWidget(self.startbutton)

    def export_queue(self) -> None:
        if self.client is not None:
            filename = QFileDialog.getSaveFileName(self, "Export Queue", "", "JSON Files (*.json)")[
                0
            ]
            if filename:
                self.client.export_queue(filename)
        else:
            QMessageBox.warning(
                self,
                "No Client Running",
                "You need to start the client before you can export the queue.",
            )

    def import_queue(self) -> None:
        if self.client is not None:
            filename = QFileDialog.getOpenFileName(self, "Import Queue", "", "JSON Files (*.json)")[
                0
            ]
            if filename:
                asyncio.create_task(self.client.import_queue(filename))
        else:
            QMessageBox.warning(
                self,
                "No Client Running",
                "You need to start the client before you can import a queue.",
            )

    def clear_cache(self) -> None:
        """
        Clear the cache directory of the client.
        """

        cache_dir = platformdirs.user_cache_dir("syng")
        if os.path.exists(cache_dir):
            answer = QMessageBox.question(
                self,
                "Clear Cache",
                f"Are you sure you want to clear the cache directory at {cache_dir}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                for root, dirs, files in os.walk(cache_dir, topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
                QMessageBox.information(self, "Cache Cleared", "The cache has been cleared.")

    def remove_room(self) -> None:
        if self.client is not None:
            answer = QMessageBox.question(
                self,
                "Remove Room",
                "Are you sure you want to remove the room on the server? This will disconnect all clients and clear the queue.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                asyncio.create_task(self.client.remove_room())
        else:
            QMessageBox.warning(
                self,
                "No Client Running",
                "You need to start the client before you can remove a room.",
            )

    def toggle_advanced(self, state: bool) -> None:
        self.resetbutton.setVisible(state)
        self.exportbutton.setVisible(state)
        self.importbutton.setVisible(state)

        for option in self.general_config.option_names.difference(
            self.general_config.simple_options
        ):
            self.general_config.rows[option][0].setVisible(state)
            widget_or_layout = self.general_config.rows[option][1]
            if isinstance(widget_or_layout, QWidget):
                widget_or_layout.setVisible(state)
            else:
                for i in range(widget_or_layout.count()):
                    item = widget_or_layout.itemAt(i)
                    widget = item.widget() if item else None
                    if widget:
                        widget.setVisible(state)

        tabbar: Optional[QTabBar] = self.tabview.tabBar()
        if not state:
            if tabbar is not None:
                tabbar.hide()
            self.tabview.setCurrentIndex(0)
            self.general_config.form_layout.addRow(self.qr_widget)
        else:
            if tabbar is not None:
                tabbar.show()
            self.frm.addWidget(self.qr_widget)

    def init_frame(self) -> None:
        self.frm = QHBoxLayout()
        self.central_layout.addLayout(self.frm)

    def init_tabs(self, show_advanced: bool) -> None:
        self.tabview: QTabWidget = QTabWidget(parent=self.central_widget)
        self.tabview.setAcceptDrops(False)
        self.tabview.setTabPosition(QTabWidget.TabPosition.West)
        self.tabview.setTabShape(QTabWidget.TabShape.Rounded)
        self.tabview.setDocumentMode(False)
        self.tabview.setTabsClosable(False)
        self.tabview.setObjectName("tabWidget")

        self.tabview.setTabText(0, "General")
        for i, source in enumerate(available_sources):
            self.tabview.setTabText(i + 1, source)

        if not show_advanced:
            tabbar = self.tabview.tabBar()
            if tabbar is not None:
                tabbar.hide()

        self.frm.addWidget(self.tabview)

    def add_qr(self, show_advanced: bool) -> None:
        self.qr_widget: QWidget = QWidget(parent=self.central_widget)
        self.qr_layout = QVBoxLayout(self.qr_widget)
        self.qr_widget.setLayout(self.qr_layout)

        self.qr_label = QLabel(self.qr_widget)
        self.linklabel = QLabel(self.qr_widget)

        self.qr_layout.addWidget(self.qr_label)
        self.qr_layout.addWidget(self.linklabel)
        self.qr_layout.setAlignment(self.linklabel, Qt.AlignmentFlag.AlignCenter)
        self.qr_layout.setAlignment(self.qr_label, Qt.AlignmentFlag.AlignCenter)

        self.linklabel.setOpenExternalLinks(True)
        if not show_advanced:
            self.general_config.form_layout.addRow(self.qr_widget)
        else:
            self.frm.addWidget(self.qr_widget)

    def add_general_config(self, config: dict[str, Any]) -> None:
        self.general_config = GeneralConfig(self, config, self.update_qr)
        self.tabview.addTab(self.general_config, "General")

    def add_ui_config(self, config: dict[str, Any]) -> None:
        self.ui_config = UIConfig(self, config)
        self.tabview.addTab(self.ui_config, "UI")

    def add_source_config(self, source_name: str, source_config: dict[str, Any]) -> None:
        self.tabs[source_name] = SourceTab(self, source_name, source_config)
        self.tabview.addTab(self.tabs[source_name], source_name)

    def add_log_tab(self) -> None:
        self.log_tab = QWidget(parent=self.central_widget)
        self.log_layout = QVBoxLayout(self.log_tab)
        self.log_tab.setLayout(self.log_layout)

        self.log_text = QTextEdit(self.log_tab)
        self.log_text.setReadOnly(True)
        self.log_layout.addWidget(self.log_text)

        self.tabview.addTab(self.log_tab, "Logs")

    def add_queue_tab(self) -> None:
        self.queue_tab = QWidget(parent=self.central_widget)
        self.queue_layout = QVBoxLayout(self.queue_tab)
        self.queue_tab.setLayout(self.queue_layout)

        self.queue_list_view: QueueView = QueueView(self.queue_tab)
        self.queue_layout.addWidget(self.queue_list_view)

        self.tabview.addTab(self.queue_tab, "Queue")

    def add_admin_tab(self) -> None:
        self.admin_tab = QWidget(parent=self.central_widget)
        self.admin_layout = QVBoxLayout(self.admin_tab)
        self.admin_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.admin_tab.setLayout(self.admin_layout)

        self.remove_room_button = QPushButton("Remove Room", self.admin_tab)
        self.remove_room_button.clicked.connect(self.remove_room)
        self.admin_layout.addWidget(self.remove_room_button)
        self.remove_room_button.setDisabled(True)

        self.export_queue_button = QPushButton("Export Queue", self.admin_tab)
        self.export_queue_button.clicked.connect(self.export_queue)
        self.admin_layout.addWidget(self.export_queue_button)
        self.export_queue_button.setDisabled(True)

        self.import_queue_button = QPushButton("Import Queue", self.admin_tab)
        self.import_queue_button.clicked.connect(self.import_queue)
        self.admin_layout.addWidget(self.import_queue_button)
        self.import_queue_button.setDisabled(True)

        self.update_config_button = QPushButton("Update Config")
        self.update_config_button.clicked.connect(self.update_config)
        self.admin_layout.addWidget(self.update_config_button)
        self.update_config_button.setDisabled(True)

        self.clear_cache_button = QPushButton("Clear Cache", self.admin_tab)
        self.clear_cache_button.clicked.connect(self.clear_cache)
        self.admin_layout.addWidget(self.clear_cache_button)

        self.version_label = QLabel(
            "",
            self.admin_tab,
        )
        self.admin_layout.addWidget(self.version_label)

        self.tabview.addTab(self.admin_tab, "Admin")

    def update_version_label(
        self,
        running_version: Optional[packaging.version.Version],
        current_version: Optional[packaging.version.Version],
    ) -> None:
        label_string = f"<i>Running version: {running_version}</i><br />Current version on pypi: {current_version}"
        if current_version is not None and running_version is not None:
            if current_version > running_version:
                label_string += '<br /><span style="color:red;">A new version is available! Please update Syng.Rocks!</span>'
            else:
                label_string += '<br /><span style="color:green;">You are running the latest version.</span><br />Visit <a href="https://site.syng.rocks/">syng.rocks</a> for more information.'
        self.version_label.setText(label_string)

    async def get_pypi_version(self) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://pypi.org/pypi/syng/json") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    versions = filter(
                        lambda v: not v.is_prerelease,
                        map(packaging.version.parse, data["releases"].keys()),
                    )
                    self.update_version_label(
                        running_version=packaging.version.parse(__version__),
                        current_version=max(versions),
                    )
        return None

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Syng.Rocks!")

        if os.name != "nt":
            self.setWindowIcon(QIcon(":/icons/syng.ico"))

        self.loop = asyncio.get_event_loop()

        self.pypi_version: Optional[str] = None
        asyncio.run_coroutine_threadsafe(self.get_pypi_version(), self.loop)

        self.client: Optional[Client] = None
        self.syng_client_logging_listener: Optional[QueueListener] = None

        self.configfile = os.path.join(platformdirs.user_config_dir("syng"), "config.yaml")

        self.central_widget = QWidget(parent=self)
        self.central_layout = QVBoxLayout(self.central_widget)

        config = self.load_config(self.configfile)

        self.init_frame()
        self.init_tabs(config["config"]["show_advanced"])
        self.add_buttons(config["config"]["show_advanced"])
        self.add_general_config(config["config"])
        self.add_ui_config(config["config"])
        self.add_qr(config["config"]["show_advanced"])
        self.tabs: dict[str, SourceTab] = {}

        for source_name in available_sources:
            self.add_source_config(source_name, config["sources"][source_name])

        # self.add_queue_tab()
        self.add_admin_tab()
        self.add_log_tab()

        self.update_qr()

        self.logqueue: Queue[logging.LogRecord] = Queue()
        logger.addHandler(QueueHandler(self.logqueue))
        self.log_label_handler = LoggingLabelHandler(self)
        self.log_label_handler.log_signal_emiter.log_signal.connect(self.print_log)

        self.syng_client_logging_listener = QueueListener(self.logqueue, self.log_label_handler)
        self.syng_client_logging_listener.start()

        self.setCentralWidget(self.central_widget)

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_if_client_is_running)

    def complete_config(self, config: dict[str, Any]) -> dict[str, Any]:
        output: dict[str, dict[str, Any]] = {"sources": {}, "config": default_config()}

        try:
            output["config"] |= config["config"]
        except (KeyError, TypeError):
            print("Could not load config")

        if not output["config"]["secret"]:
            output["config"]["secret"] = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
            )

        if output["config"]["room"] == "":
            output["config"]["room"] = "".join(
                [random.choice(string.ascii_letters) for _ in range(6)]
            ).upper()

        for source_name, source in available_sources.items():
            source_config = {}
            for name, option in source.config_schema.items():
                source_config[name] = option.default

            output["sources"][source_name] = source_config

            try:
                output["sources"][source_name] |= config["sources"][source_name]
            except (KeyError, TypeError):
                pass

        return output

    def clear_config(self) -> None:
        answer = QMessageBox.question(
            self,
            "Set to Config to Default",
            "Are you sure you want to clear the config?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.update_config(self.complete_config({"config": {}, "sources": {}}))

    def load_config(self, filename: str) -> dict[str, Any]:
        try:
            with open(filename, encoding="utf8") as cfile:
                loaded_config = load(cfile, Loader=Loader)
        except FileNotFoundError:
            print("No config found, using default values")
            loaded_config = {}

        return self.complete_config(loaded_config)

    def update_config(self, config: dict[str, Any]) -> None:
        self.general_config.load_config(config["config"])
        for source_name, source_config in config["sources"].items():
            self.tabs[source_name].load_config(source_config)

        self.update_qr()

    def save_config(self) -> None:
        os.makedirs(os.path.dirname(self.configfile), exist_ok=True)

        with open(self.configfile, "w", encoding="utf-8") as f:
            dump(self.gather_config(), f, Dumper=Dumper)

    def gather_config(self) -> dict[str, Any]:
        sources = {}
        for source, tab in self.tabs.items():
            sources[source] = tab.get_config()

        general_config = self.general_config.get_config() | {
            "show_advanced": self.show_advanced_toggle.isChecked()
        }

        return {"sources": sources, "config": general_config}

    def import_config(self) -> None:
        filename = QFileDialog.getOpenFileName(self, "Open File", "", "YAML Files (*.yaml)")[0]

        if filename:
            config = self.load_config(filename)
            self.update_config(config)

    def export_config(self) -> None:
        filename = QFileDialog.getSaveFileName(self, "Save File", "", "YAML Files (*.yaml)")[0]
        if filename:
            config = self.gather_config()

            with open(filename, "w", encoding="utf-8") as f:
                dump(config, f, Dumper=Dumper)

    def check_if_client_is_running(self) -> None:
        if self.client is None:
            self.timer.stop()
            return

        if not self.client.connection_state.is_connected():
            self.client = None
            self.set_client_button_start()
        else:
            self.set_client_button_stop()

    def set_client_button_stop(self) -> None:
        self.general_config.string_options["server"].setEnabled(False)
        self.general_config.string_options["room"].setEnabled(False)
        self.update_config_button.setDisabled(False)
        self.remove_room_button.setDisabled(False)
        self.export_queue_button.setDisabled(False)
        self.import_queue_button.setDisabled(False)

        self.startbutton.setText("Disconnect")

    def set_client_button_start(self) -> None:
        self.general_config.string_options["server"].setEnabled(True)
        self.general_config.string_options["room"].setEnabled(True)
        self.update_config_button.setDisabled(True)
        self.remove_room_button.setDisabled(True)
        self.export_queue_button.setDisabled(True)
        self.import_queue_button.setDisabled(True)

        self.startbutton.setText("Connect")

    def start_syng_client(self) -> None:
        if self.client is None or not self.client.connection_state.is_connected():
            logger.debug("Starting client")
            self.save_config()
            config = self.gather_config()
            self.client = Client(config)
            asyncio.run_coroutine_threadsafe(self.client.start_client(config), self.loop)
            # model = QueueModel(self.client.state.queue)
            # self.queue_list_view.setModel(model)
            # self.client.add_queue_callback(model.update)
            self.timer.start(500)
            self.set_client_button_stop()
        else:
            logger.debug("Stopping client")
            self.client.quit_callback()
            self.set_client_button_start()

    @pyqtSlot(str, int)
    def print_log(self, log: str, level: int) -> None:
        if level == logging.CRITICAL:
            log_msg_box = QMessageBox(self)
            log_msg_box.setIcon(QMessageBox.Icon.Critical)
            log_msg_box.setWindowTitle("Critical Error")
            log_msg_box.setText(log)
            log_msg_box.exec()
        self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {log}")

    def change_qr(self, data: str) -> None:
        qr = QRCode(box_size=10, border=2)
        qr.add_data(data)
        qr.make()
        image = qr.make_image().convert("RGB")
        buf = BytesIO()
        image.save(buf, "PNG")
        qr_pixmap = QPixmap()
        qr_pixmap.loadFromData(buf.getvalue(), "PNG")
        self.qr_label.setPixmap(qr_pixmap)

    def update_qr(self) -> None:
        config = self.general_config.get_config()
        syng_server = config["server"]
        syng_server += "" if syng_server.endswith("/") else "/"
        room = config["room"]
        self.linklabel.setText(
            f'<center><a href="{syng_server + room}">{syng_server + room}</a><center>'
        )
        self.linklabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.change_qr(syng_server + room)


class LoggingLabelHandler(logging.Handler):
    class LogSignalEmiter(QObject):
        log_signal = pyqtSignal(str, int)

        def __init__(self, parent: Optional[QObject] = None):
            super().__init__(parent)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__()
        self.log_signal_emiter = self.LogSignalEmiter(parent)
        self._cleanup = False

    def emit(self, record: logging.LogRecord) -> None:
        if not self._cleanup:  # This could race condition, but it's not a big
            # deal since it only causes a race condition,
            # when the program ends
            self.log_signal_emiter.log_signal.emit(self.format(record), record.levelno)

    def cleanup(self) -> None:
        self._cleanup = True


def run_gui() -> None:
    os.makedirs(platformdirs.user_cache_dir("syng"), exist_ok=True)
    base_dir = os.path.dirname(__file__)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = getattr(sys, "_MEIPASS")

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication([])
    event_loop = QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    if os.name == "nt":
        app.setWindowIcon(QIcon(os.path.join(base_dir, "syng.ico")))
    else:
        app.setWindowIcon(QIcon(":/icons/syng.ico"))
    app.setApplicationName("Syng.Rocks!")
    app.setDesktopFileName("rocks.syng.Syng")
    window = SyngGui()
    window.show()
    with event_loop:
        event_loop.run_forever()


if __name__ == "__main__":
    run_gui()
