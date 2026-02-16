import logging
import os
import random
import secrets
import signal
import string
import sys
from datetime import datetime
from io import BytesIO
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
from typing import TYPE_CHECKING, Any

import packaging.version

from syng.config import SourceConfig
from syng.gui.background_threads import SyngClientWorker, VersionCheckerWorker
from syng.gui.tabs import GeneralConfigTab, SourceTab, UIConfigTab

try:
    if not TYPE_CHECKING:
        from ctypes import windll

        appid = "rocks.syng.Syng.2.3.0"
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
except ImportError:
    pass


import platformdirs
from PySide6.QtCore import (
    QObject,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTabBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qrcode.main import QRCode

from syng import __version__, resources  # noqa
from syng.client import Client
from syng.config import (
    ClientConfig,
    GeneralConfig,
    SyngConfig,
    UIConfig,
    default_config,
    deserialize_config,
    load_config,
    save_config,
)
from syng.log import logger
from syng.sources import available_source_configs, available_sources


class QueueView(QListView):
    pass


class SyngGui(QMainWindow):
    def closeEvent(self, event: QCloseEvent) -> None:
        QMainWindow.closeEvent(self, event)
        self.destroy()
        if self.client_thread is not None and self.client_thread.isRunning():
            self.client_thread.cleanup()

        self.log_label_handler.cleanup()

    def add_buttons(self, show_advanced: bool) -> None:
        self.buttons_layout = QHBoxLayout()
        self.central_layout.addLayout(self.buttons_layout)

        self.resetbutton = QPushButton("Reset all to Default")
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

        self.startbutton = QPushButton("Connect")

        self.startbutton.clicked.connect(self.start_syng_client)
        self.buttons_layout.addWidget(self.startbutton)

    def export_queue(self) -> None:
        if self.client_thread is not None and self.client_thread.isRunning():
            filename = QFileDialog.getSaveFileName(self, "Export Queue", "", "JSON Files (*.json)")[
                0
            ]
            if filename:
                logger.debug("Exporting queue to %s", filename)
                self.client_thread.export_queue(filename)
        else:
            QMessageBox.warning(
                self,
                "No Client Running",
                "You need to start the client before you can export the queue.",
            )

    def import_queue(self) -> None:
        if self.client_thread.isRunning():
            filename = QFileDialog.getOpenFileName(self, "Import Queue", "", "JSON Files (*.json)")[
                0
            ]
            if filename:
                logger.debug("Importing queue from %s", filename)
                self.client_thread.import_queue(filename)
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
        if self.client_thread.isRunning():
            answer = QMessageBox.question(
                self,
                "Remove Room",
                "Are you sure you want to remove the room on the server? This will disconnect "
                "all clients and clear the queue.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.client_thread.remove_room()
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

        tabbar: QTabBar | None = self.tabview.tabBar()
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

    def add_general_config(self, config: GeneralConfig) -> None:
        self.general_config = GeneralConfigTab(self, config, self.update_qr)
        self.tabview.addTab(self.general_config, "General")

    def add_ui_config(self, config: UIConfig) -> None:
        self.ui_config = UIConfigTab(self, config)
        self.tabview.addTab(self.ui_config, "UI")

    def add_source_config(self, source_name: str, source_config: SourceConfig) -> None:
        self.tabs[source_name] = SourceTab(self, source_config)
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
        current_version: packaging.version.Version | None,
    ) -> None:
        running_version = packaging.version.parse(__version__)
        label_string = (
            f"<i>Running version: {running_version}</i><br />"
            f"Current version on pypi: {current_version}"
        )
        if current_version is not None:
            if current_version > running_version:
                label_string += (
                    '<br /><span style="color:red;">'
                    "A new version is available! Please update Syng.Rocks!</span>"
                )
            else:
                label_string += (
                    '<br /><span style="color:green;">You are running the latest '
                    'version.</span><br />Visit <a href="https://site.syng.rocks/">syng.rocks</a> '
                    "for more information."
                )
        self.version_label.setText(label_string)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Syng.Rocks!")

        if os.name != "nt":
            self.setWindowIcon(QIcon(":/icons/syng.ico"))

        self.pypi_version: str | None = None

        self.syng_client_logging_listener: QueueListener | None = None

        self.configfile = os.path.join(platformdirs.user_config_dir("syng"), "config.yaml")

        self.central_widget = QWidget(parent=self)
        self.central_layout = QVBoxLayout(self.central_widget)

        config = self.load_config(self.configfile)

        self.init_frame()
        self.init_tabs(config.config.general.show_advanced)
        self.add_buttons(config.config.general.show_advanced)
        self.add_general_config(config.config.general)
        self.add_ui_config(config.config.ui)
        self.add_qr(config.config.general.show_advanced)
        self.tabs: dict[str, SourceTab] = {}

        for source_name, source_config in config.source_configs.items():
            self.add_source_config(source_name, source_config)

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

        # run in background qthread
        self.version_worker = VersionCheckerWorker()
        self.version_worker.data.connect(self.update_version_label)
        self.version_worker.start()

        self.client_thread = SyngClientWorker()
        self.client_thread.finished.connect(self.set_client_button_start)
        self.client_thread.started.connect(self.set_client_button_stop)

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

        for source_name, source_tab in self.tabs.items():
            output["sources"][source_name] = source_tab.config

        return output

    def clear_config(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset all to Default",
            "Are you sure you want to clear the config?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            source_config_types = available_source_configs()
            default_source_configs = {
                source_name: config() for source_name, config in source_config_types.items()
            }
            self.update_config(SyngConfig(ClientConfig(), default_source_configs))

    def load_config(self, filename: str) -> SyngConfig:
        return load_config(filename, available_source_configs())

    def update_config(self, config: SyngConfig) -> None:
        self.general_config.load_config(config.config.general)
        self.ui_config.load_config(config.config.ui)
        for source_name, source_config in config.source_configs.items():
            self.tabs[source_name].load_config(source_config)

        self.update_qr()

    def save_config(self) -> None:
        save_config(self.configfile, self.gather_config())

    def gather_config(self) -> SyngConfig:
        sources: dict[str, SourceConfig] = {}
        for source, tab in self.tabs.items():
            sources[source] = tab.config

        general_config = self.general_config.get_config() | {
            "show_advanced": self.show_advanced_toggle.isChecked()
        }
        ui_config = self.ui_config.get_config()

        client_config = deserialize_config(ClientConfig, general_config | ui_config)

        return SyngConfig(client_config, sources)

    def import_config(self) -> None:
        filename = QFileDialog.getOpenFileName(self, "Open File", "", "YAML Files (*.yaml)")[0]

        if filename:
            config = self.load_config(filename)
            self.update_config(config)

    def export_config(self) -> None:
        filename = QFileDialog.getSaveFileName(self, "Save File", "", "YAML Files (*.yaml)")[0]
        if filename:
            config = self.gather_config()
            save_config(filename, config)

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
        if self.client_thread.isRunning():
            logger.debug("Stopping client")
            self.client_thread.cleanup()
            self.set_client_button_start()
        else:
            logger.debug("Starting client")
            if self.client_thread.isFinished():
                self.client_thread = SyngClientWorker()
                self.client_thread.finished.connect(self.set_client_button_start)
                self.client_thread.started.connect(self.set_client_button_stop)

            self.save_config()
            config = self.gather_config()

            client = Client(config)

            self.client_thread.set_client(client)
            self.client_thread.start()
            self.set_client_button_stop()

    @Slot(str, int)
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
        qr_pixmap.loadFromData(buf.getvalue())
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
        log_signal = Signal(str, int)

        def __init__(self, parent: QObject | None = None) -> None:
            super().__init__(parent)

    def __init__(self, parent: QObject | None = None) -> None:
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
        base_dir = sys._MEIPASS

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication([])

    if os.name == "nt":
        app.setWindowIcon(QIcon(os.path.join(base_dir, "syng.ico")))
    else:
        app.setWindowIcon(QIcon(":/icons/syng.ico"))
    app.setApplicationName("Syng.Rocks!")
    app.setDesktopFileName("rocks.syng.Syng")
    window = SyngGui()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
