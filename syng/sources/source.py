"""Abstract class for sources.

Also defines the dictionary of available sources. Each source should add itself
to this dictionary in its module.
"""

from __future__ import annotations

import asyncio
import os.path
import shlex
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from traceback import print_exc
from typing import Any

from syng.config import SourceConfig
from syng.entry import Entry
from syng.log import logger
from syng.result import Result


class EntryNotValid(Exception):
    """Raised when an entry is not valid for a source."""


@dataclass
class DLFilesEntry:
    """A song in the context of a source.

    This stores additional metadata, like the download/buffering status

    Attributes:
        ready: Event, that triggers as soon, as all files for the song are
        downloaded/buffered.
        video: The location of the video part of the song.
        audio: The location of the audio part of the song, if it is not
        incuded in the video file. (Default is ``None``)
        buffering: True if parts are buffering, False otherwise (Default is
        ``False``)
        complete: True if download is completed, False otherwise (Default
        is ``False``)
        skip: True if the next Entry for this file should be skipped
        (Default is ``False``)
        buffer_task: Reference to the task, that downloads the files.

    """

    ready: asyncio.Event = field(default_factory=asyncio.Event)
    video: str = ""
    audio: str | None = None
    buffering: bool = False
    complete: bool = False
    skip: bool = False
    buffer_task: asyncio.Task[tuple[str, str | None]] | None = None


@dataclass
class Source(ABC):
    """Parentclass for all sources.

    A new source should subclass this, and at least implement
    :py:func:`Source.do_buffer`, :py:func:`Source.data_from_ident`,
    :py:func:`Source.get_file_list`, and set the ``source_name``
    attribute.

    Source specific tasks will be forwarded to the respective source, like:
        - Buffering the audio/video
        - Searching for a query
        - Getting an entry from an identifier
        - Handling the skipping of currently played song

    Each source has a reference to all files, that are currently queued to
    download via the :py:attr:`Source.downloaded_files` attribute.

    Attributes:
        config: Specific configuration for a source
        source_name: Name of the source
        downloaded_files: Mapping to files, that are currently downloading or available
        extra_mpv_options: Extra options, that will be passed to the mpv player

    """

    config: SourceConfig
    source_name: str = ""
    build_index: bool = False

    def __post_init__(self) -> None:
        """Initialize basic source options."""
        self.downloaded_files: defaultdict[str, DLFilesEntry] = defaultdict(DLFilesEntry)
        self._masterlock: asyncio.Lock = asyncio.Lock()
        self.extra_mpv_options: dict[str, str] = {}
        self._skip_next = False

        # self.build_index = False
        self._index: list[str] = []

    def is_valid(self, entry: Entry) -> bool:
        """Check if the entry is valid.

        Each source can implement this method to check if the entry is valid. This returns always
        True.

        Args:
            entry: The entry to check

        Returns:
            True

        """
        return True

    async def configure(self) -> None:
        """Run configuration for a source."""
        if self.build_index:
            self._index = []
            logger.info(f"{self.source_name}: generating index")
            self._index = await self.get_file_list()
            logger.info(f"{self.source_name}: done")

    async def search(self, query: str) -> list[Result]:
        """Search the songs from the source for a query.

        By default, this searches in the internal index.

        Args:
            query: The query to search for.

        Returns:
            A list of Results containing the query.

        """
        filtered: list[str] = self.filter_data_by_query(query, self._index)
        results: list[Result] = []
        for filename in filtered:
            metadata = self.data_from_ident(filename)
            results.append(
                Result.from_dict(metadata | {"ident": filename, "source": self.source_name})
            )
        return results

    @abstractmethod
    def data_from_ident(self, ident: str) -> dict[str, str]:
        """Return all known information from the ident in a dictionary."""

    @abstractmethod
    async def do_buffer(self, entry: Entry, pos: int) -> tuple[str, str | None]:
        """Source specific part of buffering.

        This should asynchronous download all required files to play the entry,
        and return the location of the video and audio file. If the audio is
        included in the video file, the location for the audio file should be
        ``None``.

        Abstract, needs to be implemented by subclass.

        Args:
            entry: The entry to buffer
            pos: The position in the queue, the entry is at.

        Returns:
            A tuple of the locations for the video and the audio file.

        """

    async def buffer(self, entry: Entry, pos: int) -> None:
        """Buffer all necessary files for the entry.

        This calls the specific :py:func:`Source.do_buffer` method. It
        ensures, that the correct events will be triggered, when the buffer
        function ends. Also ensures, that no entry will be buffered multiple
        times.

        If this is called multiple times for the same song (even if they come
        from different entries) This will immediately return.

        Args:
            entry: The entry to buffer
            pos: The position in the queue, the entry is at.

        Raises:
            ValueError: If buffering failes for any reason.

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
        """Skips buffering the first song in the queue.

        Args:
            entry: A reference to the first entry of the queue

        """
        async with self._masterlock:
            self._skip_next = True
            self.downloaded_files[entry.ident].buffering = False
            buffer_task = self.downloaded_files[entry.ident].buffer_task
            if buffer_task is not None:
                buffer_task.cancel()
            self.downloaded_files[entry.ident].ready.set()

    async def ensure_playable(self, entry: Entry) -> tuple[str, str | None]:
        """Guaranties that the given entry can be played.

        First start buffering, then wait for the buffering to end.

        Args:
            entry: The entry to ensure playback for.

        Returns:
            The path to the video file and the audio file. The latter is ``None``, if audio is
            included in the video file.

        """
        await self.buffer(entry, 0)
        dlfilesentry = self.downloaded_files[entry.ident]
        await dlfilesentry.ready.wait()
        return dlfilesentry.video, dlfilesentry.audio

    async def get_missing_metadata(self, _entry: Entry) -> dict[str, Any]:
        """Read and report missing metadata.

        If the source sended a list of filenames to the server, the server can
        search these filenames, but has no way to read e.g. the duration. This
        method will be called to return the missing metadata.

        By default this just returns an empty dict.

        Args:
            _entry: The entry to get the metadata for

        Returns:
            A dictionary with the missing metadata.

        """
        return {}

    @staticmethod
    def split_search_term(search_term: str) -> list[str]:
        """Split a search term, respecting quoted spaces.

        If quotation is not deterministic, fall back to splitting at each space

        Args:
            search_term: The search term to split.

        Returns:
            List of words, respecting quotations.

        """
        try:
            return shlex.split(search_term)
        except ValueError:
            splits = search_term.split(" ")
            logger.debug(f"Failed to split '{search_term}', falling back to {splits}")
            return splits

    def filter_data_by_query(self, query: str, data: list[str]) -> list[str]:
        """Filter the ``data``-list by the ``query``.

        Args:
            query: The query to filter by
            data: The list to filter on

        Returns:
            All entries in the list containing the query.

        """

        def contains_all_words(words: list[str], element: str) -> bool:
            return all(word.lower() in os.path.basename(element).lower() for word in words)

        splitquery = Source.split_search_term(query)

        return [element for element in data if contains_all_words(splitquery, element)]

    async def get_file_list(self) -> list[str]:
        """Gather a list of all files belonging to the source.

        This list will be send to the server. When the server searches, this
        list will be searched.

        Returns:
            An empty list.

        """
        return []


available_sources: dict[str, type[Source]] = {}
