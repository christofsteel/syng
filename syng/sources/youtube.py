import asyncio
import shlex
from functools import partial
from typing import Optional, Tuple, Any

from pytube import YouTube, Search, Channel, innertube, Stream, StreamQuery

from .source import Source, available_sources
from ..entry import Entry
from ..result import Result


class YoutubeSource(Source):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.innertube_client: innertube.InnerTube = innertube.InnerTube(client="WEB")
        self.channels: list[str] = config["channels"] if "channels" in config else []
        self.tmp_dir: str = config["tmp_dir"] if "tmp_dir" in config else "/tmp/syng"
        self.max_res: int = config["max_res"] if "max_res" in config else 720
        self.start_streaming: bool = (
            config["start_streaming"] if "start_streaming" in config else False
        )

    async def get_config(self) -> dict[str, Any] | list[dict[str, Any]]:
        return {"channels": self.channels}

    async def play(self, entry: Entry) -> None:
        if self.start_streaming and not self.downloaded_files[entry.id].complete:
            print("streaming")
            self.player = await self.play_mpv(
                entry.id,
                None,
                "--script-opts=ytdl_hook-ytdl_path=yt-dlp,ytdl_hook-exclude='%.pls$'",
                f"--ytdl-format=bestvideo[height<={self.max_res}]+bestaudio/best[height<={self.max_res}]",
                "--fullscreen",
            )
            await self.player.wait()
        else:
            await super().play(entry)

    async def get_entry(self, performer: str, ident: str) -> Entry:
        def _get_entry(performer: str, url: str) -> Entry:
            yt = YouTube(url)
            return Entry(
                id=url,
                source="youtube",
                album="YouTube",
                duration=yt.length,
                title=yt.title,
                artist=yt.author,
                performer=performer,
            )

        return await asyncio.to_thread(_get_entry, performer, ident)

    def _contains_index(self, query: str, result: YouTube) -> float:
        compare_string: str = result.title.lower() + " " + result.author.lower()
        hits: int = 0
        queries: list[str] = shlex.split(query.lower())
        for word in queries:
            if word in compare_string:
                hits += 1

        return 1 - (hits / len(queries))

    async def search(self, query: str) -> list[Result]:
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

        results.sort(key=partial(self._contains_index, query))

        return [
            Result(
                id=result.watch_url,
                source="youtube",
                title=result.title,
                artist=result.author,
                album="YouTube",
            )
            for result in results
        ]

    def _yt_search(self, query: str) -> list[YouTube]:
        results: Optional[list[YouTube]] = Search(f"{query} karaoke").results
        if results is not None:
            return results
        return []

    def _channel_search(self, query: str, channel: str) -> list[YouTube]:
        browse_id: str = Channel(f"https://www.youtube.com{channel}").channel_id
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
        ]["tabs"][-1]["expandableTabRenderer"]["content"]["sectionListRenderer"][
            "contents"
        ]

        list_of_videos: list[YouTube] = []
        for item in items:
            try:
                if (
                    "itemSectionRenderer" in item
                    and "videoRenderer" in item["itemSectionRenderer"]["contents"][0]
                ):
                    yt_url: str = (
                        "https://youtube.com/watch?v="
                        + item["itemSectionRenderer"]["contents"][0]["videoRenderer"][
                            "videoId"
                        ]
                    )
                    author: str = item["itemSectionRenderer"]["contents"][0][
                        "videoRenderer"
                    ]["ownerText"]["runs"][0]["text"]
                    title: str = item["itemSectionRenderer"]["contents"][0][
                        "videoRenderer"
                    ]["title"]["runs"][0]["text"]
                    yt: YouTube = YouTube(yt_url)
                    yt.author = author
                    yt.title = title
                    list_of_videos.append(yt)

            except KeyError:
                pass
        return list_of_videos

    async def doBuffer(self, entry: Entry) -> Tuple[str, Optional[str]]:
        yt: YouTube = YouTube(entry.id)

        streams: StreamQuery = await asyncio.to_thread(lambda: yt.streams)

        video_streams: StreamQuery = streams.filter(
            type="video",
            custom_filter_functions=[lambda s: int(s.resolution[:-1]) <= self.max_res],
        )
        audio_streams: StreamQuery = streams.filter(only_audio=True)

        best_video_stream: Stream = sorted(
            video_streams,
            key=lambda s: int(s.resolution[:-1]) + (1 if s.is_progressive else 0),
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
