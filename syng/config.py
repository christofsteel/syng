from dataclasses import _MISSING_TYPE, dataclass, fields, is_dataclass
from enum import Enum
from typing import (
    Any,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

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
class ChoiceOption[T](Option[T]):
    choices: list[T]


def generate_for_class(clas: type) -> dict[str, ConfigOption[Any]]:
    config_class = get_type_hints(clas)["config"]
    config_types = get_type_hints(config_class)

    config_options = {}

    for field in fields(config_class):
        description: str = field.metadata.get("desc", "")
        semantic: str | None = field.metadata.get("semantic", None)
        server: bool = field.metadata.get("server", False)
        field_type = config_types[field.name]

        config_option_type: Option[Any] | None = None
        if field_type is bool:
            config_option_type = BoolOption()
        elif field_type is int:
            config_option_type = IntOption()
        elif field_type is str:
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
        elif issubclass(field_type, Enum):
            config_option_type = ChoiceOption([a.value for a in field_type.__members__.values()])

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


type _Parsable = dict[str, "_Parsable"] | list["_Parsable"] | str | int | None


def generate_dataclass_from_dict[T](clas: type[T], data: dict[str, _Parsable]) -> T:
    field_types = get_type_hints(clas)
    dataclass_arguments = {
        attribute: generate_class_from_dict(field_types[attribute], value)
        for attribute, value in data.items()
        if attribute in field_types
    }
    return clas(**dataclass_arguments)


def generate_list_from_list[T](clas: type[T], data: list[_Parsable]) -> list[T]:
    return [generate_class_from_dict(clas, item) for item in data]


def generate_enum_from_data[T: Enum](clas: type[T], data: str | int) -> T:
    try:
        enum_value = clas(data)
    except ValueError:
        try:
            enum_value = clas(int(data))
        except ValueError:
            try:
                enum_value = clas(str(data))
            except ValueError as e:
                raise TypeError(
                    f"could not match '{data}' for enum '{clas}'. "
                    f"Possible values are '{list(clas.__members__.values())}'"
                ) from e
    return enum_value


@overload
def generate_class_from_dict[T](clas: type[list[T]], data: _Parsable) -> list[T]: ...
@overload
def generate_class_from_dict[T](clas: type[T], data: _Parsable) -> T: ...


def generate_class_from_dict[T](clas: type[T], data: _Parsable) -> T | list[T]:
    if is_dataclass(clas):
        if not isinstance(data, dict):
            raise TypeError(
                f"got '{data}' of type '{type(data)}, expected 'dict' to create '{clas}'"
            )
        return generate_dataclass_from_dict(clas, data)
    if get_origin(clas) is list:
        if not isinstance(data, list):
            raise TypeError(
                f"got '{data}' of type '{type(data)}, expected 'list' to create '{clas}'"
            )
        inner_class = get_args(clas)[0]
        return generate_list_from_list(inner_class, data)
    if any([clas is t for t in [str, int, bool]]):
        if not isinstance(data, clas):
            raise TypeError(f"got '{data} of type '{type(data)}', expected '{clas}'")
        return data
    if issubclass(clas, Enum):
        if not isinstance(data, str) or isinstance(data, int):
            raise TypeError(
                f"got '{data} of type '{type(data)}, expected 'str' or 'int' to create {clas}"
            )
        return generate_enum_from_data(clas, data)

    raise TypeError(f"unsupported field type '{clas}'")
