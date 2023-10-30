"""
Construct the S3 source.

Adds it to the ``available_sources`` with the name ``s3``
"""
import asyncio
import os
from json import load
from json import dump
from typing import Any
from typing import cast
from typing import Optional
from typing import Tuple

import mutagen
from minio import Minio

from ..entry import Entry
from .source import available_sources
from .source import Source


class S3Source(Source):
    """A source for playing songs from a s3 compatible storage.

    Config options are:
        - ``endpoint``, ``access_key``, ``secret_key``, ``secure``, ``bucket``: These
          will simply be forwarded to the ``minio`` client.
        - ``tmp_dir``: The folder, where temporary files are stored. Default
          is ``/tmp/syng``
        - ``index_file``: If the file does not exist, saves the paths of
          files from the s3 instance to this file. If it exists, loads
          the list of files from this file.
        - ``extensions``: List of filename extensions. Index only files with these one
          of these extensions (Default: ["cdg"])
    """

    def __init__(self, config: dict[str, Any]):
        """Create the source."""
        super().__init__(config)
        self.source_name = "s3"

        if (
            "endpoint" in config
            and "access_key" in config
            and "secret_key" in config
        ):
            self.minio: Minio = Minio(
                config["endpoint"],
                access_key=config["access_key"],
                secret_key=config["secret_key"],
                secure=(config["secure"] if "secure" in config else True),
            )
            self.bucket: str = config["bucket"]
            self.tmp_dir: str = (
                config["tmp_dir"] if "tmp_dir" in config else "/tmp/syng"
            )

        self.extensions = (
            [f".{ext}" for ext in config["extensions"]]
            if "extensions" in config
            else [".cdg"]
        )

        self.index_file: Optional[str] = (
            config["index_file"] if "index_file" in config else None
        )
        self.extra_mpv_arguments = ["--scale=oversample"]

    async def get_file_list(self) -> list[str]:
        """
        Return the list of files on the s3 instance, according to the extensions.

        If an index file exists, this will be read instead.

        As a side effect, an index file is generated, if configured.

        :return: see above
        :rtype: list[str]
        """

        def _get_file_list() -> list[str]:
            if self.index_file is not None and os.path.isfile(self.index_file):
                with open(
                    self.index_file, "r", encoding="utf8"
                ) as index_file_handle:
                    return cast(list[str], load(index_file_handle))

            file_list = [
                obj.object_name
                for obj in self.minio.list_objects(self.bucket, recursive=True)
                if os.path.splitext(obj.object_name)[1] in self.extensions
            ]
            if self.index_file is not None and not os.path.isfile(
                self.index_file
            ):
                with open(
                    self.index_file, "w", encoding="utf8"
                ) as index_file_handle:
                    dump(file_list, index_file_handle)
            return file_list

        return await asyncio.to_thread(_get_file_list)

    async def get_missing_metadata(self, entry: Entry) -> dict[str, Any]:
        """
        Return the duration for the music file.

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
        Download the file from the s3.

        If it is a ``cdg`` file, the accompaning ``mp3`` file is also downloaded

        :param entry: The entry to download
        :type entry: Entry
        :return: A tuple with the location of the main file. If the file a ``cdg`` file,
                 the second position is the location of the ``mp3`` file, otherwise None
                 .
        :rtype: Tuple[str, Optional[str]]
        """

        if os.path.splitext(entry.ident)[1] == ".cdg":
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
                    self.minio.fget_object,
                    self.bucket,
                    ident_mp3,
                    target_file_mp3,
                )
            )

            await video_task
            await audio_task
            return target_file_cdg, target_file_mp3
        video_filename: str = os.path.basename(entry.ident)
        path_to_file: str = os.path.dirname(entry.ident)

        video_path: str = os.path.join(path_to_file, video_filename)
        target_file_video: str = os.path.join(self.tmp_dir, video_path)

        os.makedirs(os.path.dirname(target_file_video), exist_ok=True)

        video_task: asyncio.Task[Any] = asyncio.create_task(
            asyncio.to_thread(
                self.minio.fget_object,
                self.bucket,
                entry.ident,
                target_file_video,
            )
        )

        await video_task
        return target_file_video, None


available_sources["s3"] = S3Source
