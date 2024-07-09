"""
Construct the YouTube source.

If available, downloading will be performed via yt-dlp, if not, pytube will be
used.

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

from ..entry import Entry
from ..result import Result
from .source import Source, available_sources


class YouTube:
    """
    A minimal compatibility layer for the YouTube object of pytube, implemented via yt-dlp
    """

    __cache__: dict[str, Any] = (
        {}
    )  # TODO: this may grow fast... but atm it fixed youtubes anti bot measures

    def __init__(self, url: Optional[str] = None):
        self._title: Optional[str]
        self._author: Optional[str]

        if url is not None:
            if url in YouTube.__cache__:
                self._infos = YouTube.__cache__[url]
            else:
                try:
                    self._infos = YoutubeDL({"quiet": True}).extract_info(
                        url, download=False
                    )
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
        if self._title is None:
            return ""
        else:
            return self._title

    @property
    def author(self) -> str:
        if self._author is None:
            return ""
        else:
            return self._author

    @classmethod
    def from_result(cls, search_result: dict[str, Any]) -> YouTube:
        """
        Construct a YouTube object from yt-dlp results.
        """
        url = search_result["url"]
        cls.__cache__[url] = {
            "duration": search_result["duration"],
            "title": search_result["title"],
            "channel": search_result["channel"],
            "url": url,
        }
        return cls(url)


class Search:
    """
    A minimal compatibility layer for the Search object of pytube, implemented via yt-dlp
    """

    def __init__(self, query: str, channel: Optional[str] = None):
        sp = "EgIQAfABAQ=="
        if channel is None:
            query_url = f"https://youtube.com/results?{urlencode({'search_query': query, 'sp':sp})}"
        else:
            if channel[0] == "/":
                channel = channel[1:]
            query_url = f"https://www.youtube.com/{channel}/search?{urlencode({'query': query, 'sp':sp})}"

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
            filtered_entries = filter(
                lambda entry: "short" not in entry["url"], results["entries"]
            )

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
        "channels": (list, "A list channels\nto search in", []),
        "tmp_dir": (str, "Folder for\ntemporary download", "/tmp/syng"),
        "max_res": (int, "Maximum resolution\nto download", 720),
        "start_streaming": (
            bool,
            "Start streaming if\ndownload is not complete",
            False,
        ),
    }

    # pylint: disable=too-many-instance-attributes
    def __init__(self, config: dict[str, Any]):
        """Create the source."""
        super().__init__(config)

        self.channels: list[str] = config["channels"] if "channels" in config else []
        self.tmp_dir: str = config["tmp_dir"] if "tmp_dir" in config else "/tmp/syng"
        self.max_res: int = config["max_res"] if "max_res" in config else 720
        self.start_streaming: bool = (
            config["start_streaming"] if "start_streaming" in config else False
        )
        self.formatstring = (
            f"bestvideo[height<={self.max_res}]+"
            f"bestaudio/best[height<={self.max_res}]"
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

    async def play(self, entry: Entry) -> None:
        """
        Play the given entry.

        If ``start_streaming`` is set and buffering is not yet done, starts
        immediatly and forwards the url to ``mpv``.

        Otherwise wait for buffering and start playing.

        :param entry: The entry to play.
        :type entry: Entry
        :rtype: None
        """
        if self.start_streaming and not self.downloaded_files[entry.ident].complete:
            self.player = await self.play_mpv(
                entry.ident,
                None,
                "--script-opts=ytdl_hook-ytdl_path=yt-dlp,ytdl_hook-exclude='%.pls$'",
                f"--ytdl-format={self.formatstring}",
                "--fullscreen",
            )
            await self.player.wait()
        else:
            await super().play(entry)

    async def get_entry(self, performer: str, ident: str) -> Optional[Entry]:
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

        def _get_entry(performer: str, url: str) -> Optional[Entry]:
            yt_song = YouTube(url)
            try:
                length = yt_song.length
            except TypeError:
                length = 180
            return Entry(
                ident=url,
                source="youtube",
                album="YouTube",
                duration=length,
                title=yt_song._title,
                artist=yt_song._author,
                performer=performer,
            )

        return await asyncio.to_thread(_get_entry, performer, ident)

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
            compare_string: str = result.title.lower() + " " + result.author.lower()
            hits: int = 0
            queries: list[str] = shlex.split(query.lower())
            for word in queries:
                if word in compare_string:
                    hits += 1

            return 1 - (hits / len(queries))

        results: list[YouTube] = []
        results_lists: list[list[YouTube]] = await asyncio.gather(
            *[
                asyncio.to_thread(self._channel_search, query, channel)
                for channel in self.channels
            ],
            asyncio.to_thread(self._yt_search, query),
        )
        results = [
            search_result for yt_result in results_lists for search_result in yt_result
        ]

        results.sort(key=partial(_contains_index, query))

        return [
            Result(
                ident=result.watch_url,
                source="youtube",
                title=result.title,
                artist=result.author,
                album="YouTube",
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
        if entry.title is None or entry.artist is None:
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
