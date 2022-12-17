"""
Construct the YouTube source.

If available, downloading will be performed via yt-dlp, if not, pytube will be
used.

Adds it to the ``available_sources`` with the name ``youtube``.
"""
import asyncio
import shlex
from functools import partial
from typing import Any
from typing import Optional
from typing import Tuple

from pytube import Channel
from pytube import innertube
from pytube import Search
from pytube import Stream
from pytube import StreamQuery
from pytube import YouTube

try:
    from yt_dlp import YoutubeDL

    USE_YT_DLP = True
except ImportError:
    USE_YT_DLP = False

from ..entry import Entry
from ..result import Result
from .source import available_sources
from .source import Source


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

    # pylint: disable=too-many-instance-attributes

    def __init__(self, config: dict[str, Any]):
        """Create the source."""
        super().__init__(config)
        self.source_name = "youtube"

        self.innertube_client: innertube.InnerTube = innertube.InnerTube(
            client="WEB"
        )
        self.channels: list[str] = (
            config["channels"] if "channels" in config else []
        )
        self.tmp_dir: str = (
            config["tmp_dir"] if "tmp_dir" in config else "/tmp/syng"
        )
        self.max_res: int = config["max_res"] if "max_res" in config else 720
        self.start_streaming: bool = (
            config["start_streaming"] if "start_streaming" in config else False
        )
        self.formatstring = (
            f"bestvideo[height<={self.max_res}]+"
            f"bestaudio/best[height<={self.max_res}]"
        )
        if USE_YT_DLP:
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
        if (
            self.start_streaming
            and not self.downloaded_files[entry.ident].complete
        ):
            self.player = await self.play_mpv(
                entry.ident,
                None,
                "--script-opts=ytdl_hook-ytdl_path=yt-dlp,"
                "ytdl_hook-exclude='%.pls$'",
                f"--ytdl-format={self.formatstring}",
                "--fullscreen",
            )
            await self.player.wait()
        else:
            await super().play(entry)

    async def get_entry(self, performer: str, ident: str) -> Entry:
        """
        Create an :py:class:`syng.entry.Entry` for the identifier.

        The identifier should be a youtube url. An entry is created with
        all available metadata for the video.

        :param performer: The persong singing.
        :type performer: str
        :param ident: A url to a YouTube video.
        :type ident: str
        :return: An entry with the data.
        :rtype: Entry
        """

        def _get_entry(performer: str, url: str) -> Entry:
            yt_song = YouTube(url)
            return Entry(
                ident=url,
                source="youtube",
                album="YouTube",
                duration=yt_song.length,
                title=yt_song.title,
                artist=yt_song.author,
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
            compare_string: str = (
                result.title.lower() + " " + result.author.lower()
            )
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
            search_result
            for yt_result in results_lists
            for search_result in yt_result
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
        results: Optional[list[YouTube]] = Search(f"{query} karaoke").results
        if results is not None:
            return results
        return []

    # pylint: disable=protected-access
    def _channel_search(self, query: str, channel: str) -> list[YouTube]:
        """
        Search a channel for a query.

        A lot of black Magic happens here.
        """
        browse_id: str = Channel(
            f"https://www.youtube.com{channel}"
        ).channel_id
        endpoint: str = f"{self.innertube_client.base_url}/browse"

        data: dict[str, str] = {
            "query": query,
            "browseId": browse_id,
            "params": "EgZzZWFyY2g%3D",
        }
        data.update(self.innertube_client.base_data)
        results: dict[str, Any] = self.innertube_client._call_api(
            endpoint, self.innertube_client.base_params, data
        )
        items: list[dict[str, Any]] = results["contents"][
            "twoColumnBrowseResultsRenderer"
        ]["tabs"][-1]["expandableTabRenderer"]["content"][
            "sectionListRenderer"
        ][
            "contents"
        ]

        list_of_videos: list[YouTube] = []
        for item in items:
            try:
                if (
                    "itemSectionRenderer" in item
                    and "videoRenderer"
                    in item["itemSectionRenderer"]["contents"][0]
                ):
                    yt_url: str = (
                        "https://youtube.com/watch?v="
                        + item["itemSectionRenderer"]["contents"][0][
                            "videoRenderer"
                        ]["videoId"]
                    )
                    author: str = item["itemSectionRenderer"]["contents"][0][
                        "videoRenderer"
                    ]["ownerText"]["runs"][0]["text"]
                    title: str = item["itemSectionRenderer"]["contents"][0][
                        "videoRenderer"
                    ]["title"]["runs"][0]["text"]
                    yt_song: YouTube = YouTube(yt_url)
                    yt_song.author = author
                    yt_song.title = title
                    list_of_videos.append(yt_song)

            except KeyError:
                pass
        return list_of_videos

    async def _buffer_with_yt_dlp(
        self, entry: Entry
    ) -> Tuple[str, Optional[str]]:
        """
        Download the video using yt-dlp.

        Yt-dlp automatically merges the audio and video, so only the video
        location exists, the return value for the audio part will always be
        ``None``.

        :param entry: The entry to download.
        :type entry: Entry
        :return: The location of the video file and ```None```
        :rtype: Tuple[str, Optional[str]]
        """
        info = await asyncio.to_thread(self._yt_dlp.extract_info, entry.ident)
        combined_path = info["requested_downloads"][0]["filepath"]
        return combined_path, None

    async def do_buffer(self, entry: Entry) -> Tuple[str, Optional[str]]:
        """
        Download the video.

        Downloads the highest quality stream respecting the ``max_res``.
        For higher resolution videos (1080p and above), YouTube will give you
        the video and audio seperatly. If that is the case, both will be
        downloaded.

        If yt-dlp is installed it will be used, otherwise pytube will be used.


        :param entry: The entry to download.
        :type entry: Entry
        :return: The location of the video file and (if applicable) the
          location of the audio file.
        :rtype: Tuple[str, Optional[str]]
        """
        if USE_YT_DLP:
            return await self._buffer_with_yt_dlp(entry)

        yt_song: YouTube = YouTube(entry.ident)

        streams: StreamQuery = await asyncio.to_thread(lambda: yt_song.streams)

        video_streams: StreamQuery = streams.filter(
            type="video",
            custom_filter_functions=[
                lambda s: int(s.resolution[:-1]) <= self.max_res
            ],
        )
        audio_streams: StreamQuery = streams.filter(only_audio=True)

        best_video_stream: Stream = sorted(
            video_streams,
            key=lambda s: int(s.resolution[:-1])
            + (1 if s.is_progressive else 0),
        )[-1]
        best_audio_stream: Stream = sorted(
            audio_streams, key=lambda s: int(s.abr[:-4])
        )[-1]

        audio: Optional[str] = (
            await asyncio.to_thread(
                best_audio_stream.download,
                output_path=self.tmp_dir,
                filename_prefix="audio-",
            )
            if best_video_stream.is_adaptive
            else None
        )

        video: str = await asyncio.to_thread(
            best_video_stream.download,
            output_path=self.tmp_dir,
        )

        return video, audio


available_sources["youtube"] = YoutubeSource
