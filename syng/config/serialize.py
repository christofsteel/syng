"""Serialization functions for Config objects."""

import os
from collections.abc import Mapping
from dataclasses import fields
from datetime import datetime
from enum import Enum
from typing import overload

from yaml import Dumper, dump

from syng.config.config import Config, SourceOptions, SyngConfig, _Parsable

type _Serializable = (
    Config | int | str | datetime | None | Enum | Mapping[str, _Serializable] | list[_Serializable]
)


@overload
def serialize_config(inp: Config) -> dict[str, _Parsable]: ...
@overload
def serialize_config(inp: Mapping[str, _Serializable]) -> dict[str, _Parsable]: ...
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
        - dicts (to dicts)
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
    if isinstance(inp, dict):
        return {key: serialize_config(value) for key, value in inp.items()}
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
    if isinstance(config, SourceOptions):
        output["type"] = str(type(config))
    return output


def save_config(filename: str, config: SyngConfig) -> None:
    """Serialize and save the configuration to a file.

    Args:
        filename: Path to the file
        config: Configuration object

    """
    general = serialize_dataclass(config.config)
    sources = serialize_config(config.sources)
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        dump({"config": general, "sources": sources}, f, Dumper=Dumper)
