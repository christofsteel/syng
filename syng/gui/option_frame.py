"""Windget, that hold options depending on the types of a configuration object."""

from collections.abc import MutableMapping
from dataclasses import asdict, fields
from enum import Enum
from functools import partial
from types import NoneType, UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QWidget,
)

from syng.config import Config
from syng.gui.row_widgets import (
    Boolean,
    RowWidget,
    SupportedBaseType,
    make_input_widget,
    make_optional_input_widget,
    make_row,
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
            default: Any = (
                field.default
                if field.default
                else field.default_factory()
                if callable(field.default_factory)
                else None
            )
            if hidden:
                continue

            field_type = config_types[name]
            value = values[name]
            optional = False
            if get_origin(field_type) in (Union, UnionType):
                args = get_args(field_type)
                if NoneType in args:
                    parts = [ty for ty in args if ty is not NoneType]
                    if len(parts) == 1:
                        field_type = parts[0]
                        optional = True

            if field_type is bool and isinstance(value, bool):
                field_type = Boolean
            self.add_config_row(field_type, name, description, value, semantic, optional, default)

    def set_config_field(self, name: str, value: Any) -> None:
        """Set a field of the configuration object, if it exists.

        If the object does not have the attribute, nothing happens.

        Args:
            name: name of the attribute
            value: value to set

        """
        if hasattr(self.config, name):
            setattr(self.config, name, value)

    def add_config_row[T: SupportedBaseType | Enum](
        self,
        ty: type[T],
        name: str,
        description: str,
        value: T,
        semantic: str | None,
        optional: bool,
        default: T,
    ) -> None:
        """Add a row to the form, depending on the type of an option.

        The following types are supported:
            - bool
            - int
            - str (with semantic: "password", "folder", "file" or None)
            - list[str]
            - datetime
            - enums

        Args:
            ty: The type for which to add a row
            name: The attribute name in the config object (for the update callback)
            description: Label for the inputfield
            value: Initial value
            semantic: Semantic specification of the type (see above)
            optional: If True, the option can be deactivated
            default: The default value for the setting

        """
        if optional:
            input_widget = make_optional_input_widget(ty, semantic, value, default)
        else:
            input_widget = make_input_widget(ty, semantic, value, default)

        origin = get_origin(ty)
        signal_ty: type[Any] = ty
        if origin is not None:
            signal_ty = origin
        if optional:
            signal_ty = object

        settings_row = make_row(Signal(signal_ty), description, input_widget, self)

        self.options[name] = settings_row
        settings_row.valueChanged.connect(partial(self.set_config_field, name))
        self.form_layout.addRow(*settings_row.to_form_tuple())

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
        self.options: MutableMapping[str, RowWidget[Any]] = {}

        self.config = config
        self.add_rows_from_config(config)

    @property
    def option_names(self) -> set[str]:
        """Names of all registered options.

        Returns:
            All option names.

        """
        return set(self.options.keys())

    def load_config(self, config: Config) -> None:
        """Load and apply options to the form.

        Args:
            config: Cofiguration object with values.

        """
        config_dict = asdict(config)

        for name, form_row in self.options.items():
            form_row.set_value(config_dict[name])
