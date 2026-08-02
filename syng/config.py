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
    override,
)

import platformdirs
from yaml import Dumper, Loader, dump, load

from syng.log import logger


@dataclass
class Config:
    """Base class for all configuration objects."""

    @staticmethod
    def migration(config_dict: dict[str, _Parsable]) -> dict[str, _Parsable]:
        """Migration from old config versions.

        Args:
            config_dict: Old configuration dictionary

        Returns:
            migrated configuration dictionary
        """
        return config_dict


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


class InitialQueueState(Enum):
    """Initial lockung state of the queue."""

    LOCKED = "Locked"
    UNLOCKED = "Unlocked"


@dataclass
class GeneralConfig(Config):
    """Configuration of the general behavior of Syng.

    Attributes:
        server: Hostname of the server to connect to.
        room: Room to connect to.
        secret: Secret of the room.
        max_songs_per_person: The maximum number of allowed songs in queue for a person
        allow_collab_mode: Allow poerformers to add collaboration tags.
        last_song: Time, after which no songs are accepted into the queue.
        key: Key for the server.
        buffer_in_advance: Number of songs to buffer in advance.
        log_level: Level of detail for the logs
        show_advanced: Show the advanced options.

    """

    __help__ = """<h3>Welcome to Syng.Rocks!</h3>

    <p>You can start right up by pressing "connect" and have a YouTube powered karaoke party, <br/>
    or enable <i>Advanced Options</i> to configure Syng.Rocks! to your liking</p>
    """

    server: str = field(
        default="https://syng.rocks",
        metadata={
            "update_qr": True,
            "desc": "Server",
            "simple": True,
            "help": """<p>The URL of the server, hosting the Syng-Server.</p>
            <p>You can run your own, or just use the public server at
            <a href="https://syng.rocks">https://syng.rocks</a>. 
            If you are using a pre-release version of syng, you might want to connect to 
            <a href="https://beta.syng.rocks">https://beta.syng.rocks</a> instead.</p>""",
        },
    )
    room: str = field(
        default_factory=lambda: "".join(secrets.choice(string.ascii_letters) for _ in range(6)),
        metadata={
            "update_qr": True,
            "desc": "Room",
            "simple": True,
            "help": """<p>The server can host multiple karaoke sessions at once. Each session gets 
            an ID, called room</p><p>You can provide your own name, or take the randomly generated
            name.</p><p>Only one playback client can be connected to a session. If you want to
            connect to an existing session, the <i>Admin Passwords</i> must match.

            <p><b>Note:</b> There is no mechanism to keep people from joining your session, 
            if they know the room id, so keep this id only for the participants of your 
            karaoke event.</p>
            """,
        },
    )
    secret: str = field(
        default_factory=lambda: "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(8)
        ),
        metadata={
            "semantic": "password",
            "desc": "Admin Password",
            "simple": True,
            "help": """<p>This is used to reconnect to a running session and to enter 
            <i>admin mode</i> in the web ui</p> You can enter the admin mode by clicking 
            <b>Advanced</b> on the web client welcome screen and enter this password.
            There you can moderate the playlist</p>""",
        },
    )
    initial_queue_state: InitialQueueState = field(
        default=InitialQueueState.UNLOCKED,
        metadata={
            "desc": "Initial State of the Queue",
            "help": """<p>If a queue is locked, only admins can add songs to it.</p>
            <p>The locked state of the queue can be changed in the webui, if you are an admin,
            or in the admin tab in this client.</p>
            <p>This option allows to set the initial state of the queue.</p>""",
        },
    )
    max_songs_per_person: int | None = field(
        default=1,
        metadata={
            "desc": "Max. songs per person",
            "help": """<p>To keep things fair, you can set a limit of how many songs each 
            participant can have in the queue, so no single person can <i>hog</i> the queue.</p>
            <p>If a participant wants to add more songs, these are put in the <i>waiting room</i>.
            Once they have less song than this number, these songs will be added to the queue.
            A value of 1 is recommended.</p>
            <p>Songs, that are added on an admin connection, ignore this limitation</p>
            <p><b>Note:</b> There is no real user tracking. Participants will be matched soley by
            their names, which they can freely change. If you notice persons abusing this, you may
            need to moderate manually</p>""",
        },
    )
    allow_collab_mode: bool = field(
        default=True,
        metadata={
            "desc": "Allow collaboration tags",
            "help": """<p>Sometimes people do not want to sing alone, but have no specific partner.
            </p><p>This enables collaboration tags, that can be included when adding a song to the
            queue. The tags are:<br /> <i>Everyone can join</i>, <i>Looking for Singer</i> and 
            <i>Just me</i>""",
        },
    )
    last_song: datetime | None = field(
        default=None,
        metadata={
            "desc": "Last song",
            "help": """<p>If your event has a predetermined end, you can set it here.</p>
            <p>If a song would exceed this time, it will be rejected.</p>
            <p>This limitation does not apply to an admin connection</p>""",
        },
    )
    key: str = field(
        default="",
        metadata={
            "semantic": "password",
            "desc": "Server Password",
            "help": """<p>If your server has needs a password to create rooms, you can set it here.
            The default server at <a href="https://syng.rocks">https://syng.rocks</a> does
            <b>not</b> need a password.</p>""",
        },
    )
    buffer_in_advance: int = field(
        default=2,
        metadata={
            "desc": "Buffer songs in advance",
            "help": """<p>For each remote source, download this many songs in advance, to ensure a
            smooth event.</p>""",
        },
    )
    log_level: LogLevel = field(
        default=LogLevel.INFO,
        metadata={
            "desc": "Log Level",
            "help": """<p>Level of logging shown on the <i>Logs</i> tab.
            This can be used for debugging.</p>""",
        },
    )
    show_advanced: bool = field(
        default=False, metadata={"desc": "Show Advanced Options", "hidden": True}
    )

    @override
    @staticmethod
    def migration(config_dict: dict[str, _Parsable]) -> dict[str, _Parsable]:
        # Version 2.3.0 to 2.4.0
        if "waiting_room_policy" in config_dict:
            max_songs_per_person: int | None
            match config_dict["waiting_room_policy"]:
                case None:
                    max_songs_per_person = None
                case "forced":
                    max_songs_per_person = 1
                case "optional":
                    max_songs_per_person = 1
                case _:
                    max_songs_per_person = None
            logger.warning(
                "Migration from earlyer version. 'waiting_room_policy': "
                f"{config_dict['waiting_room_policy']} -> "
                f"'max_songs_per_person': {max_songs_per_person}"
            )
            config_dict["max_songs_per_person"] = max_songs_per_person
        return config_dict


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

    __help__ = """<h3>UI Configuration</h3>
    <p>You can set some look and feel options here.</p>"""

    preview_duration: int = field(
        default=3,
        metadata={
            "desc": "Next Up Screen Duration",
            "help": """<p>Between the songs, there is a pause of this length in seconds 
            to switch out performers. During this pause, the next performers and song 
            will previewed.</p>""",
        },
    )
    next_up_time: int = field(
        default=20,
        metadata={
            "desc": "Next Up Box Duration",
            "help": """<p>During the last seconds of each performance, the next performance will be
            announced by a small popup.</p><p>This option defines these amount of seconds, the 
            popup is shown</p>""",
        },
    )
    qr_box_size: int = field(
        default=7,
        metadata={
            "desc": "QR Code Box Size",
            "help": """<p>The number of pixels for every \"block\" of the qr code. This is used to 
            size of the qr code, that is shown during performance to join.</p>""",
        },
    )
    qr_position: QRPosition = field(
        default=QRPosition.BOTTOM_RIGHT,
        metadata={"desc": "QR Code Position", "help": """Set the corner, the QR Code is shown."""},
    )
    pause_background: str = field(
        default=os.path.join(platformdirs.user_data_dir("syng"), "background.png"),
        metadata={
            "desc": "Pause Image",
            "semantic": "file",
            "help": """<p>Background image when no song is played</p>""",
        },
    )
    pause_music: str | None = field(
        default=os.path.join(platformdirs.user_data_dir("syng"), "background.mp3"),
        metadata={
            "desc": "Pause Music",
            "semantic": "file",
            "help": """<p>Music, that is played in a loop, when no song is played</p>""",
        },
    )
    preview_background: str = field(
        default=os.path.join(platformdirs.user_data_dir("syng"), "background20perc.png"),
        metadata={
            "desc": "Next Up Background",
            "semantic": "file",
            "help": """<p>Backgound image behind the Next Up Screen</p>""",
        },
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

    enabled: bool = field(
        default=False,
        metadata={
            "desc": "Enable this source",
            "help": "This source will only be used if enabled.",
        },
    )


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
) -> T | list[T] | int | str | datetime | None:
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
