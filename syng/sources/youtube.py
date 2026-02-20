"""Construct the YouTube source.

This source uses yt-dlp to search and download videos from YouTube.

Adds it to the ``available_sources`` with the name ``youtube``.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
from dataclasses import dataclass, field
from functools import partial
from typing import Any
from urllib.parse import urlencode

from platformdirs import user_cache_dir
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from syng.config import SourceConfig
from syng.entry import Entry
from syng.result import Result
from syng.sources.source import (
    Source,
    available_sources,
)


class YouTube:
    """A minimal compatibility layer for the YouTube object of pytube, implemented via yt-dlp."""

    def __init__(self, url: str | None = None, info: dict[str, Any] | None = None) -> None:
        """Construct a YouTube object from a url.

        If the url is already in the cache, the object is constructed from the
        cache. Otherwise yt-dlp is used to extract the information.

        Args:
            url: The url of the video. If ``None`` an empy object is constructed.
            info: Cache for the url

        Raises:
            RuntimeError: If the information cannot be loaded from YouTube

        """
        self._title: str | None
        self._author: str | None

        if url is not None:
            try:
                if info is not None:
                    self._infos = info
                else:
                    self._infos = YoutubeDL({"quiet": True}).extract_info(url, download=False)
            except DownloadError:
                self.length = 300
                self._title = None
                self._author = None
                self.watch_url = url
                return
            if self._infos is None:
                raise RuntimeError(f'Extraction not possible for "{url}"')
            self.length = int(self._infos["duration"])
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
        """The title of the video."""
        if self._title is None:
            return ""
        return self._title

    @property
    def author(self) -> str:
        """The author of the video."""
        if self._author is None:
            return ""
        return self._author

    @classmethod
    def from_result(cls, search_result: dict[str, Any]) -> YouTube:
        """Construct a YouTube object from yt-dlp search results.

        Args:
            search_result: The search result from yt-dlp.

        Returns:
            ``YouTube`` object from the search results.

        """
        url = search_result["url"]
        return cls(url, info=search_result)


class Search:
    """A minimal compatibility layer for the Search object of pytube, implemented via yt-dlp."""

    def __init__(self, query: str, channel: str | None = None) -> None:
        """Construct a Search object from a query and an optional channel.

        Uses yt-dlp to search for the query.

        If no channel is given, the search is done on the whole of YouTube.

        Args:
            query: The query to search for.
            channel: Optionally, the channel to search in.

        """
        sp = "EgIQAfABAQ=="  # This is a magic string, that tells youtube to search for videos
        if channel is None:
            query_url = (
                f"https://youtube.com/results?{urlencode({'search_query': query, 'sp': sp})}"
            )
        else:
            if channel[0] == "/":
                channel = channel[1:]
            query_url = (
                f"https://www.youtube.com/{channel}/search?{urlencode({'query': query, 'sp': sp})}"
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
                with contextlib.suppress(KeyError):
                    self.results.append(YouTube.from_result(r))


class Resolution(enum.Enum):
    """Target resolution of a YouTube Video."""

    RES144 = 144
    RES360 = 360
    RES720 = 720
    RES1080 = 1080
    RES2160 = 2160


@dataclass
class YouTubeConfig(SourceConfig):
    """Configuration object for YouTubeSources.

    Attributes:
        enabled: Enable this source
        channels: A list of all channel this source should search in.
            Examples are ``/c/CCKaraoke`` or ``/channel/UCwTRjvjVge51X-ILJ4i22ew``
        tmp_dir: The folder, where temporary files are stored. Default is ``${XDG_CACHE_DIR}/syng``.
        max_res: The highest video resolution, that should be downloaded/streamed. Default is 720.
        start_streaming: If set to ``True``, the client starts streaming the video, if buffering was
            not completed. Needs the ``yt-dlp`` binary installed. Default is False.
        search_suffix: A string that is appended to the search query. Default is "karaoke".
        max_duration: The maximum duration of a video in seconds. A value of 0 disables this.
            Default is 1800.

    """

    enabled: bool = field(default=True, metadata={"desc": "Enable this source"})
    channels: list[str] = field(
        default_factory=list, metadata={"desc": "A list of channels\nto search in", "server": True}
    )
    tmp_dir: str = field(
        default=user_cache_dir("syng"),
        metadata={"desc": "Folder for\ntemporary download", "semantic": "folder"},
    )
    max_res: Resolution = field(
        default=Resolution.RES720, metadata={"desc": "Maximum resolution\nto download"}
    )
    start_streaming: bool = field(
        default=False, metadata={"desc": "Start streaming if\ndownload is not complete"}
    )
    search_suffix: str = field(
        default="karaoke",
        metadata={"desc": "A string that is appended\nto each search query", "server": True},
    )
    max_duration: int = field(
        default=1800,
        metadata={
            "desc": "The maximum duration\nof a video in seconds\nA value of 0 disables this",
            "server": True,
        },
    )


@dataclass
class YoutubeSource(Source):
    """A source for playing karaoke files from YouTube.

    Attributes:
        config: ``YouTubeConfig`` object.

    """

    config: YouTubeConfig

    source_name = "youtube"

    def __post_init__(self) -> None:
        """Initialize the YoutubeSource."""
        super().__post_init__()

        self.formatstring = (
            f"bestvideo[height<={self.config.max_res.value}]+"
            f"bestaudio/best[height<={self.config.max_res.value}]"
        )
        self.extra_mpv_options = {"ytdl-format": self.formatstring}
        self._yt_dlp = YoutubeDL(
            params={
                "paths": {"home": self.config.tmp_dir},
                "format": self.formatstring,
                "quiet": True,
            }
        )

    async def ensure_playable(self, entry: Entry) -> tuple[str, str | None]:
        """Ensure that the entry is playable.

        If the entry is not yet downloaded, download it.
        If start_streaming is set, start streaming immediatly.

        Args:
            entry: The entry to download.

        Raises:
            ValueError: if video exceeds the configured maximum duration.

        Returns:
            Path to the video file and ``None``, since the audio track is already included in the
            video.

        """
        if entry.incomplete_data:
            meta_info = await self.get_missing_metadata(entry)
            entry.update(**meta_info)

        if 0 < self.config.max_duration < entry.duration:
            raise ValueError(f"Video {entry.ident} too long.")

        if self.config.start_streaming and not self.downloaded_files[entry.ident].complete:
            return entry.ident, None

        return await super().ensure_playable(entry)

    async def get_entry(
        self,
        performer: str,
        ident: str,
        collab_mode: str | None,
        /,
        artist: str | None = None,
        title: str | None = None,
    ) -> Entry | None:
        """Create an :py:class:`syng.entry.Entry` for the identifier.

        The identifier should be a youtube url. An entry is created with
        all available metadata for the video.

        Args:
            performer: The person singing.
            ident: A url to a YouTube video.
            collab_mode: The collaboration mode
            artist: Channel of the video
            title: Title of the video

        Returns:
            An entry with the data.

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
            collab_mode=collab_mode,
        )

    async def search(self, query: str) -> list[Result]:
        """Search YouTube and the configured channels for the query.

        The first results are the results of the configured channels. The next
        results are the results from youtube as a whole, a configurable suffix
        is appended to the search query (default is "karaoke").

        All results are sorted by how good they match to the search query,
        respecting their original source (channel or YouTube as a whole).

        All searching is done concurrently.

        Args:
            query: The query to search for

        Returns:
            A list of Results.

        """

        def _contains_index(queries: list[str], result: YouTube) -> float:
            """Calculate a score for the result.

            The score is the ratio of how many words of the query are in the
            title and author of the result.

            Args:
                queries: The query to search for, seperated by chunks.
                result: The result to score.

            Returns:
                Score as floating point, 0 means perfect match, 1 means no matches

            """
            compare_string: str = result.title.lower() + " " + result.author.lower()
            hits: int = 0
            for word in queries:
                if word in compare_string:
                    hits += 1

            return 1 - (hits / len(queries))

        queries = Source.split_search_term(query)

        results_lists: list[list[YouTube]] = await asyncio.gather(
            *[
                asyncio.to_thread(self._channel_search, query, channel)
                for channel in self.config.channels
            ],
            asyncio.to_thread(self._yt_search, query),
        )
        results = [search_result for yt_result in results_lists for search_result in yt_result]

        results.sort(key=partial(_contains_index, queries))

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
            if self.config.max_duration == 0 or result.length <= self.config.max_duration
        ]

    def is_valid(self, entry: Entry) -> bool:
        """Check if the entry is valid.

        An entry is valid, if the video is not too long.

        Args:
            entry: The entry to check.

        Returns:
            True if the entry is valid, False otherwise.

        """
        return self.config.max_duration == 0 or entry.duration <= self.config.max_duration

    def _yt_search(self, query: str) -> list[YouTube]:
        """Search youtube as a whole.

        Adds a configurable suffix to the query.

        Args:
            query: The query to search for.

        Returns:
            A list of all results

        """
        suffix = f" {self.config.search_suffix}" if self.config.search_suffix else ""
        return Search(f"{query}{suffix}").results

    def _channel_search(self, query: str, channel: str) -> list[YouTube]:
        """Search a channel for a query.

        Adds a configurable suffix to the query.

        Args:
            query: The query to search for.
            channel: The channel to search in.

        Returns:
            A list of all results

        """
        suffix = f" {self.config.search_suffix}" if self.config.search_suffix else ""
        return Search(f"{query}{suffix}", channel).results

    async def get_missing_metadata(self, entry: Entry) -> dict[str, Any]:
        """Fill missing metadata for a given entry.

        This should happen on the playback client, to avoid banning the server.
        If the entry already has all necessary data, this returns an empty dictionary.

        Args:
            entry: The entry to fill the metadata for

        Returns:
            A dict with ``duration``, ``artist`` and ``title``, taken from YouTube, or an empty
            dict.

        """
        if entry.incomplete_data or None in (entry.artist, entry.title):
            youtube_video: YouTube = await asyncio.to_thread(YouTube, entry.ident)
            return {
                "duration": youtube_video.length,
                "artist": youtube_video.author,
                "title": youtube_video.title,
            }
        return {}

    async def do_buffer(self, entry: Entry, pos: int) -> tuple[str, str | None]:
        """Download the video.

        Downloads the highest quality stream respecting the ``max_res``.
        For higher resolution videos (1080p and above).

        Yt-dlp automatically merges the audio and video, so only the video
        location exists, the return value for the audio part will always be
        ``None``.

        If pos is 0 and start_streaming is set, no buffering is done, instead the
        youtube url is returned.

        Args:
            entry (Entry): The entry to download
            pos (int): The position of the video in the queue

        Returns:
            tuple[str, str | None]: The location of the video file and ``None`

        Raises:
            ValueError: If video length exceeds the configured maximum duration

        """
        if 0 < self.config.max_duration < entry.duration:
            raise ValueError(
                f"Video {entry.ident} too long: {entry.duration} > {self.config.max_duration}"
            )

        if pos == 0 and self.config.start_streaming:
            return entry.ident, None

        info: Any = await asyncio.to_thread(self._yt_dlp.extract_info, entry.ident)
        combined_path = info["requested_downloads"][0]["filepath"]
        return combined_path, None


available_sources["youtube"] = YoutubeSource
