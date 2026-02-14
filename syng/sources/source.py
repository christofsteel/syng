"""
Abstract class for sources.

Also defines the dictionary of available sources. Each source should add itself
to this dictionary in its module.
"""

from __future__ import annotations

import asyncio
import os.path
import shlex
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field, fields
from itertools import zip_longest
from traceback import print_exc
from typing import Any, get_type_hints

from syng.config import Config
from syng.entry import Entry
from syng.log import logger
from syng.result import Result


class EntryNotValid(Exception):
    """Raised when an entry is not valid for a source."""


@dataclass
class DLFilesEntry:
    """This represents a song in the context of a source.

    :param ready: This event triggers as soon, as all files for the song are
        downloaded/buffered.
    :type ready: asyncio.Event
    :param video: The location of the video part of the song.
    :type video: str
    :param audio: The location of the audio part of the song, if it is not
        incuded in the video file. (Default is ``None``)
    :type audio: Optional[str]
    :param buffering: True if parts are buffering, False otherwise (Default is
        ``False``)
    :type buffering: bool
    :param complete: True if download was completed, False otherwise (Default
        is ``False``)
    :type complete: bool
    :param skip: True if the next Entry for this file should be skipped
        (Default is ``False``)
    :param buffer_task: Reference to the task, that downloads the files.
    :type buffer_task: Optional[asyncio.Task[Tuple[str, Optional[str]]]]
    """

    # pylint: disable=too-many-instance-attributes

    ready: asyncio.Event = field(default_factory=asyncio.Event)
    video: str = ""
    audio: str | None = None
    buffering: bool = False
    complete: bool = False
    skip: bool = False
    buffer_task: asyncio.Task[tuple[str, str | None]] | None = None


@dataclass
class SourceConfig(Config):
    enabled: bool = field(default=False, metadata={"desc": "Enable this source"})


