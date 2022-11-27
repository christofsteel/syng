from json import load, dump
from time import sleep, perf_counter
from itertools import zip_longest
import asyncio
import os
from typing import Tuple, Optional

from minio import Minio

import mutagen

from .source import Source, available_sources
from ..result import Result
from ..entry import Entry


class S3Source(Source):
    def __init__(self, config):
        super().__init__(config)

        if "endpoint" in config and "access_key" in config and "secret_key" in config:
            self.minio: Minio = Minio(
                config["endpoint"],
                access_key=config["access_key"],
                secret_key=config["secret_key"],
            )
            self.bucket: str = config["bucket"]
            self.tmp_dir: str = (
                config["tmp_dir"] if "tmp_dir" in config else "/tmp/syng"
            )

        self.index: list[str] = [] if "index" not in config else config["index"]
        self.extra_mpv_arguments = ["--scale=oversample"]

    async def get_entry(self, performer: str, ident: str) -> Entry:
        res: Optional[Result] = Result.from_filename(ident, "s3")
        if res is not None:
            return Entry(
                id=ident,
                source="s3",
                duration=180,
                album=res.album,
                title=res.title,
                artist=res.artist,
                performer=performer,
            )
        raise RuntimeError(f"Could not parse {ident}")

    async def get_config(self) -> dict | list[dict]:
        def _get_config() -> dict | list[dict]:
            if not self.index:
                print(f"Indexing {self.bucket}")
                # self.index = [
                #     obj.object_name
                #     for obj in self.minio.list_objects(self.bucket, recursive=True)
                # ]
                # with open("s3_files", "w") as f:
                #     dump(self.index, f)
                with open("s3_files", "r") as f:
                    self.index = [item for item in load(f) if item.endswith(".cdg")]

            chunked = zip_longest(*[iter(self.index)] * 1000, fillvalue="")
            return [
                {"index": list(filter(lambda x: x != "", chunk))} for chunk in chunked
            ]

        return await asyncio.to_thread(_get_config)

    def add_to_config(self, config: dict) -> None:
        self.index += config["index"]

    async def search(self, result_future: asyncio.Future, query: str) -> None:
        print("searching s3")
        filtered: list[str] = self.filter_data_by_query(query, self.index)
        results: list[Result] = []
        for filename in filtered:
            result: Optional[Result] = Result.from_filename(filename, "s3")
            if result is None:
                continue
            results.append(result)
        result_future.set_result(results)

    async def get_missing_metadata(self, entry: Entry) -> dict:
        def mutagen_wrapped(file: str) -> int:
            meta_infos = mutagen.File(file).info
            return int(meta_infos.length)

        await self.ensure_playable(entry)

        audio_file_name: Optional[str] = self.downloaded_files[entry.id].audio

        if audio_file_name is None:
            duration: int = 180
        else:
            duration = await asyncio.to_thread(mutagen_wrapped, audio_file_name)

        return {"duration": int(duration)}

    async def doBuffer(self, entry: Entry) -> Tuple[str, Optional[str]]:
        cdg_filename: str = os.path.basename(entry.id)
        path_to_file: str = os.path.dirname(entry.id)

        cdg_path: str = os.path.join(path_to_file, cdg_filename)
        target_file_cdg: str = os.path.join(self.tmp_dir, cdg_path)

        ident_mp3: str = entry.id[:-3] + "mp3"
        target_file_mp3: str = target_file_cdg[:-3] + "mp3"
        os.makedirs(os.path.dirname(target_file_cdg), exist_ok=True)

        video_task: asyncio.Task = asyncio.create_task(
            asyncio.to_thread(
                self.minio.fget_object, self.bucket, entry.id, target_file_cdg
            )
        )
        audio_task: asyncio.Task = asyncio.create_task(
            asyncio.to_thread(
                self.minio.fget_object, self.bucket, ident_mp3, target_file_mp3
            )
        )

        await video_task
        await audio_task
        return target_file_cdg, target_file_mp3


available_sources["s3"] = S3Source
