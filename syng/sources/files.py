"""Module for the files Source"""
import asyncio
import os
from itertools import zip_longest
from typing import Any
from typing import Optional
from typing import Tuple

import mutagen

from ..entry import Entry
from ..result import Result
from .source import available_sources
from .source import Source


class FilesSource(Source):
    """A source for indexing and playing songs from a local folder.


    Config options are:
        -``dir``, dirctory to index and server from.
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.dir = config["dir"] if "dir" in config else "."
        self.index: list[str] = config["index"] if "index" in config else []
        self.extra_mpv_arguments = ["--scale=oversample"]

    async def get_entry(self, performer: str, ident: str) -> Entry:
        """
        Extract the information for an Entry from the file name.

        Since the server does not have access to the actual file, only to the
        file name, ``duration`` can not be set. It will be approximated with
        180 seconds. When added to the queue, the server will ask the client
        for additional metadata, like this.

        :param performer: The persong singing.
        :type performer: str
        :param ident: A path to a ``cdg`` file.
        :type ident: str
        :return: An entry with the data.
        :rtype: Entry
        """
        res: Optional[Result] = Result.from_filename(ident, "files")
        if res is not None:
            return Entry(
                ident=ident,
                source="files",
                duration=180,
                album=res.album,
                title=res.title,
                artist=res.artist,
                performer=performer,
            )
        raise RuntimeError(f"Could not parse {ident}")

    async def get_config(self) -> list[dict[str, Any]]:
        """
        Return the list of ``cdg`` files in the configured directory.

        The list is chunked in 1000 files per entry and inside the dictionary
        with key ``index``. The filenames are all relative to the configured
        ``dir``, so you don't expose parts of your configuration.

        :return: see above
        :rtype: list[dict[str, Any]]
        """

        def _get_config() -> list[dict[str, Any]]:
            if not self.index:
                self.index = []
                print(f"files: indexing {self.dir}")
                for path, dir, files in os.walk(self.dir):
                    for file in files:
                        if file.endswith(".cdg"):
                            self.index.append(
                                os.path.join(path, file)[len(self.dir) :]
                            )
                print("files: indexing done")
            chunked = zip_longest(*[iter(self.index)] * 1000, fillvalue="")
            return [
                {"index": list(filter(lambda x: x != "", chunk))}
                for chunk in chunked
            ]

        return await asyncio.to_thread(_get_config)

    def add_to_config(self, config: dict[str, Any]) -> None:
        """Add the chunk of the index list to the internal index list."""
        self.index += config["index"]

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

    async def search(self, query: str) -> list[Result]:
        """
        Search the internal index list for the query.

        :param query: The query to search for
        :type query: str
        :return: A list of Results, that need to contain all the words from
          the ``query``
        :rtype: list[Result]
        """
        print("searching files")
        filtered: list[str] = self.filter_data_by_query(query, self.index)
        results: list[Result] = []
        for filename in filtered:
            result: Optional[Result] = Result.from_filename(filename, "files")
            if result is None:
                continue
            results.append(result)
        return results


available_sources["files"] = FilesSource
