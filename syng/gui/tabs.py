"""Module containing the specific tabs for the configuration window."""

from collections.abc import Callable
from dataclasses import fields

from PySide6.QtWidgets import QWidget

from syng.config import GeneralConfig, SourceConfig, UIConfig
from syng.gui.option_frame import OptionFrame


class SourceTab(OptionFrame):
    """Configuration tab for a source configuration."""

    config: SourceConfig


class UIConfigTab(OptionFrame):
    """Configuration tab for the UI configuration."""

    config: UIConfig


class GeneralConfigTab(OptionFrame):
    """Configuration widget for the general settings."""

    config: GeneralConfig

    def toggle_show_advanced(self, state: bool | int) -> None:
        """Show/Hide advenced settings.

        If state is True or a number greater than 0, shows the settings, otherwise it hides them.

        Args:
            state: A value of True or a number greater than 0, shows the settings, otherwise they
                are hidden

        """
        state = state if isinstance(state, bool) else state > 0

        for option in self.option_names.difference(self.simple_options):
            self.rows[option][0].setVisible(state)
            widget_or_layout = self.rows[option][1]
            if isinstance(widget_or_layout, QWidget):
                widget_or_layout.setVisible(state)
            else:
                for i in range(widget_or_layout.count()):
                    item = widget_or_layout.itemAt(i)
                    widget = item.widget() if item else None
                    if widget:
                        widget.setVisible(state)

    def __init__(
        self,
        parent: QWidget,
        config: GeneralConfig,
        callback: Callable[..., None],
    ) -> None:
        """Initialize the widget.

        A configuration, that has not `simple`=True in its metadata is an advanced option.
        If configuration states, that advanced options should not be shown, they are hidden.

        Args:
            parent: Qt-Parent object
            config: Configuration object to store and access the configuration
            callback: Function, that is executed, when the server or room option changes.

        """
        super().__init__(parent, config)

        update_qr_fields = [
            field.name for field in fields(config) if field.metadata.get("update_qr", False)
        ]

        for name in update_qr_fields:
            self.string_options[name].textChanged.connect(callback)

        self.simple_options = [
            field.name for field in fields(config) if field.metadata.get("simple", False)
        ]

        self.toggle_show_advanced(config.show_advanced)
