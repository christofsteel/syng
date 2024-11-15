"""
Abstract class for sources.

Also defines the dictionary of available sources. Each source should add itself
to this dictionary in its module.
"""

from __future__ import annotations

import asyncio
import os.path
import shlex
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from itertools import zip_longest
from traceback import print_exc
from typing import Any
from typing import Optional
from typing import Tuple
from typing import Type
from abc import ABC, abstractmethod


from ..log import logger
from ..entry import Entry
from ..result import Result
from ..config import BoolOption, ConfigOption

# logger: logging.Logger = logging.getLogger(__name__)


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


class Source(ABC):
    """Parentclass for all sources.

    A new source should subclass this, and at least implement
    :py:func:`Source.do_buffer`, :py:func:`Song.get_entry` and
    :py:func:`Source.get_file_list`, and set the ``source_name``
    attribute.

    Source specific tasks will be forwarded to the respective source, like:
        - Playing the audio/video
        - Buffering the audio/video
        - Searching for a query
        - Getting an entry from an identifier
        - Handling the skipping of currently played song

    Some methods of a source will be called by the server and some will be
    called by the playback client.

    Specific server methods:
    ``get_entry``, ``search``, ``add_to_config``

    Specific client methods:
    ``buffer``, ``do_buffer``, ``play``, ``skip_current``, ``ensure_playable``,
    ``get_missing_metadata``, ``get_config``

    Each source has a reference to all files, that are currently queued to
    download via the :py:attr:`Source.downloaded_files` attribute and a
    reference to a ``mpv`` process playing songs for that specific source

    :attributes: - ``downloaded_files``, a dictionary mapping
                   :py:attr:`Entry.ident` to :py:class:`DLFilesEntry`.
                 - ``player``, the reference to the ``mpv`` process, if it has
                   started
                 - ``extra_mpv_arguments``, list of arguments added to the mpv
                   instance, can be overwritten by a subclass
                 - ``source_name``, the string used to identify the source
    """

    source_name: str = ""
    config_schema: dict[str, ConfigOption[Any]] = {
        "enabled": ConfigOption(BoolOption(), "Enable this source", False)
    }

    def __init__(self, config: dict[str, Any]):
        """
        Create and initialize a new source.

        You should never try to instantiate the Source class directly, rather
        you should instantiate a subclass.

        :param config: Specific configuration for a source. See the respective
          source for documentation.
        :type config: dict[str, Any]
        """
        self.downloaded_files: defaultdict[str, DLFilesEntry] = defaultdict(DLFilesEntry)
        self._masterlock: asyncio.Lock = asyncio.Lock()
        self.player: Optional[asyncio.subprocess.Process] = None
        self._index: list[str] = config["index"] if "index" in config else []
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
        args = ["--fullscreen", *options, video] + ([f"--audio-file={audio}"] if audio else [])

        # print(f"File is {video=} and {audio=}")

        mpv_process = asyncio.create_subprocess_exec(
            "mpv",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return await mpv_process

    async def get_entry(
        self,
        performer: str,
        ident: str,
        /,
        artist: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Optional[Entry]:
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
        """
        if ident not in self._index:
            return None

        res: Result = Result.from_filename(ident, self.source_name)
        return Entry(
            ident=ident,
            source=self.source_name,
            duration=180,
            album=res.album if res.album else "Unknown",
            title=res.title if res.title else title if title else "Unknown",
            artist=res.artist if res.artist else artist if artist else "Unknown",
            performer=performer,
            incomplete_data=True,
        )

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

    async def play(self, entry: Entry, mpv_options: str) -> None:
        """
        Play the entry.

        This waits until buffering is complete and starts
        playing the entry.

        :param entry: The entry to play
        :type entry: Entry
        :param mpv_options: Extra options for the mpv player
        :type mpv_options: str
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

            extra_options = (
                (self.extra_mpv_arguments + [mpv_options])
                if mpv_options
                else self.extra_mpv_arguments
            )

            self.player = await self.play_mpv(
                self.downloaded_files[entry.ident].video,
                self.downloaded_files[entry.ident].audio,
                *extra_options,
            )
        await self.player.communicate()
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
                if word.lower() not in os.path.basename(element).lower():
                    return False
            return True

        splitquery = shlex.split(query)
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

    async def update_file_list(self) -> Optional[list[str]]:
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

    async def update_config(self) -> Optional[dict[str, Any] | list[dict[str, Any]]]:
        """
        Update the config of the source.

        This is called after the client sends its initial config to the server to
        update the config. E.g. to update the list of files, that should be send to
        the server.

        It returns None, if the config is already up to date.
        Otherwise returns the new config.

        :rtype: Optional[dict[str, Any] | list[dict[str, Any]]
        """

        logger.warning(f"{self.source_name}: updating index")
        new_index = await self.update_file_list()
        logger.warning(f"{self.source_name}: done")
        if new_index is not None:
            self._index = new_index
            chunked = zip_longest(*[iter(new_index)] * 1000, fillvalue="")
            return [{"index": list(filter(lambda x: x != "", chunk))} for chunk in chunked]
        return None

    async def get_config(self) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Return the part of the config, that should be send to the server.

        Can be either a dictionary or a list of dictionaries. If it is a
        dictionary, a single message will be send. If it is a list, one message
        will be send for each entry in the list.

        By default this is the list of files handled by the source, split into
        chunks of 1000 filenames. This list is cached internally, so it does
        not need to be rebuild, when the client reconnects.

        But this can be any other values, as long as the respective source can
        handle that data.

        :return: The part of the config, that should be sended to the server.
        :rtype: dict[str, Any] | list[dict[str, Any]]
        """
        if not self._index:
            self._index = []
            logger.warning(f"{self.source_name}: generating index")
            self._index = await self.get_file_list()
            logger.warning(f"{self.source_name}: done")
        chunked = zip_longest(*[iter(self._index)] * 1000, fillvalue="")
        return [{"index": list(filter(lambda x: x != "", chunk))} for chunk in chunked]

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


available_sources: dict[str, Type[Source]] = {}
