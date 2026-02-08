from dataclasses import _MISSING_TYPE, dataclass, fields
from typing import Any, TypeVar, get_type_hints

T = TypeVar("T")


class Option[T]:
    pass


@dataclass
class ConfigOption[T]:
    type: Option[T]
    description: str
    default: T
    send_to_server: bool = False


class BoolOption(Option[bool]):
    pass


class IntOption(Option[int]):
    pass


class StrOption(Option[str]):
    pass


class PasswordOption(Option[str]):
    pass


class FolderOption(Option[str]):
    pass


class FileOption(Option[str]):
    pass


class ListStrOption(Option[list[str]]):
    pass


@dataclass
class ChoiceOption(Option[str]):
    choices: list[str]


def generate_for_class(clas: type) -> dict[str, ConfigOption[Any]]:
    config_class = get_type_hints(clas)["config_object"]
    config_options = {}

    for field in fields(config_class):
        description: str = field.metadata.get("desc", "")
        semantic: str | None = field.metadata.get("semantic", None)
        server: bool = field.metadata.get("server", False)

        config_option_type: Option[Any] | None = None
        if field.type is bool or field.type == "bool":
            config_option_type = BoolOption()
        elif field.type is int or field.type == "int":
            config_option_type = IntOption()
        elif field.type is str or field.type == "str":
            if semantic == "password":
                config_option_type = PasswordOption()
            elif semantic == "folder":
                config_option_type = FolderOption()
            elif semantic == "file":
                config_option_type = FileOption()
            elif semantic is None:
                config_option_type = StrOption()
        elif str(field.type) == "list[str]":
            config_option_type = ListStrOption()
        elif isinstance(field.type, str):
            literals = [
                literal.strip()[len("Literal") :].strip("\"'[]")
                for literal in field.type.split("|")
                if "Literal" in literal
            ]
            config_option_type = ChoiceOption(literals)

        if config_option_type is None:
            raise RuntimeError(f"Could not match {field.type}, {semantic}")

        default = None
        if not isinstance(field.default, _MISSING_TYPE):
            default = field.default
        elif not isinstance(field.default_factory, _MISSING_TYPE):
            default = field.default_factory()

        config_option = ConfigOption(
            config_option_type, description, default, send_to_server=server
        )
        config_options[field.name] = config_option

    return config_options
