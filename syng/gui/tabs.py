from collections.abc import Callable
from typing import Any

from PyQt6.QtWidgets import QWidget

from syng.config import (
    BoolOption,
    ChoiceOption,
    FileOption,
    FolderOption,
    IntOption,
    ListStrOption,
    PasswordOption,
    StrOption,
    generate_for_class,
)
from syng.gui.option_frame import OptionFrame
from syng.sources import available_sources


class SourceTab(OptionFrame):
    def __init__(self, parent: QWidget, source_name: str, config: dict[str, Any]) -> None:
        super().__init__(parent)
        source = available_sources[source_name]
        self.vars: dict[str, str | bool | list[str]] = {}
        for name, option in generate_for_class(source).items():
            value = config.get(name, option.default)
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
    def __init__(self, parent: QWidget, config: dict[str, Any]) -> None:
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
