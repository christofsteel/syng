"""Module for the configuration objects and serialization and deserialization."""

from __future__ import annotations

import os
import secrets
import string
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum
from types import UnionType
from typing import (
    Union,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from yaml import Dumper, Loader, dump, load


@dataclass
class Config:
    """Base class for all configuration objects."""

    pass


class WaitingRoomPolicy(Enum):
    """Policy for the waiting room.

    Options are:
        - FORCED: If a performer has more than one entry in the queue, all other will be send to
            the waiting room.
        - OPTIONAL: If a performer has more than one entry in the queue, they get a choice to be
            send to the waiting room.
        - NONE: Waiting room is disabled.

    """

    FORCED = "forced"
    OPTIONAL = "optional"
    NONE = "none"


class LogLevel(Enum):
    """Log level for the client."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class GeneralConfig(Config):
    """Configuration of the general behavior of Syng.

    Attributes:
        server: Hostname of the server to connect to.
        room: Room to connect to.
        secret: Secret of the room.
        waiting_room_policy: The waiting room policy.
        allow_collab_mode: Allow poerformers to add collaboration tags.
        last_song: Time, after which no songs are accepted into the queue.
        key: Key for the server.
        buffer_in_advance: Number of songs to buffer in advance.
        log_level: Level of detail for the logs
        show_advanced: Show the advanced options.

    """

    server: str = field(
        default="https://syng.rocks", metadata={"update_qr": True, "desc": "Server", "simple": True}
    )
    room: str = field(
        default_factory=lambda: "".join(secrets.choice(string.ascii_letters) for _ in range(6)),
        metadata={"update_qr": True, "desc": "Room", "simple": True},
    )
    secret: str = field(
        default_factory=lambda: "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
        ),
        metadata={"semantics": "password", "desc": "Admin Password", "simple": True},
    )
    waiting_room_policy: WaitingRoomPolicy = field(
        default=WaitingRoomPolicy.NONE, metadata={"desc": "Waiting room policy"}
    )
    allow_collab_mode: bool = field(
        default=True, metadata={"desc": "Allow performers to add collaboration tags"}
    )
    last_song: datetime | None = field(default=None, metadata={"desc": "Last song ends at"})
    key: str = field(
        default="", metadata={"semantics": "password", "desc": "Key for server (if necessary)"}
    )
    buffer_in_advance: int = field(default=2, metadata={"desc": "Buffer the next songs in advance"})
    log_level: LogLevel = field(default=LogLevel.INFO, metadata={"desc": "Log Level"})
    show_advanced: bool = field(
        default=False, metadata={"desc": "Show Advanced Options", "hidden": True}
    )


class QRPosition(Enum):
    """Corner of the QR code to show."""

    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"


@dataclass
class UIConfig(Config):
    """Configuration options for the UI elements.

    Attributes:
        preview_duration: Duration the "next up" screen is shown
        qr_box_size: Size of the QR Code
        next_up_time: Duration of the "next up" pop-up.
        qr_position: Position of the qr code.

    """

    preview_duration: int = field(default=3, metadata={"desc": "Preview duration in seconds"})
    next_up_time: int = field(
        default=20, metadata={"desc": "Time remaining before Next Up Box is shown"}
    )
    qr_box_size: int = field(default=7, metadata={"desc": "QR Code Box Size"})
    qr_position: QRPosition = field(
        default=QRPosition.BOTTOM_RIGHT, metadata={"desc": "QR Code Position"}
    )


@dataclass
class ClientConfig(Config):
    """Configuration of the client.

    Attributes:
        general: General configuration options.
        ui: UI configuration options.

    """

    general: GeneralConfig = field(default_factory=GeneralConfig, metadata={"flatten": True})
    ui: UIConfig = field(default_factory=UIConfig, metadata={"flatten": True})


@dataclass
class SourceConfig(Config):
    """Base class for configuration for sources.

    Attributes:
        enabled: Wheather the source is enabled.

    """

    enabled: bool = field(default=False, metadata={"desc": "Enable this source"})


@dataclass
class SyngConfig(Config):
    """Complete configuration of the Syng client.

    Attributes:
        config: Configuration for the playback
        sources: Configuration for each source.

    """

    config: ClientConfig
    source_configs: dict[str, SourceConfig]


type _Parsable = dict[str, "_Parsable"] | list["_Parsable"] | str | int | None


def deserialize_dataclass[T](clas: type[T], data: dict[str, _Parsable]) -> T:
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
    field_types = get_type_hints(clas)
    dataclass_arguments = {}

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


def deserialize_config[T](clas: type[T], data: _Parsable) -> T | list[T] | datetime | None:
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
    if isinstance(data, dict):
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
    if issubclass(clas, Enum):
        if not isinstance(data, str) and not isinstance(data, int):
            raise TypeError(
                f"got '{data}' of type '{type(data)}, expected 'str' or 'int' to create {clas}"
            )
        return deserialize_enum(clas, data)

    raise TypeError(f"unsupported field type '{clas}'")


def default_config() -> dict[str, int | str | None]:
    """Return a default configuration for the client.

    Returns:
        A dictionary with the default configuration.
    """
    return {
        "server": "https://syng.rocks",
        "room": "",
        "preview_duration": 3,
        "secret": None,
        "last_song": None,
        "waiting_room_policy": None,
        "key": None,
        "buffer_in_advance": 2,
        "qr_box_size": 7,
        "qr_position": "top-right",
        "show_advanced": False,
        "log_level": "info",
        "next_up_time": 20,
        "allow_collab_mode": True,
    }


type _Serializable = Config | int | str | datetime | None | Enum | list[_Serializable]


@overload
def serialize_config(inp: Config) -> dict[str, _Parsable]: ...
@overload
def serialize_config(inp: datetime) -> str: ...
@overload
def serialize_config(inp: list[_Serializable]) -> list[_Parsable]: ...
@overload
def serialize_config(inp: str) -> str: ...
@overload
def serialize_config(inp: int) -> int: ...
@overload
def serialize_config(inp: None) -> None: ...
@overload
def serialize_config(inp: Enum) -> int: ...


def serialize_config(inp: _Serializable) -> _Parsable:
    """Serialize an object to dict or data.

    The following types can be serialized:
        - ``Config``-objects (to dict)
        - datetime (to iso8601-strings)
        - strings (directly)
        - integer (directly)
        - lists (to lists)
        - None (directly)
        - Enum (to string or integer value)

    Args:
        inp: Inputdata

    Returns:
        dict, list, string or int, depending on the input.

    Raises:
        ValueError: if a nonsupported object is given.

    """
    if isinstance(inp, Config):
        return serialize_dataclass(inp)
    if isinstance(inp, datetime):
        return inp.isoformat()
    if isinstance(inp, str):
        return inp
    if isinstance(inp, int):
        return inp
    if isinstance(inp, list):
        return [serialize_config(element) for element in inp]
    if inp is None:
        return None
    if isinstance(inp, Enum) and isinstance(inp.value, int):
        return inp.value
    if isinstance(inp, Enum) and isinstance(inp.value, str):
        return inp.value
    raise ValueError(f"Could not serialize {inp} of type {type(inp)}")


def serialize_dataclass(config: Config) -> _Parsable:
    """Serialize a Config object to a dict.

    If a field is annotated as "flatten" in its metadata, its attributes are included in the parent
    dict.

    Args:
        config: Config object to serialize.

    Returns:
        dictionary, mapping the fieldsnames to serialized data

    """
    output: dict[str, _Parsable] = {}
    for data_field in fields(config):
        if data_field.metadata.get("flatten", False):
            output |= serialize_config(getattr(config, data_field.name))
        else:
            output[data_field.name] = serialize_config(getattr(config, data_field.name))
    return output


def load_config(filename: str, source_config_types: Mapping[str, type[SourceConfig]]) -> SyngConfig:
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
        loaded_config = {"config": {}, "sources": {}}

    sources_config: dict[str, SourceConfig] = {}

    for source_name, source_config_type in source_config_types.items():
        source_config_dict = loaded_config.get("sources", {}).get(source_name, {})
        sources_config[source_name] = deserialize_config(source_config_type, source_config_dict)
    client_config = deserialize_config(ClientConfig, loaded_config["config"])
    return SyngConfig(client_config, sources_config)


def save_config(filename: str, config: SyngConfig) -> None:
    """Serialize and save the configuration to a file.

    Args:
        filename: Path to the file
        config: Configuration object

    """
    general = serialize_dataclass(config.config)
    sources = {
        source_name: serialize_dataclass(source_config)
        for source_name, source_config in config.source_configs.items()
    }
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        dump({"config": general, "sources": sources}, f, Dumper=Dumper)
