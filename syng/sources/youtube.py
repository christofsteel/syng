"""
Construct the YouTube source.

This source uses yt-dlp to search and download videos from YouTube.

Adds it to the ``available_sources`` with the name ``youtube``.
"""

from __future__ import annotations

import asyncio
import shlex
from functools import partial
from urllib.parse import urlencode
from typing import Any, Optional, Tuple

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from platformdirs import user_cache_dir


from ..entry import Entry
from ..result import Result
from .source import Source, available_sources
from ..config import BoolOption, ChoiceOption, FolderOption, ListStrOption, ConfigOption


class YouTube:
    """
    A minimal compatibility layer for the YouTube object of pytube, implemented via yt-dlp
    """

    def __init__(self, url: Optional[str] = None):
        """
        Construct a YouTube object from a url.

        If the url is already in the cache, the object is constructed from the
        cache. Otherwise yt-dlp is used to extract the information.

        :param url: The url of the video.
        :type url: Optional[str]
        """
        self._title: Optional[str]
        self._author: Optional[str]

        if url is not None:
            try:
                self._infos = YoutubeDL({"quiet": True}).extract_info(url, download=False)
            except DownloadError:
                self.length = 300
                self._title = None
                self._author = None
                self.watch_url = url
                return
            if self._infos is None:
                raise RuntimeError(f'Extraction not possible for "{url}"')
            self.length = self._infos["duration"]
            self._title = self._infos["title"]
            self._author = self._infos["channel"]
            self.watch_url = url
        else:
            self.length = 0
            self._title = ""
            self.channel = ""
            self._author = ""
            self.watch_url = ""

    @property
    def title(self) -> str:
        """
        The title of the video.

        :return: The title of the video.
        :rtype: str
        """
        if self._title is None:
            return ""
        return self._title

    @property
    def author(self) -> str:
        """
        The author of the video.

        :return: The author of the video.
        :rtype: str
        """
        if self._author is None:
            return ""
        return self._author

    @classmethod
    def from_result(cls, search_result: dict[str, Any]) -> YouTube:
        """
        Construct a YouTube object from yt-dlp search results.

        Updates the cache with the url and the metadata.

        :param search_result: The search result from yt-dlp.
        :type search_result: dict[str, Any]
        """
        url = search_result["url"]
        # cls.__cache__[url] = {
        #     "duration": int(search_result["duration"]),
        #     "title": search_result["title"],
        #     "channel": search_result["channel"],
        #     "url": url,
        # }
        return cls(url)


class Search:
    """
    A minimal compatibility layer for the Search object of pytube, implemented via yt-dlp
    """

    # pylint: disable=too-few-public-methods
    def __init__(self, query: str, channel: Optional[str] = None):
        """
        Construct a Search object from a query and an optional channel.

        Uses yt-dlp to search for the query.

        If no channel is given, the search is done on the whole of YouTube.

        :param query: The query to search for.
        :type query: str
        :param channel: The channel to search in.
        :type channel: Optional[str]
        """
        sp = "EgIQAfABAQ=="  # This is a magic string, that tells youtube to search for videos
        if channel is None:
            query_url = f"https://youtube.com/results?{urlencode({'search_query': query, 'sp':sp})}"
        else:
            if channel[0] == "/":
                channel = channel[1:]
            query_url = (
                f"https://www.youtube.com/{channel}/search?{urlencode({'query': query, 'sp':sp})}"
            )

        results = YoutubeDL(
            {
                "extract_flat": True,
                "quiet": True,
                "playlist_items": ",".join(map(str, range(1, 51))),
            }
        ).extract_info(
            query_url,
            download=False,
        )
        self.results = []
        if results is not None:
            filtered_entries = filter(lambda entry: "short" not in entry["url"], results["entries"])

            for r in filtered_entries:
                try:
                    self.results.append(YouTube.from_result(r))
                except KeyError:
                    pass


