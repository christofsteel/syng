from json import load, dump
from time import sleep, perf_counter
from itertools import zip_longest
from threading import Event, Lock
from asyncio import Future
import os

from minio import Minio

import mutagen

from .source import Source, async_in_thread, available_sources
from .common import play_mpv, kill_mpv
from ..result import Result
from ..entry import Entry


class S3Source(Source):
    def __init__(self, config):
        super().__init__()

        if "endpoint" in config and "access_key" in config and "secret_key" in config:
            self.minio = Minio(
                config["endpoint"],
                access_key=config["access_key"],
                secret_key=config["secret_key"],
            )
            self.bucket = config["bucket"]
            self.tmp_dir = config["tmp_dir"] if "tmp_dir" in config else "/tmp/syng"

        self.index = [] if "index" not in config else config["index"]
        self.downloaded_files = {}
        self.player = None
        self.masterlock = Lock()

    async def get_entry(self, performer: str, filename: str) -> Entry:
        res = Result.from_filename(filename, "s3")
        if res is not None:
            return Entry(
                id=filename,
                source="s3",
                duration=180,
                album=res.album,
                title=res.title,
                artist=res.artist,
                performer=performer,
            )
        raise RuntimeError(f"Could not parse {filename}")

    async def play(self, entry) -> None:
        while not entry.uuid in self.downloaded_files:
            sleep(0.1)

        self.downloaded_files[entry.uuid]["lock"].wait()

        cdg_file = self.downloaded_files[entry.uuid]["cdg"]
        mp3_file = self.downloaded_files[entry.uuid]["mp3"]

        self.player = await play_mpv(
            cdg_file, mp3_file, ["--scale=oversample"]
        )

        await self.player.wait()

    async def skip_current(self, entry) -> None:
        await self.player.kill()

    @async_in_thread
    def get_config(self):
        if not self.index:
            print("Start indexing")
            start = perf_counter()
            # self.index = [
            #     obj.object_name
            #     for obj in self.minio.list_objects(self.bucket, recursive=True)
            # ]
            # with open("s3_files", "w") as f:
            #     dump(self.index, f)
            with open("s3_files", "r") as f:
                self.index = [item for item in load(f) if item.endswith(".cdg")]
            print(len(self.index))
            stop = perf_counter()
            print(f"Took {stop - start:0.4f} seconds")

        chunked = zip_longest(*[iter(self.index)] * 1000, fillvalue="")
        return [{"index": list(filter(lambda x: x != "", chunk))} for chunk in chunked]

    def add_to_config(self, config):
        self.index += config["index"]

    @async_in_thread
    def search(self, result_future: Future, query: str) -> None:
        print("searching s3")
        filtered = self.filter_data_by_query(query, self.index)
        results = []
        for filename in filtered:
            print(filename)
            result = Result.from_filename(filename, "s3")
            print(result)
            if result is None:
                continue
            results.append(result)
        print(results)
        result_future.set_result(results)

    @async_in_thread
    def buffer(self, entry: Entry) -> dict:
        with self.masterlock:
            if entry.uuid in self.downloaded_files:
                return {}
            self.downloaded_files[entry.uuid] = {"lock": Event()}

        cdg_filename = os.path.basename(entry.id)
        path_to_file = os.path.dirname(entry.id)

        cdg_path_with_uuid = os.path.join(path_to_file, f"{entry.uuid}-{cdg_filename}")
        target_file_cdg = os.path.join(self.tmp_dir, cdg_path_with_uuid)

        ident_mp3 = entry.id[:-3] + "mp3"
        target_file_mp3 = target_file_cdg[:-3] + "mp3"
        os.makedirs(os.path.dirname(target_file_cdg), exist_ok=True)

        print(
            f'self.minio.fget_object("{self.bucket}", "{entry.id}", "{target_file_cdg}")'
        )
        self.minio.fget_object(self.bucket, entry.id, target_file_cdg)
        self.minio.fget_object(self.bucket, ident_mp3, target_file_mp3)

        self.downloaded_files[entry.uuid]["cdg"] = target_file_cdg
        self.downloaded_files[entry.uuid]["mp3"] = target_file_mp3
        self.downloaded_files[entry.uuid]["lock"].set()

        meta_infos = mutagen.File(target_file_mp3).info

        print(f"duration is {meta_infos.length}")

        return {"duration": int(meta_infos.length)}


available_sources["s3"] = S3Source
