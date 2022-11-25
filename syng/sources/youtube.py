import asyncio
import shlex
from functools import partial
from threading import Event, Lock

from pytube import YouTube, Search, Channel, innertube

from .common import play_mpv, kill_mpv
from .source import Source, async_in_thread, available_sources
from ..entry import Entry
from ..result import Result


class YoutubeSource(Source):
    def __init__(self, config):
        super().__init__()
        self.innertube_client = innertube.InnerTube(client="WEB")
        self.channels = config["channels"] if "channels" in config else []
        self.tmp_dir = config["tmp_dir"] if "tmp_dir" in config else "/tmp/syng"
        self.player: None | asyncio.subprocess.Process = None
        self.downloaded_files = {}
        self.masterlock = Lock()

    async def get_config(self):
        return {"channels": self.channels}

    async def play(self, entry: Entry) -> None:

        if entry.uuid in self.downloaded_files and "video" in self.downloaded_files[entry.uuid]:
            print("playing locally")
            video_file = self.downloaded_files[entry.uuid]["video"]
            audio_file = self.downloaded_files[entry.uuid]["audio"]
            self.player = await play_mpv(video_file, audio_file)
        else:
            print("streaming")
            self.player = await play_mpv(
                entry.id,
                None,
                [
                    "--script-opts=ytdl_hook-ytdl_path=yt-dlp,ytdl_hook-exclude='%.pls$'",
                    "--ytdl-format=bestvideo[height<=720]+bestaudio/best[height<=720]",
                    "--fullscreen",
                ],
            )

        await self.player.wait()

    async def skip_current(self, entry) -> None:        
        await self.player.kill()

    @async_in_thread
    def get_entry(self, performer: str, url: str) -> Entry:
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

    def _contains_index(self, query, result):
        compare_string = result.title.lower() + " " + result.author.lower()
        hits = 0
        queries = shlex.split(query.lower())
        for word in queries:
            if word in compare_string:
                hits += 1

        return 1 - (hits / len(queries))

    @async_in_thread
    def search(self, result_future: asyncio.Future, query: str) -> None:
        results = []
        for channel in self.channels:
            results += self._channel_search(query, channel)
        results += Search(query + " karaoke").results

        results.sort(key=partial(self._contains_index, query))

        result_future.set_result(
            [
                Result(
                    id=result.watch_url,
                    source="youtube",
                    title=result.title,
                    artist=result.author,
                    album="YouTube",
                )
                for result in results
            ]
        )

    def _channel_search(self, query, channel) -> list:
        browseID = Channel(f"https://www.youtube.com{channel}").channel_id
        endpoint = f"{self.innertube_client.base_url}/browse"

        data = {"query": query, "browseId": browseID, "params": "EgZzZWFyY2g%3D"}
        data.update(self.innertube_client.base_data)
        results = self.innertube_client._call_api(
            endpoint, self.innertube_client.base_params, data
        )
        items = results["contents"]["twoColumnBrowseResultsRenderer"]["tabs"][-1][
            "expandableTabRenderer"
        ]["content"]["sectionListRenderer"]["contents"]

        list_of_videos = []
        for item in items:
            try:
                if (
                    "itemSectionRenderer" in item
                    and "videoRenderer" in item["itemSectionRenderer"]["contents"][0]
                ):
                    yt_url = (
                        "https://youtube.com/watch?v="
                        + item["itemSectionRenderer"]["contents"][0]["videoRenderer"][
                            "videoId"
                        ]
                    )
                    author = item["itemSectionRenderer"]["contents"][0][
                        "videoRenderer"
                    ]["ownerText"]["runs"][0]["text"]
                    title = item["itemSectionRenderer"]["contents"][0]["videoRenderer"][
                        "title"
                    ]["runs"][0]["text"]
                    yt = YouTube(yt_url)
                    yt.author = author
                    yt.title = title
                    list_of_videos.append(yt)

            except KeyError:
                pass
        return list_of_videos

    @async_in_thread
    def buffer(self, entry: Entry) -> dict:
        print(f"Buffering {entry}")
        with self.masterlock:
            if entry.uuid in self.downloaded_files:
                print(f"Already buffering {entry}")
                return {}
            self.downloaded_files[entry.uuid] = {}

        yt = YouTube(entry.id)

        streams = yt.streams
    
        video_streams = streams.filter(
                type="video", 
                custom_filter_functions=[lambda s: int(s.resolution[:-1]) <= 1080]
                )
        audio_streams = streams.filter(only_audio=True)

        best_720_stream = sorted(video_streams, key=lambda s: int(s.resolution[:-1]) + (1 if s.is_progressive else 0))[-1]
        best_audio_stream = sorted(audio_streams, key=lambda s: int(s.abr[:-4]))[-1]

        print(best_720_stream)
        print(best_audio_stream)

        if not best_720_stream.is_progressive:
            self.downloaded_files[entry.uuid]["audio"] = best_audio_stream.download(output_path=self.tmp_dir, filename_prefix=f"{entry.uuid}-audio")
        else:
            self.downloaded_files[entry.uuid]["audio"] = None

        self.downloaded_files[entry.uuid]["video"] = best_720_stream.download(output_path=self.tmp_dir, filename_prefix=entry.uuid)

        return {}


available_sources["youtube"] = YoutubeSource