class YoutubeSource(Source):
    """A source for playing karaoke files from YouTube.

    Config options are:
        - ``channels``: A list of all channel this source should search in.
          Examples are ``/c/CCKaraoke`` or
          ``/channel/UCwTRjvjVge51X-ILJ4i22ew``
        - ``tmp_dir``: The folder, where temporary files are stored. Default
          is ``/tmp/syng``
        - ``max_res``: The highest video resolution, that should be
          downloaded/streamed. Default is 720.
        - ``start_streaming``: If set to ``True``, the client starts streaming
          the video, if buffering was not completed. Needs ``youtube-dl`` or
          ``yt-dlp``. Default is False.
    """

    source_name = "youtube"
    config_schema = Source.config_schema | {
        "enabled": ConfigOption(BoolOption(), "Enable this source", True),
        "channels": ConfigOption(ListStrOption(), "A list channels\nto search in", []),
        "tmp_dir": ConfigOption(
            FolderOption(), "Folder for\ntemporary download", user_cache_dir("syng")
        ),
        "max_res": ConfigOption(
            ChoiceOption(["144", "240", "360", "480", "720", "1080", "2160"]),
            "Maximum resolution\nto download",
            "720",
        ),
        "start_streaming": ConfigOption(
            BoolOption(),
            "Start streaming if\ndownload is not complete",
            False,
        ),
    }

    # pylint: disable=too-many-instance-attributes
    def __init__(self, config: dict[str, Any]):
        """
        Create the YouTube source.

        :param config: The configuration for the source.
        :type config: dict[str, Any]
        """
        super().__init__(config)

        self.channels: list[str] = config["channels"] if "channels" in config else []
        self.tmp_dir: str = config["tmp_dir"] if "tmp_dir" in config else "/tmp/syng"
        try:
            self.max_res: int = int(config["max_res"])
        except (ValueError, KeyError):
            self.max_res = 720
        self.start_streaming: bool = (
            config["start_streaming"] if "start_streaming" in config else False
        )
        self.formatstring = (
            f"bestvideo[height<={self.max_res}]+" f"bestaudio/best[height<={self.max_res}]"
        )
        self._yt_dlp = YoutubeDL(
            params={
                "paths": {"home": self.tmp_dir},
                "format": self.formatstring,
                "quiet": True,
            }
        )

    async def get_config(self) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Return the list of channels in a dictionary with key ``channels``.

        :return: see above
        :rtype: dict[str, Any]]
        """
        return {"channels": self.channels}

    async def play(self, entry: Entry, mpv_options: str) -> None:
        """
        Play the given entry.

        If ``start_streaming`` is set and buffering is not yet done, starts
        immediatly and forwards the url to ``mpv``.

        Otherwise wait for buffering and start playing.

        :param entry: The entry to play.
        :type entry: Entry
        :param mpv_options: The options to pass to ``mpv``.
        :type mpv_options: str
        :rtype: None
        """
        if self.start_streaming and not self.downloaded_files[entry.ident].complete:
            self.player = await self.play_mpv(
                entry.ident,
                None,
                "--script-opts=ytdl_hook-ytdl_path=yt-dlp,ytdl_hook-exclude='%.pls$'",
                f"--ytdl-format={self.formatstring}",
                "--fullscreen",
                mpv_options,
            )
            await self.player.communicate()
            await self.player.wait()
        else:
            await super().play(entry, mpv_options)

    async def get_entry(
        self,
        performer: str,
        ident: str,
        /,
        artist: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Optional[Entry]:
        """
        Create an :py:class:`syng.entry.Entry` for the identifier.

        The identifier should be a youtube url. An entry is created with
        all available metadata for the video.

        :param performer: The person singing.
        :type performer: str
        :param ident: A url to a YouTube video.
        :type ident: str
        :return: An entry with the data.
        :rtype: Optional[Entry]
        """

        return Entry(
            ident=ident,
            source="youtube",
            duration=180,
            album="YouTube",
            title=title,
            artist=artist,
            performer=performer,
            incomplete_data=True,
        )

    async def search(self, query: str) -> list[Result]:
        """
        Search YouTube and the configured channels for the query.

        The first results are the results of the configured channels. The next
        results are the results from youtube as a whole, but the term "Karaoke"
        is appended to the search query.

        All results are sorted by how good they match to the search query,
        respecting their original source (channel or YouTube as a whole).

        All searching is done concurrently.

        :param query: The query to search for
        :type query: str
        :return: A list of Results.
        :rtype: list[Result]
        """

        def _contains_index(query: str, result: YouTube) -> float:
            """
            Calculate a score for the result.

            The score is the ratio of how many words of the query are in the
            title and author of the result.

            :param query: The query to search for.
            :type query: str
            :param result: The result to score.
            :type result: YouTube
            """
            compare_string: str = result.title.lower() + " " + result.author.lower()
            hits: int = 0
            queries: list[str] = shlex.split(query.lower())
            for word in queries:
                if word in compare_string:
                    hits += 1

            return 1 - (hits / len(queries))

        results: list[YouTube] = []
        results_lists: list[list[YouTube]] = await asyncio.gather(
            *[asyncio.to_thread(self._channel_search, query, channel) for channel in self.channels],
            asyncio.to_thread(self._yt_search, query),
        )
        results = [search_result for yt_result in results_lists for search_result in yt_result]

        results.sort(key=partial(_contains_index, query))

        return [
            Result(
                ident=result.watch_url,
                source="youtube",
                title=result.title,
                artist=result.author,
                album="YouTube",
                duration=str(result.length),
            )
            for result in results
        ]

    def _yt_search(self, query: str) -> list[YouTube]:
        """Search youtube as a whole.

        Adds "karaoke" to the query.
        """
        return Search(f"{query} karaoke").results

    def _channel_search(self, query: str, channel: str) -> list[YouTube]:
        """
        Search a channel for a query.

        A lot of black Magic happens here.
        """
        return Search(f"{query} karaoke", channel).results

    async def get_missing_metadata(self, entry: Entry) -> dict[str, Any]:
        """
        Video metadata should be read on the client to avoid banning
        the server.
        """
        if entry.incomplete_data:
            print(f"Looking up {entry.ident}")
            youtube_video: YouTube = await asyncio.to_thread(YouTube, entry.ident)
            return {
                "duration": youtube_video.length,
                "artist": youtube_video.author,
                "title": youtube_video.title,
            }
        return {}

    async def do_buffer(self, entry: Entry) -> Tuple[str, Optional[str]]:
        """
        Download the video.

        Downloads the highest quality stream respecting the ``max_res``.
        For higher resolution videos (1080p and above).

        Yt-dlp automatically merges the audio and video, so only the video
        location exists, the return value for the audio part will always be
        ``None``.

        :param entry: The entry to download.
        :type entry: Entry
        :return: The location of the video file and ``None``.
        :rtype: Tuple[str, Optional[str]]
        """
        info: Any = await asyncio.to_thread(self._yt_dlp.extract_info, entry.ident)
        combined_path = info["requested_downloads"][0]["filepath"]
        return combined_path, None


available_sources["youtube"] = YoutubeSource
