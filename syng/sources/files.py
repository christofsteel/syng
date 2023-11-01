"""Module for the files Source."""
import asyncio
import os
from typing import Any
from typing import Tuple

import mutagen

from ..entry import Entry
from .source import available_sources
from .source import Source


class FilesSource(Source):
    """A source for indexing and playing songs from a local folder.

    Config options are:
        -``dir``, dirctory to index and server from.
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize the file module."""
        super().__init__(config)
        self.source_name = "files"

        self.dir = config["dir"] if "dir" in config else "."
        self.extra_mpv_arguments = ["--scale=oversample"]

    async def get_file_list(self) -> list[str]:
        """Collect all ``cdg`` files in ``dir``."""

        def _get_file_list() -> list[str]:
            file_list = []
            for path, _, files in os.walk(self.dir):
                for file in files:
                    if file.endswith(".cdg"):
                        file_list.append(os.path.join(path, file)[len(self.dir) :])
            return file_list

        return await asyncio.to_thread(_get_file_list)

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

        audio_file_name: str = os.path.join(self.dir, entry.ident[:-3] + "mp3")

        duration = await asyncio.to_thread(mutagen_wrapped, audio_file_name)

        return {"duration": int(duration)}

    async def do_buffer(self, entry: Entry) -> Tuple[str, str]:
        """
        No buffering needs to be done, since the files are already on disk.

        We just return the cdg file name and the inferred mp3 file name
        """
        video_file_name: str = os.path.join(self.dir, entry.ident)
        audio_file_name: str = os.path.join(self.dir, entry.ident[:-3] + "mp3")

        return video_file_name, audio_file_name


available_sources["files"] = FilesSource
