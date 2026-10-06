"""Serialization functions for Config objects."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from types import NoneType, UnionType
from typing import Any, Union, cast, get_args, get_origin, get_type_hints, overload

from yaml import Loader, load

from syng.config.config import (
    Config,
    SourceOptions,
    SourcesConfig,
    SyngConfig,
    _Parsable,
)
from syng.config.serialize import serialize_dataclass
from syng.sources import Source, available_sources


def _get_field_type[T: Source](clas: type[T], field_name: str) -> type[Any] | None:
    for field, typ in get_type_hints(clas).items():
        if field == field_name:
            return cast(type[Any], typ)
    return NoneType


def deserialize_dataclass[T: Config](clas: type[T], data: dict[str, _Parsable]) -> T:
    """Deserialize a dataclass from a dict.

    If a dataclass has an attribute, that is marked as `flatten` in the metadata, it will be
    created using the data for the parent object.

    Args:
        clas: type of the class to deserialize
        data: data to construct the object from

    Returns:
        Object of type `clas` with data from `data`.

    Raises:
        TypeError: When the clas is not a dataclass.

    """
    if not is_dataclass(clas):
        raise TypeError(f"got '{data}' of type '{type(data)}, expected 'dict' to create '{clas}'")

    if issubclass(clas, SourceOptions):
        source_name = data["source_name"]
        if isinstance(source_name, str):
            real_class = _get_field_type(available_sources[source_name], "config")
            if real_class is not None:
                clas = real_class

    field_types = get_type_hints(clas)
    dataclass_arguments = {}

    data = clas.migration(data)

    for data_field in fields(clas):
        if data_field.metadata.get("flatten", False):
            dataclass_arguments[data_field.name] = deserialize_config(
                field_types[data_field.name], data
            )
        else:
            if data_field.name in data:
                dataclass_arguments[data_field.name] = deserialize_config(
                    field_types[data_field.name], data[data_field.name]
                )

    return clas(**dataclass_arguments)


def deserialize_list[T](clas: type[T], data: list[_Parsable]) -> list[T]:
    """Deserialize each element of a list to a list.

    Args:
        clas: The type of every element in the list.
        data: List of data to deserialize

    Returns:
        list of objects of type `clas`.

    """
    return [deserialize_config(clas, item) for item in data]


def deserialize_enum[T: Enum](clas: type[T], data: str | int) -> T:
    """Deserialize an enum.

    Deserialization is based on the values of each enum instance. If direct loading fails, the
    data is first read as an integer, if that fails it is read as a string.
    If both fail, a TypeError is raised.

    Args:
        clas: A subclass of type ``Enum``
        data: data, representing a enum value.

    Returns:
        Enum value for type `class`

    Raises:
        TypeError: If `data` cannot be loaded.

    """
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


def deserialize_datetime_or_None(data: _Parsable) -> datetime | None:
    """Deserialize a datetime object, or None.

    Handles both deserialization of datetime and NoneType objects.

    Args:
        data: datetime as iso8601-string to parse, or None

    Returns:
        datetime object, if data is a valid iso8601-string, None, if data is None

    Raises:
        TypeError: if data is neither a string, nor None.

    """
    if type(data) is str:
        return datetime.fromisoformat(data)
    elif data is None:
        return None
    raise TypeError(f"cannot convert '{data}' of type '{type(data)}' to 'datetime | None'")


@overload
def deserialize_config(clas: type[datetime] | type[None], data: _Parsable) -> datetime | None: ...
@overload
def deserialize_config[T](clas: type[list[T]], data: _Parsable) -> list[T]: ...
@overload
def deserialize_config[T](clas: type[T], data: _Parsable) -> T: ...


def deserialize_config[T](
    clas: type[T], data: _Parsable
) -> T | dict[str, T] | list[T] | int | str | datetime | None:
    """Deserialize an Object from a dictionary or data.

    This checks, that input data is of correct type according to `clas` and relays it to the
    correct deserializer.

    Currently the following objects can be deserialized:
        - dataclasses (from dicts)
        - lists (from lists)
        - strings (directly)
        - integers (directly)
        - bools (directly)
        - datetime | None (from iso8601-strings or None)
        - Enums (from int or str)

    Args:
        clas: type to create from the data
        data: data to deserialize to clas

    Returns:
        `clas` object

    Raises:
        TypeError: If data does not match to the desired outputclass

    """
    if isinstance(data, dict) and get_origin(clas) is dict:
        _, value_clas = get_args(clas)
        return {key: deserialize_config(value_clas, value) for key, value in data.items()}
    if isinstance(data, dict) and issubclass(clas, Config):
        return deserialize_dataclass(clas, data)
    if get_origin(clas) is list:
        if not isinstance(data, list):
            raise TypeError(
                f"got '{data}' of type '{type(data)}, expected 'list' to create '{clas}'"
            )
        inner_class = get_args(clas)[0]
        return deserialize_list(inner_class, data)
    if any([clas is t for t in [str, int, bool]]):
        if not isinstance(data, clas):
            raise TypeError(f"got '{data}' of type '{type(data)}', expected '{clas}'")
        return data
    if get_origin(clas) in (Union, UnionType) and set(get_args(clas)) == set(
        get_args(None | datetime)
    ):
        return deserialize_datetime_or_None(data)
    if (
        get_origin(clas) in (Union, UnionType)
        and set(get_args(clas)) == set(get_args(None | int))
        and (isinstance(data, int) or data is None)
    ):
        return data
    if (
        get_origin(clas) in (Union, UnionType)
        and set(get_args(clas)) == set(get_args(None | str))
        and (isinstance(data, str) or data is None)
    ):
        return data
    if issubclass(clas, Enum):
        if not isinstance(data, str) and not isinstance(data, int):
            raise TypeError(
                f"got '{data}' of type '{type(data)}, expected 'str' or 'int' to create {clas}"
            )
        return deserialize_enum(clas, data)

    raise TypeError(f"unsupported field type '{clas}'")


def load_config(
    filename: str, source_config_types: Mapping[str, type[SourceOptions]]
) -> SyngConfig:
    """Load and deserialize a yaml file to a configuration.

    The config file should have a ``config`` and a ``sources`` section.

    Args:
        filename: Path to the file
        source_config_types: Mapping of the sources to load to their configuration type.

    Returns:
        A configuration object for Syng.

    """
    try:
        with open(filename, encoding="utf8") as cfile:
            loaded_config = load(cfile, Loader=Loader)
    except FileNotFoundError:
        print("No config found, using default values")
        loaded_config = {
            "config": {},
            "sources": serialize_dataclass(
                SourcesConfig({"youtube": source_config_types["youtube"]()})
            ),
        }

    # client_config = deserialize_config(ClientConfig, loaded_config["config"])
    # sources_config = deserialize_config(SourcesConfig, loaded_config["sources"])
    syng_config = deserialize_config(SyngConfig, loaded_config)
    return syng_config
