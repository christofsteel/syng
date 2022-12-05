"""
Construct the S3 source.

Adds it to the ``available_sources`` with the name ``s3``
"""
import asyncio
import os
from itertools import zip_longest
from json import load
from json import dump
from typing import Any
from typing import Optional
from typing import Tuple

import mutagen
from minio import Minio

from ..entry import Entry
from ..result import Result
from .source import available_sources
from .source import Source


class S3Source(Source):
    """A source for playing songs from a s3 compatible storage.

    Config options are:
        - ``endpoint``, ``access_key``, ``secret_key``, ``bucket``: These
          will simply be forwarded to the ``minio`` client.
        - ``tmp_dir``: The folder, where temporary files are stored. Default
          is ``/tmp/syng``
        - ``index_file``: If the file does not exist, saves the list of
          ``cdg``-files from the s3 instance to this file. If it exists, loads
          the list of files from this file.
    """

    def __init__(self, config: dict[str, Any]):
        """Create the source."""
        super().__init__(config)

        if (
            "endpoint" in config
            and "access_key" in config
            and "secret_key" in config
        ):
            self.minio: Minio = Minio(
                config["endpoint"],
                access_key=config["access_key"],
                secret_key=config["secret_key"],
            )
            self.bucket: str = config["bucket"]
            self.tmp_dir: str = (
                config["tmp_dir"] if "tmp_dir" in config else "/tmp/syng"
            )

        self.index: list[str] = []
        self.index_file: Optional[str] = (
            config["index_file"] if "index_file" in config else None
        )
        self.extra_mpv_arguments = ["--scale=oversample"]

    async def get_entry(self, performer: str, ident: str) -> Entry:
        """
        Create an :py:class:`syng.entry.Entry` for the identifier.

        The identifier should be a ``cdg`` filepath on the s3 server.

        Initially the duration for the generated entry will be set to 180
        seconds, so the server will ask the client for that missing
        metadata.

        :param performer: The persong singing.
        :type performer: str
        :param ident: A path to a ``cdg`` file.
        :type ident: str
        :return: An entry with the data.
        :rtype: Entry
        """
        res: Optional[Result] = Result.from_filename(ident, "s3")
        if res is not None:
            return Entry(
                ident=ident,
                source="s3",
                duration=180,
                album=res.album,
                title=res.title,
                artist=res.artist,
                performer=performer,
            )
        raise RuntimeError(f"Could not parse {ident}")

    async def get_config(self) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Return the list of ``cdg`` files on the s3 instance.

        The list is chunked in 1000 files per entry and inside the dictionary
        with key ``index``.

        :return: see above
        :rtype: list[dict[str, Any]]
        """

        def _get_config() -> dict[str, Any] | list[dict[str, Any]]:
            if not self.index:
                if self.index_file is not None and os.path.isfile(
                    self.index_file
                ):
                    with open(
                        self.index_file, "r", encoding="utf8"
                    ) as index_file_handle:
                        self.index = load(index_file_handle)
                else:
                    print(f"s3: Indexing '{self.bucket}'")
                    self.index = [
                        obj.object_name
                        for obj in self.minio.list_objects(
                            self.bucket, recursive=True
                        )
                        if obj.object_name.endswith(".cdg")
                    ]
                    print("s3: Indexing done")
                    if self.index_file is not None and not os.path.isfile(
                        self.index_file
                    ):
                        with open(
                            self.index_file, "w", encoding="utf8"
                        ) as index_file_handle:
                            dump(self.index, index_file_handle)

            chunked = zip_longest(*[iter(self.index)] * 1000, fillvalue="")
            return [
                {"index": list(filter(lambda x: x != "", chunk))}
                for chunk in chunked
            ]

        return await asyncio.to_thread(_get_config)

    def add_to_config(self, config: dict[str, Any]) -> None:
        """Add the chunk of the index list to the internal index list."""
        self.index += config["index"]

    async def search(self, query: str) -> list[Result]:
        """
        Search the internal index list for the query.

        :param query: The query to search for
        :type query: str
        :return: A list of Results, that need to contain all the words from
          the ``query``
        :rtype: list[Result]
        """
        filtered: list[str] = self.filter_data_by_query(query, self.index)
        results: list[Result] = []
        for filename in filtered:
            result: Optional[Result] = Result.from_filename(filename, "s3")
            if result is None:
                continue
            results.append(result)
        return results

    async def get_missing_metadata(self, entry: Entry) -> dict[str, Any]:
        """
        Return the duration for the mp3 file.

        :param entry: The entry with the associated mp3 file
        :type entry: Entry
        :return: A dictionary containing the duration in seconds in the
          ``duration`` key.
        :rtype: dict[str, Any]
        """

        def mutagen_wrapped(file: str) -> int:
            meta_infos = mutagen.File(file).info
            return int(meta_infos.length)

        await self.ensure_playable(entry)

        audio_file_name: Optional[str] = self.downloaded_files[
            entry.ident
        ].audio

        if audio_file_name is None:
            duration: int = 180
        else:
            duration = await asyncio.to_thread(
                mutagen_wrapped, audio_file_name
            )

        return {"duration": int(duration)}

    async def do_buffer(self, entry: Entry) -> Tuple[str, Optional[str]]:
        """
        Download the ``cdg`` and the ``mp3`` file from the s3.

        :param entry: The entry to download
        :type entry: Entry
        :return: A tuple with the location of the ``cdg`` and the ``mp3`` file.
        :rtype: Tuple[str, Optional[str]]
        """
        cdg_filename: str = os.path.basename(entry.ident)
        path_to_file: str = os.path.dirname(entry.ident)

        cdg_path: str = os.path.join(path_to_file, cdg_filename)
        target_file_cdg: str = os.path.join(self.tmp_dir, cdg_path)

        ident_mp3: str = entry.ident[:-3] + "mp3"
        target_file_mp3: str = target_file_cdg[:-3] + "mp3"
        os.makedirs(os.path.dirname(target_file_cdg), exist_ok=True)

        video_task: asyncio.Task[Any] = asyncio.create_task(
            asyncio.to_thread(
                self.minio.fget_object,
                self.bucket,
                entry.ident,
                target_file_cdg,
            )
        )
        audio_task: asyncio.Task[Any] = asyncio.create_task(
            asyncio.to_thread(
                self.minio.fget_object, self.bucket, ident_mp3, target_file_mp3
            )
        )

        await video_task
        await audio_task
        return target_file_cdg, target_file_mp3


available_sources["s3"] = S3Source
