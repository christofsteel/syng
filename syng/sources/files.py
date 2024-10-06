"""Module for the files Source."""

import asyncio
import os
from typing import Any, Optional
from typing import Tuple


from ..entry import Entry
from .source import available_sources
from .filebased import FileBasedSource
from ..config import FolderOption, ConfigOption


class FilesSource(FileBasedSource):
    """A source for indexing and playing songs from a local folder.

    Config options are:
        -``dir``, dirctory to index and serve from.
    """

    source_name = "files"
    config_schema = FileBasedSource.config_schema | {
        "dir": ConfigOption(FolderOption(), "Directory to index", "."),
        # "index_file": ("file", "Index file", os.path.join(user_cache_dir("syng"), "files-index")),
    }

    def __init__(self, config: dict[str, Any]):
        """Initialize the file module."""
        super().__init__(config)

        self.dir = config["dir"] if "dir" in config else "."
        self.extra_mpv_arguments = ["--scale=oversample"]

    async def get_file_list(self) -> list[str]:
        """Collect all files in ``dir``, that have the correct filename extension"""

        def _get_file_list() -> list[str]:
            file_list = []
            for path, _, files in os.walk(self.dir):
                for file in files:
                    if self.has_correct_extension(file):
                        file_list.append(os.path.join(path, file)[len(self.dir) :])
            return file_list

        return await asyncio.to_thread(_get_file_list)

    async def get_missing_metadata(self, entry: Entry) -> dict[str, Any]:
        """
        Return the duration for the entry file.

        :param entry: An entry
        :type entry: Entry
        :return: A dictionary containing the duration in seconds in the
          ``duration`` key.
        :rtype: dict[str, Any]
        """

        duration = await self.get_duration(os.path.join(self.dir, entry.ident))

        return {"duration": duration}

    async def do_buffer(self, entry: Entry) -> Tuple[str, Optional[str]]:
        """
        No buffering needs to be done, since the files are already on disk.

        We just return the file names.
        """

        return self.get_video_audio_split(os.path.join(self.dir, entry.ident))


available_sources["files"] = FilesSource
