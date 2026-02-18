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
    pass


class WaitingRoomPolicy(Enum):
    FORCED = "forced"
    OPTIONAL = "optional"
    NONE = "none"


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class GeneralConfig(Config):
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
    show_advanced: bool = False


class QRPosition(Enum):
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"


@dataclass
class UIConfig(Config):
    preview_duration: int = field(default=3, metadata={"desc": "Preview duration in seconds"})
    qr_box_size: int = 7
    show_advanced: bool = False
    next_up_time: int = 20
    qr_position: QRPosition = QRPosition.BOTTOM_RIGHT


@dataclass
class ClientConfig(Config):
    general: GeneralConfig = field(default_factory=GeneralConfig, metadata={"flatten": True})
    ui: UIConfig = field(default_factory=UIConfig, metadata={"flatten": True})


@dataclass
class SourceConfig(Config):
    enabled: bool = field(default=False, metadata={"desc": "Enable this source"})


@dataclass
class SyngConfig(Config):
    config: ClientConfig
    source_configs: dict[str, SourceConfig]


type _Parsable = dict[str, "_Parsable"] | list["_Parsable"] | str | int | None


def deserialize_dataclass[T](clas: type[T], data: dict[str, _Parsable]) -> T:
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
    return [deserialize_config(clas, item) for item in data]


def deserialize_enum[T: Enum](clas: type[T], data: str | int) -> T:
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

    :returns: A dictionary with the default configuration.
    :rtype: dict[str, Optional[int | str]]
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
    output: dict[str, _Parsable] = {}
    for data_field in fields(config):
        if data_field.metadata.get("flatten", False):
            output |= serialize_config(getattr(config, data_field.name))
        else:
            output[data_field.name] = serialize_config(getattr(config, data_field.name))
    return output


def load_config(filename: str, source_config_types: Mapping[str, type[SourceConfig]]) -> SyngConfig:
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
    general = serialize_dataclass(config.config)
    sources = {
        source_name: serialize_dataclass(source_config)
        for source_name, source_config in config.source_configs.items()
    }
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        dump({"config": general, "sources": sources}, f, Dumper=Dumper)
