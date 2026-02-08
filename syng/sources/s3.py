"""
Construct the S3 source.

Adds it to the ``available_sources`` with the name ``s3``
"""

import asyncio
import os
from dataclasses import dataclass, field
from json import dump, load
from typing import TYPE_CHECKING, Any, cast

from platformdirs import user_cache_dir

try:
    from minio import Minio

    MINIO_AVAILABE = True
except ImportError:
    if TYPE_CHECKING:
        from minio import Minio
    MINIO_AVAILABE = False

from syng.entry import Entry
from syng.sources.filebased import FileBasedConfig, FileBasedSource
from syng.sources.source import available_sources


@dataclass
class S3Config(FileBasedConfig):
    endpoint: str = field(default="", metadata={"desc": "Endpoint of the s3"})
    access_key: str = field(default="", metadata={"desc": "Access key of the s3 (username)"})
    secret_key: str = field(
        default="", metadata={"desc": "Secret key of the s3 (password)", "semantic": "password"}
    )
    secure: bool = field(default=True, metadata={"desc": "Use SSL"})
    bucket: str = field(default="", metadata={"desc": "Bucket of the s3"})
    tmp_dir: str = field(
        default=user_cache_dir("syng"),
        metadata={"desc": "Folder for\ntemporary download", "semantic": "folder"},
    )
    index_file: str = field(
        default=os.path.join(user_cache_dir("syng"), "s3-index"),
        metadata={"desc": "Index file", "semantic": "file"},
    )


@dataclass
class S3Source(FileBasedSource):
    """A source for playing songs from a s3 compatible storage.

    Config options are:
        - ``endpoint``, ``access_key``, ``secret_key``, ``secure``, ``bucket``: These
          will simply be forwarded to the ``minio`` client.
        - ``tmp_dir``: The folder, where temporary files are stored. Default
          is ``${XDG_CACHE_DIR}/syng``
        - ``index_file``: If the file does not exist, saves the paths of
          files from the s3 instance to this file. If it exists, loads
          the list of files from this file.
    """

    config: S3Config
    source_name = "s3"

    def __post_init__(self) -> None:
        super().__post_init__()
        if MINIO_AVAILABE:
            self.minio: Minio = Minio(
                self.config.endpoint,
                access_key=self.config.access_key,
                secret_key=self.config.secret_key,
                secure=self.config.secure,
            )

    def load_file_list_from_server(self) -> list[str]:
        """
        Load the file list from the s3 instance.

        :return: A list of file paths
        :rtype: list[str]
        """

        file_list = [
            obj.object_name
            for obj in self.minio.list_objects(self.config.bucket, recursive=True)
            if obj.object_name is not None and self.has_correct_extension(obj.object_name)
        ]
        return file_list

    def write_index(self, file_list: list[str]) -> None:
        index_dir = os.path.dirname(self.config.index_file)
        if index_dir:
            os.makedirs(os.path.dirname(self.config.index_file), exist_ok=True)

        with open(self.config.index_file, "w", encoding="utf8") as index_file_handle:
            dump(file_list, index_file_handle)

    async def get_file_list(self) -> list[str]:
        """
        Return the list of files on the s3 instance, according to the extensions.

        If an index file exists, this will be read instead.

        As a side effect, an index file is generated, if configured.

        :return: see above
        :rtype: list[str]
        """

        def _get_file_list() -> list[str]:
            if os.path.isfile(self.config.index_file):
                with open(self.config.index_file, encoding="utf8") as index_file_handle:
                    return cast(list[str], load(index_file_handle))

            file_list = self.load_file_list_from_server()
            if not os.path.isfile(self.config.index_file):
                self.write_index(file_list)

            return file_list

        return await asyncio.to_thread(_get_file_list)

    async def update_file_list(self) -> list[str] | None:
        """
        Rescan the file list and update the index file.

        :return: The updated file list
        :rtype: list[str]
        """

        def _update_file_list() -> list[str]:
            file_list = self.load_file_list_from_server()
            self.write_index(file_list)
            return file_list

        return await asyncio.to_thread(_update_file_list)

    async def get_missing_metadata(self, entry: Entry) -> dict[str, Any]:
        """
        Return the duration for the music file.

        :param entry: The entry with the associated mp3 file
        :type entry: Entry
        :return: A dictionary containing the duration in seconds in the
          ``duration`` key.
        :rtype: dict[str, Any]
        """

        await self.ensure_playable(entry)

        file_name: str = self.downloaded_files[entry.ident].video

        duration = await self.get_duration(file_name)

        return {"duration": duration}

    async def do_buffer(self, entry: Entry, pos: int) -> tuple[str, str | None]:
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

        video_path, audio_path = self.get_video_audio_split(entry.ident)
        video_dl_path: str = os.path.join(self.config.tmp_dir, video_path)
        os.makedirs(os.path.dirname(video_dl_path), exist_ok=True)
        video_dl_task: asyncio.Task[Any] = asyncio.create_task(
            asyncio.to_thread(
                self.minio.fget_object, self.config.bucket, entry.ident, video_dl_path
            )
        )

        audio_dl_path: str | None
        if audio_path is not None:
            audio_dl_path = os.path.join(self.config.tmp_dir, audio_path)

            audio_dl_task: asyncio.Task[Any] = asyncio.create_task(
                asyncio.to_thread(
                    self.minio.fget_object, self.config.bucket, audio_path, audio_dl_path
                )
            )
        else:
            audio_dl_path = None
            audio_dl_task = asyncio.create_task(asyncio.sleep(0))

        await video_dl_task
        await audio_dl_task

        return video_dl_path, audio_dl_path


available_sources["s3"] = S3Source
