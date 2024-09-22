from argparse import Namespace
from io import BytesIO
from multiprocessing import Process
from collections.abc import Callable
from datetime import datetime
import os
import builtins
from functools import partial
import random
from typing import TYPE_CHECKING, Any, Optional
import webbrowser
import multiprocessing
import secrets
import string
import subprocess
import signal

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QCloseEvent, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from yaml import dump, load, Loader, Dumper
from qrcode.main import QRCode
import platformdirs

from .client import create_async_and_start_client, default_config

from .sources import available_sources

try:
    from .server import run_server

    SERVER_AVAILABLE = True
except ImportError:
    if TYPE_CHECKING:
        from .server import run_server

    SERVER_AVAILABLE = False


# TODO: ScrollableFrame
class OptionFrame(QWidget):
    def add_bool_option(self, name: str, description: str, value: bool = False) -> None:
        label = QLabel(description, self)

        self.bool_options[name] = QCheckBox(self)
        self.bool_options[name].setChecked(value)
        self.form_layout.addRow(label, self.bool_options[name])
        self.number_of_options += 1

    def add_string_option(
        self,
        name: str,
        description: str,
        value: Optional[str] = "",
        callback: Optional[Callable[..., None]] = None,
    ) -> None:
        if value is None:
            value = ""

        label = QLabel(description, self)

        self.string_options[name] = QLineEdit(self)
        self.string_options[name].insert(value)
        self.form_layout.addRow(label, self.string_options[name])
        if callback is not None:
            self.string_options[name].textChanged.connect(callback)
        self.number_of_options += 1

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

        minus_button = QPushButton("-", input_and_minus)
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

        self.list_options[name] = []
        for v in value:
            self.add_list_element(name, container_layout, v, callback)
        plus_button = QPushButton("+", self)
        plus_button.clicked.connect(
            partial(self.add_list_element, name, container_layout, "", callback)
        )
        plus_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        container_layout.addWidget(plus_button)

        self.number_of_options += 1

    def add_choose_option(
        self, name: str, description: str, values: list[str], value: str = ""
    ) -> None:
        label = QLabel(description, self)

        self.choose_options[name] = QComboBox(self)
        self.choose_options[name].addItems(values)
        self.choose_options[name].setCurrentText(value)
        self.form_layout.addRow(label, self.choose_options[name])
        self.number_of_options += 1

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

        self.number_of_options += 1

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.form_layout = QFormLayout(self)
        self.setLayout(self.form_layout)
        self.number_of_options: int = 0
        self.string_options: dict[str, QLineEdit] = {}
        self.choose_options: dict[str, QComboBox] = {}
        self.bool_options: dict[str, QCheckBox] = {}
        self.list_options: dict[str, list[QLineEdit]] = {}
        self.date_time_options: dict[str, tuple[QDateTimeEdit, QCheckBox]] = {}

    def get_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {}
        for name, textbox in self.string_options.items():
            config[name] = textbox.text().strip()

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


class SourceTab(OptionFrame):
    def __init__(self, parent: QWidget, source_name: str, config: dict[str, Any]) -> None:
        super().__init__(parent)
        source = available_sources[source_name]
        self.vars: dict[str, str | bool | list[str]] = {}
        for name, (typ, desc, default) in source.config_schema.items():
            value = config[name] if name in config else default
            match typ:
                case builtins.bool:
                    self.add_bool_option(name, desc, value=value)
                case builtins.list:
                    self.add_list_option(name, desc, value=value)
                case builtins.str:
                    self.add_string_option(name, desc, value=value)


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
        self.add_string_option("secret", "Admin Password", config["secret"])
        self.add_choose_option(
            "waiting_room_policy",
            "Waiting room policy",
            ["forced", "optional", "none"],
            str(config["waiting_room_policy"]).lower(),
        )
        self.add_date_time_option("last_song", "Last song ends at", config["last_song"])
        self.add_string_option(
            "preview_duration", "Preview duration in seconds", str(config["preview_duration"])
        )
        self.add_string_option("key", "Key for server (if necessary)", config["key"])

    def get_config(self) -> dict[str, Any]:
        config = super().get_config()
        try:
            config["preview_duration"] = int(config["preview_duration"])
        except ValueError:
            config["preview_duration"] = 0

        return config


