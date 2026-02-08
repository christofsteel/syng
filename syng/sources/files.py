"""Module for the files Source."""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from syng.entry import Entry
from syng.sources.filebased import FileBasedConfig, FileBasedSource
from syng.sources.source import available_sources


@dataclass
class FileSourceConfig(FileBasedConfig):
    dir: str = field(default=".", metadata={"desc": "Directory to index", "semantic": "folder"})


class FilesSource(FileBasedSource):
    """A source for indexing and playing songs from a local folder.

    Config options are:
        -``dir``, dirctory to index and serve from.
    """

    config_object: FileSourceConfig

    source_name = "files"

    def apply_config(self, config: dict[str, Any]) -> None:
        super().apply_config(config)
        self.dir = config.get("dir", ".")

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

    async def do_buffer(self, entry: Entry, pos: int) -> tuple[str, str | None]:
        """
        No buffering needs to be done, since the files are already on disk.

        We just return the file names.
        """

        return self.get_video_audio_split(os.path.join(self.dir, entry.ident))


available_sources["files"] = FilesSource
