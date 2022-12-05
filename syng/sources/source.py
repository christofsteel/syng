"""
Abstract class for sources.

Also defines the dictionary of available sources. Each source should add itself
to this dictionary in its module.
"""
from __future__ import annotations

import asyncio
import logging
import os.path
import shlex
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from traceback import print_exc
from typing import Any
from typing import Optional
from typing import Tuple
from typing import Type

from ..entry import Entry
from ..result import Result

logger: logging.Logger = logging.getLogger(__name__)


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
    :param failed: True if the buffering failed, False otherwise (Default is
        ``False``)
    :type failed: bool
    :param skip: True if the next Entry for this file should be skipped
        (Default is ``False``)
    :param buffer_task: Reference to the task, that downloads the files.
    :type buffer_task: Optional[asyncio.Task[Tuple[str, Optional[str]]]]
    """

    # pylint: disable=too-many-instance-attributes

    ready: asyncio.Event = field(default_factory=asyncio.Event)
    video: str = ""
    audio: Optional[str] = None
    buffering: bool = False
    complete: bool = False
    failed: bool = False
    skip: bool = False
    buffer_task: Optional[asyncio.Task[Tuple[str, Optional[str]]]] = None


class Source:
    """Parentclass for all sources.

    A new source should subclass this, and at least implement
    :py:func:`Source.get_entry`, :py:func:`Source.search` and
    :py:func:`Source.do_buffer`. The sources will be shared between the server
    and the playback client.

    Source specific tasks will be forwarded to the respective source, like:
        - Playing the audio/video
        - Buffering the audio/video
        - Searching for a query
        - Getting an entry from an identifier
        - Handling the skipping of currently played song

    Each source has a reference to all files, that are currently queued to
    download via the :py:attr:`Source.downloaded_files` attribute and a
    reference to a ``mpv`` process playing songs for that specific source

    :attributes: - ``downloaded_files``, a dictionary mapping
                   :py:attr:`Entry.ident` to :py:class:`DLFilesEntry`.
                 - ``player``, the reference to the ``mpv`` process, if it has
                   started
                 - ``extra_mpv_arguments``, list of arguments added to the mpv
                   instance, can be overwritten by a subclass
    """

    def __init__(self, _: dict[str, Any]):
        """
        Create and initialize a new source.

        You should never try to instantiate the Source class directly, rather
        you should instantiate a subclass.

        :param _: Specific configuration for a Soure, ignored in the base
            class
        :type _: dict[str, Any]
        """
        self.downloaded_files: defaultdict[str, DLFilesEntry] = defaultdict(
            DLFilesEntry
        )
        self._masterlock: asyncio.Lock = asyncio.Lock()
        self.player: Optional[asyncio.subprocess.Process] = None
        self.extra_mpv_arguments: list[str] = []
        self._skip_next = False

    @staticmethod
    async def play_mpv(
        video: str, audio: Optional[str], /, *options: str
    ) -> asyncio.subprocess.Process:
        """
        Create a mpv process to play a song in full screen.

        :param video: Location of the video part.
        :type video: str
        :param audio: Location of the audio part, if it exists.
        :type audio: Optional[str]
        :param options: Extra arguments forwarded to the mpv player
        :type options: str
        :returns: An async reference to the process
        :rtype: asyncio.subprocess.Process
        """
        args = ["--fullscreen", *options, video] + (
            [f"--audio-file={audio}"] if audio else []
        )

        mpv_process = asyncio.create_subprocess_exec(
            "mpv",
            *args,
            stdout=asyncio.subprocess.PIPE,
        )
        return await mpv_process

    async def get_entry(self, performer: str, ident: str) -> Entry:
        """
        Create an :py:class:`syng.entry.Entry` from a given identifier.

        Abstract, needs to be implemented by subclass.

        :param performer: The performer of the song
        :type performer: str
        :param ident: Unique identifier of the song.
        :type ident: str
        :returns: New entry for the identifier.
        :rtype: Entry
        """
        raise NotImplementedError

    async def search(self, query: str) -> list[Result]:
        """
        Search the songs from the source for a query.

        Abstract, needs to be implemented by subclass.

        :param query: The query to search for
        :type query: str
        :returns: A list of Results containing the query.
        :rtype: list[Result]
        """
        raise NotImplementedError

    async def do_buffer(self, entry: Entry) -> Tuple[str, Optional[str]]:
        """
        Source specific part of buffering.

        This should asynchronous download all required files to play the entry,
        and return the location of the video and audio file. If the audio is
        included in the video file, the location for the audio file should be
        `None`.

        Abstract, needs to be implemented by subclass.

        :param entry: The entry to buffer
        :type entry: Entry
        :returns: A Tuple of the locations for the video and the audio file.
        :rtype: Tuple[str, Optional[str]]
        """
        raise NotImplementedError

    async def buffer(self, entry: Entry) -> None:
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
        :rtype: None
        """
        async with self._masterlock:
            if self.downloaded_files[entry.ident].buffering:
                return
            self.downloaded_files[entry.ident].buffering = True

        try:
            buffer_task = asyncio.create_task(self.do_buffer(entry))
            self.downloaded_files[entry.ident].buffer_task = buffer_task
            video, audio = await buffer_task

            self.downloaded_files[entry.ident].video = video
            self.downloaded_files[entry.ident].audio = audio
            self.downloaded_files[entry.ident].complete = True
        except Exception:  # pylint: disable=broad-except
            print_exc()
            logger.error("Buffering failed for %s", entry)
            self.downloaded_files[entry.ident].failed = True

        self.downloaded_files[entry.ident].ready.set()

    async def play(self, entry: Entry) -> None:
        """
        Play the entry.

        This waits until buffering is complete and starts
        playing the entry.

        :param entry: The entry to play
        :type entry: Entry
        :rtype: None
        """
        await self.ensure_playable(entry)

        if self.downloaded_files[entry.ident].failed:
            del self.downloaded_files[entry.ident]
            return

        async with self._masterlock:
            if self._skip_next:
                self._skip_next = False
                entry.skip = True
                return

            self.player = await self.play_mpv(
                self.downloaded_files[entry.ident].video,
                self.downloaded_files[entry.ident].audio,
                *self.extra_mpv_arguments,
            )
        await self.player.wait()
        self.player = None
        if self._skip_next:
            self._skip_next = False
            entry.skip = True

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

            if self.player is not None:
                self.player.kill()

    async def ensure_playable(self, entry: Entry) -> None:
        """
        Guaranties that the given entry can be played.

        First start buffering, then wait for the buffering to end.

        :param entry: The entry to ensure playback for.
        :type entry: Entry
        :rtype: None
        """
        await self.buffer(entry)
        await self.downloaded_files[entry.ident].ready.wait()

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

    def filter_data_by_query(self, query: str, data: list[str]) -> list[str]:
        """
        Filter the ``data``-list by the ``query``.

        :param query: The query to filter
        :type query: str
        :param data: The list to filter
        :type data: list[str]
        :return: All entries in the list containing the query.
        :rtype: list[str]
        """

        def contains_all_words(words: list[str], element: str) -> bool:
            for word in words:
                if not word.lower() in os.path.basename(element).lower():
                    return False
            return True

        splitquery = shlex.split(query)
        return [
            element
            for element in data
            if contains_all_words(splitquery, element)
        ]

    async def get_config(self) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Return the part of the config, that should be send to the server.

        Can be either a dictionary or a list of dictionaries. If it is a
        dictionary, a single message will be send. If it is a list, one message
        will be send for each entry in the list.

        Abstract, needs to be implemented by subclass.

        :return: The part of the config, that should be sended to the server.
        :rtype: dict[str, Any] | list[dict[str, Any]]
        """
        raise NotImplementedError

    def add_to_config(self, config: dict[str, Any]) -> None:
        """
        Add the config to the own config.

        This is called on the server, if :py:func:`Source.get_config` returns a
        list.

        :param config: The part of the config to add.
        :type config: dict[str, Any]
        :rtype: None
        """


available_sources: dict[str, Type[Source]] = {}