@dataclass
class Source(ABC):
    """Parentclass for all sources.

    A new source should subclass this, and at least implement
    :py:func:`Source.do_buffer`, :py:func:`Song.get_entry` and
    :py:func:`Source.get_file_list`, and set the ``source_name``
    attribute.

    Source specific tasks will be forwarded to the respective source, like:
        - Buffering the audio/video
        - Searching for a query
        - Getting an entry from an identifier
        - Handling the skipping of currently played song

    Some methods of a source will be called by the server and some will be
    called by the playback client.

    Specific server methods:
    ``get_entry``, ``search``, ``add_to_config``

    Specific client methods:
    ``buffer``, ``do_buffer``, ``skip_current``, ``ensure_playable``,
    ``get_missing_metadata``, ``get_config``

    Each source has a reference to all files, that are currently queued to
    download via the :py:attr:`Source.downloaded_files` attribute and a
    reference to a ``mpv`` process playing songs for that specific source

    :attributes: - ``downloaded_files``, a dictionary mapping
                   :py:attr:`Entry.ident` to :py:class:`DLFilesEntry`.
                 - ``player``, the reference to the ``mpv`` process, if it has
                   started
                 - ``extra_mpv_options``, dictionary of arguments added to the mpv
                   instance, can be overwritten by a subclass
                 - ``source_name``, the string used to identify the source
    """

    config: SourceConfig
    source_name: str = ""

    def __post_init__(self) -> None:
        self.downloaded_files: defaultdict[str, DLFilesEntry] = defaultdict(DLFilesEntry)
        self._masterlock: asyncio.Lock = asyncio.Lock()
        self.extra_mpv_options: dict[str, str] = {}
        self._skip_next = False

        self.build_index = False
        self._index: list[str] = []

    @classmethod
    def get_config_type(cls) -> type[SourceConfig]:
        config_type: type[SourceConfig] = get_type_hints(cls)["config"]
        if not issubclass(config_type, SourceConfig):
            raise TypeError
        return config_type

    def is_valid(self, entry: Entry) -> bool:
        """
        Check if the entry is valid.

        Each source can implement this method to check if the entry is valid.

        :param entry: The entry to check
        :type entry: Entry
        :returns: True if the entry is valid, False otherwise.
        :rtype: bool
        """
        return True

    async def get_entry(
        self,
        performer: str,
        ident: str,
        collab_mode: str | None,
        /,
        artist: str | None = None,
        title: str | None = None,
    ) -> Entry | None:
        """
        Create an :py:class:`syng.entry.Entry` from a given identifier.

        By default, this confirmes, that the ident is a valid entry (i.e. part
        of the indexed list), and builds an Entry by parsing the file name.

        Since the server does not have access to the actual file, only to the
        file name, ``duration`` can not be set. It will be approximated with
        180 seconds. When added to the queue, the server will ask the client
        for additional metadata, like this.

        :param performer: The performer of the song
        :type performer: str
        :param ident: Unique identifier of the song.
        :type ident: str
        :returns: New entry for the identifier, or None, if the ident is
            invalid.
        :rtype: Optional[Entry]
        :raises EntryNotValid: If the entry is not valid for the source.
        """

        res: Result = Result.from_filename(ident, self.source_name)
        if collab_mode not in ["solo", "group", "duet"]:
            collab_mode = None
        entry = Entry(
            ident=ident,
            source=self.source_name,
            duration=180,
            album=res.album if res.album else "Unknown",
            title=res.title if res.title else title if title else "Unknown",
            artist=res.artist if res.artist else artist if artist else "Unknown",
            performer=performer,
            incomplete_data=True,
            collab_mode=collab_mode,
        )
        if not self.is_valid(entry):
            raise EntryNotValid(f"Entry {entry} is not valid for source {self.source_name}")
        return entry

    async def search(self, query: str) -> list[Result]:
        """
        Search the songs from the source for a query.

        By default, this searches in the internal index.

        :param query: The query to search for
        :type query: str
        :returns: A list of Results containing the query.
        :rtype: list[Result]
        """
        filtered: list[str] = self.filter_data_by_query(query, self._index)
        results: list[Result] = []
        for filename in filtered:
            results.append(Result.from_filename(filename, self.source_name))
        return results

    @abstractmethod
    async def do_buffer(self, entry: Entry, pos: int) -> tuple[str, str | None]:
        """
        Source specific part of buffering.

        This should asynchronous download all required files to play the entry,
        and return the location of the video and audio file. If the audio is
        included in the video file, the location for the audio file should be
        `None`.

        Abstract, needs to be implemented by subclass.

        :param entry: The entry to buffer
        :type entry: Entry
        :param pos: The position in the queue, the entry is at.
        :type pos: int
        :returns: A Tuple of the locations for the video and the audio file.
        :rtype: Tuple[str, Optional[str]]
        """

    async def buffer(self, entry: Entry, pos: int) -> None:
        """
        Buffer all necessary files for the entry.

        This calls the specific :py:func:`Source.do_buffer` method. It
        ensures, that the correct events will be triggered, when the buffer
        function ends. Also ensures, that no entry will be buffered multiple
        times.

        If this is called multiple times for the same song (even if they come
        from different entries) This will immediately return.

        :param entry: The entry to buffer
        :type entry: Entry
        :param pos: The position in the queue, the entry is at.
        :type pos: int
        :rtype: None
        """
        async with self._masterlock:
            if self.downloaded_files[entry.ident].buffering:
                return
            self.downloaded_files[entry.ident].buffering = True

        try:
            buffer_task = asyncio.create_task(self.do_buffer(entry, pos))
            self.downloaded_files[entry.ident].buffer_task = buffer_task
            video, audio = await buffer_task

            self.downloaded_files[entry.ident].video = video
            self.downloaded_files[entry.ident].audio = audio
            self.downloaded_files[entry.ident].complete = True
        except ValueError as exc:
            raise exc
        except Exception as err:  # pylint: disable=broad-except
            print_exc()
            raise ValueError(f"Buffering failed for {entry}") from err

        self.downloaded_files[entry.ident].ready.set()

    async def skip_current(self, entry: Entry) -> None:
        """
        Skips first song in the queue.

        If it is played, the player is killed, if it is still buffered, the
        buffering is aborted. Then a flag is set to keep the player from
        playing it.

        :param entry: A reference to the first entry of the queue
        :type entry: Entry
        :rtype: None
        """
        async with self._masterlock:
            self._skip_next = True
            self.downloaded_files[entry.ident].buffering = False
            buffer_task = self.downloaded_files[entry.ident].buffer_task
            if buffer_task is not None:
                buffer_task.cancel()
            self.downloaded_files[entry.ident].ready.set()

    async def ensure_playable(self, entry: Entry) -> tuple[str, str | None]:
        """
        Guaranties that the given entry can be played.

        First start buffering, then wait for the buffering to end.

        :param entry: The entry to ensure playback for.
        :type entry: Entry
        :rtype: None
        """
        await self.buffer(entry, 0)
        dlfilesentry = self.downloaded_files[entry.ident]
        await dlfilesentry.ready.wait()
        return dlfilesentry.video, dlfilesentry.audio

    async def get_missing_metadata(self, _entry: Entry) -> dict[str, Any]:
        """
        Read and report missing metadata.

        If the source sended a list of filenames to the server, the server can
        search these filenames, but has no way to read e.g. the duration. This
        method will be called to return the missing metadata.

        By default this just returns an empty dict.

        :param _entry: The entry to get the metadata for
        :type _entry: Entry
        :returns: A dictionary with the missing metadata.
        :rtype dict[str, Any]
        """
        return {}

    @staticmethod
    def split_search_term(search_term: str) -> list[str]:
        """
        Split a search term, respecting quoted spaces

        If quotation is not deterministic, fall back to splitting at each space
        """
        try:
            return shlex.split(search_term)
        except ValueError:
            splits = search_term.split(" ")
            logger.debug(f"Failed to split '{search_term}', falling back to {splits}")
            return splits

    def filter_data_by_query(self, query: str, data: list[str]) -> list[str]:
        """
        Filter the ``data``-list by the ``query``.

        :param query: The query to filter
        :type query: str
        :param data: The list to filter
        :type data: list[str]
        :return: All entries in the list containing the query.
        :rtype: list[str]
        :raises: MalformedSearchQueryException when the search query is malformed
        """

        def contains_all_words(words: list[str], element: str) -> bool:
            return all(word.lower() in os.path.basename(element).lower() for word in words)

        splitquery = Source.split_search_term(query)

        return [element for element in data if contains_all_words(splitquery, element)]

    async def get_file_list(self) -> list[str]:
        """
        Gather a list of all files belonging to the source.

        This list will be send to the server. When the server searches, this
        list will be searched.

        :return: List of filenames belonging to the source
        :rtype: list[str]
        """
        return []

    async def update_file_list(self) -> list[str] | None:
        """
        Update the internal list of files.

        This is called after the client sends its initial file list to the
        server to update the list of files since the last time an index file
        was written.

        It should return None, if the list is already up to date.
        Otherwise it should return the new list of files.


        :rtype: Optional[list[str]]
        """
        return None

    async def update_config(self) -> dict[str, Any] | list[dict[str, Any]] | None:
        """
        Update the config of the source.

        This is called after the client sends its initial config to the server to
        update the config. E.g. to update the list of files, that should be send to
        the server.

        It returns None, if the config is already up to date.
        Otherwise returns the new config.

        :rtype: Optional[dict[str, Any] | list[dict[str, Any]]
        """

        if not self.build_index:
            return None
        logger.warning(f"{self.source_name}: updating index")
        new_index = await self.update_file_list()
        logger.warning(f"{self.source_name}: done")
        if new_index is not None:
            self._index = new_index
            return await self.get_config()
        return None

    async def get_config(self) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Return the part of the config, that should be sent to the server.

        Can be either a dictionary or a list of dictionaries. If it is a
        dictionary, a single message will be sent. If it is a list, one message
        will be sent for each entry in the list.

        By default, this is the list of files handled by the source, split into
        chunks of 1000 filenames. This list is cached internally, so it does
        not need to be rebuilt, when the client reconnects.

        But this can be any other values, as long as the respective source can
        handle that data.

        :return: The part of the config, that should be sent to the server.
        :rtype: dict[str, Any] | list[dict[str, Any]]
        """
        packages = []

        if self.build_index:
            if not self._index:
                self._index = []
                logger.warning(f"{self.source_name}: generating index")
                self._index = await self.get_file_list()
                logger.warning(f"{self.source_name}: done")
            chunked = zip_longest(*[iter(self._index)] * 1000, fillvalue="")
            packages = [{"index": list(filter(lambda x: x != "", chunk))} for chunk in chunked]

        first_package = {
            field.name: getattr(self.config, field.name)
            for field in fields(self.config)
            if field.metadata.get("server", False)
        }
        if not packages:
            packages = [first_package]
        else:
            packages[0] |= first_package
        if len(packages) == 1:
            return first_package
        return packages

    def add_to_config(self, config: dict[str, Any], running_number: int) -> None:
        """
        Add the config to the own config.

        This is called on the server, if :py:func:`Source.get_config` returns a
        list.

        In the default configuration, this just adds the index key of the
        config to the index attribute of the source

        If the running_number is 0, the index will be reset.

        :param config: The part of the config to add.
        :type config: dict[str, Any]
        :param running_number: The running number of the config
        :type running_number: int
        :rtype: None
        """
        if running_number == 0:
            self._index = []
        self._index += config["index"]


available_sources: dict[str, type[Source]] = {}
