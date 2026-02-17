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
    """Configuration object for ``FilesSource``.

    Attributes:
        dir: Directory with the files to serve.

    """

    dir: str = field(default=".", metadata={"desc": "Directory to index", "semantic": "folder"})


@dataclass
class FilesSource(FileBasedSource):
    """A source for indexing and playing songs from a local folder.

    Attributes:
        config: ``FileSourceConfig`` object.

    """

    config: FileSourceConfig
    source_name = "files"

    async def get_file_list(self) -> list[str]:
        """Collect all files in ``dir``, that have the correct filename extension.

        Returns:
            All files in ``dir``, filtered by their filename extension.

        """

        def _get_file_list() -> list[str]:
            file_list = []
            for path, _, files in os.walk(self.config.dir):
                for file in files:
                    if self.has_correct_extension(file):
                        file_list.append(os.path.join(path, file)[len(self.config.dir) :])
            return file_list

        return await asyncio.to_thread(_get_file_list)

    async def get_missing_metadata(self, entry: Entry) -> dict[str, Any]:
        """Return the duration for the entry file.

        Args:
            entry: An entry

        Returns:
            A dictionary containing the duration in seconds in the ``duration`` key.

        """
        duration = await self.get_duration(os.path.join(self.config.dir, entry.ident))

        return {"duration": duration}

    async def do_buffer(self, entry: Entry, pos: int) -> tuple[str, str | None]:
        """No buffering needs to be done, since the files are already on disk.

        Returns:
            The video and the audio filename fot the entry, if applicable.

        """
        return self.get_video_audio_split(os.path.join(self.config.dir, entry.ident))


available_sources["files"] = FilesSource
