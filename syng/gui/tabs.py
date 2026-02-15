from collections.abc import Callable
from dataclasses import fields
from types import NoneType, UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from PySide6.QtWidgets import QWidget

from syng.gui.option_frame import OptionFrame
from syng.sources.source import SourceConfig


class SourceTab(OptionFrame):
    def __init__(self, parent: QWidget, config: SourceConfig) -> None:
        super().__init__(config, parent)
        config_types = get_type_hints(config.__class__)
        values = config.__dict__

        for field in fields(config):
            name = field.name
            description: str = field.metadata.get("desc", "")
            semantic: str | None = field.metadata.get("semantic", None)
            field_type = config_types[name]
            value = values[name]
            if get_origin(field_type) in (Union, UnionType):
                args = get_args(field_type)
                if NoneType in args:
                    parts = [ty for ty in args if ty is not NoneType]
                    if len(parts) == 1:
                        field_type = parts[0]

            self.add_option(field_type, name, description, value, semantic)


class UIConfigTab(OptionFrame):
    def __init__(self, parent: QWidget, config: dict[str, Any]) -> None:
        super().__init__(config, parent)

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


class GeneralConfigTab(OptionFrame):
    def __init__(
        self,
        parent: QWidget,
        config: dict[str, Any],
        callback: Callable[..., None],
    ) -> None:
        super().__init__(config, parent)

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