class SyngGui(QMainWindow):
    def closeEvent(self, a0: Optional[QCloseEvent]) -> None:
        if self.syng_server is not None:
            self.syng_server.kill()
            self.syng_server.join()

        if self.syng_client is not None:
            self.syng_client.terminate()
            self.syng_client.wait(1.0)
            self.syng_client.kill()

        self.destroy()

    def add_buttons(self) -> None:
        self.buttons_layout = QHBoxLayout()
        self.central_layout.addLayout(self.buttons_layout)

        self.startsyng_serverbutton = QPushButton("Start Local Server")
        self.startsyng_serverbutton.clicked.connect(self.start_syng_server)
        self.buttons_layout.addWidget(self.startsyng_serverbutton)

        spacer_item = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.notification_label = QLabel("", self)
        spacer_item2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.buttons_layout.addItem(spacer_item)
        self.buttons_layout.addWidget(self.notification_label)
        self.buttons_layout.addItem(spacer_item2)

        self.savebutton = QPushButton("Save")
        self.savebutton.clicked.connect(self.save_config)
        self.buttons_layout.addWidget(self.savebutton)

        self.startbutton = QPushButton("Save and Start")

        self.startbutton.clicked.connect(self.start_syng_client)
        self.buttons_layout.addWidget(self.startbutton)

    def init_frame(self) -> None:
        self.frm = QHBoxLayout()
        self.central_layout.addLayout(self.frm)

    def init_tabs(self) -> None:
        self.tabview = QTabWidget(parent=self.central_widget)
        self.tabview.setAcceptDrops(False)
        self.tabview.setTabPosition(QTabWidget.TabPosition.West)
        self.tabview.setTabShape(QTabWidget.TabShape.Rounded)
        self.tabview.setDocumentMode(False)
        self.tabview.setTabsClosable(False)
        self.tabview.setObjectName("tabWidget")

        self.tabview.setTabText(0, "General")
        for i, source in enumerate(available_sources):
            self.tabview.setTabText(i + 1, source)

        self.frm.addWidget(self.tabview)

    def add_qr(self) -> None:
        self.qr_widget = QWidget(parent=self.central_widget)
        self.qr_layout = QVBoxLayout(self.qr_widget)
        self.qr_widget.setLayout(self.qr_layout)

        self.qr_label = QLabel(self.qr_widget)
        self.linklabel = QLabel(self.qr_widget)

        self.qr_layout.addWidget(self.qr_label)
        self.qr_layout.addWidget(self.linklabel)

        self.linklabel.setOpenExternalLinks(True)

        self.frm.addWidget(self.qr_widget)

    def add_general_config(self, config: dict[str, Any]) -> None:
        self.general_config = GeneralConfig(self, config, self.update_qr)
        self.tabview.addTab(self.general_config, "General")

    def add_source_config(self, source_name: str, source_config: dict[str, Any]) -> None:
        self.tabs[source_name] = SourceTab(self, source_name, source_config)
        self.tabview.addTab(self.tabs[source_name], source_name)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Syng")

        rel_path = os.path.dirname(__file__)
        qt_img = QPixmap(os.path.join(rel_path, "static/syng.png"))
        self.qt_icon = QIcon(qt_img)
        self.setWindowIcon(self.qt_icon)

        self.syng_server: Optional[Process] = None
        self.syng_client: Optional[subprocess.Popen] = None

        self.configfile = os.path.join(platformdirs.user_config_dir("syng"), "config.yaml")

        try:
            with open(self.configfile, encoding="utf8") as cfile:
                loaded_config = load(cfile, Loader=Loader)
        except FileNotFoundError:
            print("No config found, using default values")
            loaded_config = {}
        config: dict[str, dict[str, Any]] = {"sources": {}, "config": default_config()}

        try:
            config["config"] |= loaded_config["config"]
        except (KeyError, TypeError):
            print("Could not load config")

        if not config["config"]["secret"]:
            config["config"]["secret"] = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
            )

        if config["config"]["room"] == "":
            config["config"]["room"] = "".join(
                [random.choice(string.ascii_letters) for _ in range(6)]
            ).upper()

        self.central_widget = QWidget(parent=self)
        self.central_layout = QVBoxLayout(self.central_widget)

        self.init_frame()
        self.init_tabs()
        self.add_buttons()
        self.add_qr()
        self.add_general_config(config["config"])
        self.tabs: dict[str, SourceTab] = {}

        for source_name in available_sources:
            try:
                source_config = loaded_config["sources"][source_name]
            except (KeyError, TypeError):
                source_config = {}

            self.add_source_config(source_name, source_config)

        self.update_qr()

        self.setCentralWidget(self.central_widget)

        # check every 100 ms if client is running
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_if_client_is_running)

    def save_config(self) -> None:
        os.makedirs(os.path.dirname(self.configfile), exist_ok=True)

        with open(self.configfile, "w", encoding="utf-8") as f:
            dump(self.gather_config(), f, Dumper=Dumper)

    def gather_config(self) -> dict[str, Any]:
        sources = {}
        for source, tab in self.tabs.items():
            sources[source] = tab.get_config()

        general_config = self.general_config.get_config()

        return {"sources": sources, "config": general_config}

    def check_if_client_is_running(self) -> None:
        if self.syng_client is None:
            self.timer.stop()
            return

        ret = self.syng_client.poll()
        if ret is not None:
            _, stderr = self.syng_client.communicate()
            stderr_lines = stderr.decode("utf-8").strip().split("\n")
            if stderr_lines and stderr_lines[-1].startswith("Warning"):
                self.notification_label.setText(stderr_lines[-1])
            else:
                self.notification_label.setText("")
            self.syng_client.wait()
            self.syng_client = None
            self.set_client_button_start()
        else:
            self.set_client_button_stop()

    def set_client_button_stop(self) -> None:
        self.startbutton.setText("Stop")

    def set_client_button_start(self) -> None:
        self.startbutton.setText("Save and Start")

    def start_syng_client(self) -> None:
        if self.syng_client is None or self.syng_client.poll() is not None:
            self.save_config()
            self.syng_client = subprocess.Popen(["syng", "client"], stderr=subprocess.PIPE)
            self.notification_label.setText("")
            self.timer.start()
            self.set_client_button_stop()
        else:
            self.syng_client.terminate()
            self.syng_client.wait(1.0)
            self.syng_client.kill()
            self.set_client_button_start()

    def start_syng_server(self) -> None:
        if self.syng_server is None:
            root_path = os.path.join(os.path.dirname(__file__), "static")
            self.syng_server = multiprocessing.Process(
                target=run_server,
                args=[
                    Namespace(
                        host="0.0.0.0",
                        port=8080,
                        registration_keyfile=None,
                        root_folder=root_path,
                        private=False,
                        restricted=False,
                    )
                ],
            )
            self.syng_server.start()
            self.startsyng_serverbutton.setText("Stop Local Server")
        else:
            self.syng_server.terminate()
            self.syng_server.join()
            self.syng_server = None
            self.startsyng_serverbutton.setText("Start Local Server")

    def open_web(self) -> None:
        config = self.general_config.get_config()
        syng_server = config["server"]
        syng_server += "" if syng_server.endswith("/") else "/"
        room = config["room"]
        webbrowser.open(syng_server + room)

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


def run_gui() -> None:
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication([])
    app.setApplicationName("Syng")
    app.setDesktopFileName("rocks.syng.Syng")
    window = SyngGui()
    window.show()
    app.exec()
