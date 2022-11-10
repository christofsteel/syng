import asyncio
import shlex
from functools import partial

from pytube import YouTube, Search, Channel, innertube
from mpv import MPV

from .source import Source, async_in_thread
from ..entry import Entry
from ..result import Result


class YoutubeSource(Source):
    def __init__(self):
        super().__init__()
        self.innertube_client = innertube.InnerTube(client="WEB")
        self.channels = ["/c/CCKaraoke"]

    @async_in_thread
    def play(self, ident: str) -> None:
        self.player = MPV(
            input_default_bindings=True,
            input_vo_keyboard=True,
            osc=True,
            ytdl=True,
            script_opts="ytdl_hook-ytdl_path=yt-dlp",
        )
        self.player.play(ident)
        self.player.wait_for_playback()

    async def skip_current(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.player.terminate)

    @async_in_thread
    def get_entry(self, performer: str, url: str) -> Entry:
        yt = YouTube(url)
        return Entry(
            id=url,
            source="youtube",
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
    def search(self, query: str) -> list[Result]:
        for channel in self.channels:
            results = self._channel_search(query, channel)
        results += Search(query + " karaoke").results

        results.sort(key=partial(self._contains_index, query))

        return [
            Result(
                id=result.watch_url,
                source="youtube",
                title=result.title,
                artist=result.author,
            )
            for result in results
        ]

    def _channel_search(self, query, channel):
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
