"""Module for an abstract filebased Source."""

import asyncio
import os
import re
from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

from syng.entry import Entry

try:
    from pymediainfo import MediaInfo

    PYMEDIAINFO_AVAILABLE = True
except ImportError:
    if TYPE_CHECKING:
        from pymediainfo import MediaInfo
    PYMEDIAINFO_AVAILABLE = False

from syng.config import SourceConfig
from syng.log import logger
from syng.sources.source import Source


@dataclass
class FileBasedConfig(SourceConfig):
    """(Base) Configuration object for filebased Sources.

    Attributes:
        extensions: List of filename extensions, that are included in this source.

    """

    extensions: list[str] = field(
        default_factory=lambda: ["mp3+cdg", "mp4", "mkv", "webm"],
        metadata={
            "desc": "Filename Extensions",
            "help": """<p>Only files with these filename extensions will be indexed</p>
            <p>For files, that have their audio and video parts seperate, you can use the "+" 
            notation, e.g. mp3+cdg. Files, that belong together must have the same file name, 
            except the extension. The first part will be used as audio, the latter will be 
            used as video.</p>""",
        },
    )
    filename_schema: str = field(
        default="{artist} - {title} - {album}.{extension}",
        metadata={
            "desc": "Filename Schema",
            "help": """<p>Schema to infer some metadata of the files. The filename will be used 
            as title, if parsing failes.</p>
            <p>You can use {artist}, {title}, {album} and {extension} as fields.</p>""",
        },
    )


@dataclass
class FileBasedSource(Source, ABC):
    """A abstract source for indexing and playing songs based on files.

    By default, a index to help with searching is created, and mpv is set up to use ``oversample``
    for a more __blocky__ look, to mimic traditional karaoke machines.

    Attributes:
        config: ``FileBasedConfig`` object.

    """

    config: FileBasedConfig
    build_index: bool = True

    def __post_init__(self) -> None:
        """Initialize the source and set default."""
        super().__post_init__()
        self.extra_mpv_options = {"scale": "oversample"}

    @staticmethod
    def __match_re__(match_string: str, ident: str) -> dict[str, str]:
        """Match against the {var} syntax.

        Args:
            match_string: Schema in {var} syntax
            ident: string to match

        Returns:
            A dictionary with all matches

        """
        m = re.match(
            match_string.replace("+", "\\+")
            .replace("*", "\\*")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("[", "\\[")
            .replace("]", "\\]")
            .replace(".", "\\.")
            .replace("{", "(?P<")
            .replace("}", ">.+)"),
            ident,
        )
        if m is not None:
            return m.groupdict()
        return {}

    @override
    def data_from_ident(self, ident: str) -> dict[str, str]:
        return {"artist": "Unknown", "title": ident, "album": "Unknown"} | self.__match_re__(
            self.config.filename_schema, ident
        )

    def is_valid(self, entry: Entry) -> bool:
        """Check if an entry is valid.

        An entry is valid, if it its source is registered as this source.

        Args:
            entry: The entry to check.

        Returns:
            True iff. the entry is valud.

        """
        logger.debug(entry)
        logger.debug(self.source_name)
        return entry.source == self.source_name

    def has_correct_extension(self, path: str | None) -> bool:
        """Check if a `path` has a correct extension.

        For A+B type extensions (like mp3+cdg) only the latter half is checked

        Args:
            path: The path to check.

        Returns:
            True iff path has correct extension, or is ``None``

        """
        return path is not None and os.path.splitext(path)[1][1:] in [
            ext.rsplit("+", maxsplit=1)[-1] for ext in self.config.extensions
        ]

    def get_video_audio_split(self, path: str) -> tuple[str, str | None]:
        """Return path for audio and video file, if filetype is marked as split.

        If the file is not marked as split, the second element of the tuple will be None.

        Args:
            path: The path to the file

        Returns:
            Tuple with path to video and audio file, if applicable

        """
        extension_of_path = os.path.splitext(path)[1][1:]
        splitted_extensions = [ext.split("+") for ext in self.config.extensions if "+" in ext]
        splitted_extensions_dict = {video: audio for [audio, video] in splitted_extensions}

        if extension_of_path in splitted_extensions_dict:
            audio_path = (
                os.path.splitext(path)[0] + "." + splitted_extensions_dict[extension_of_path]
            )
            return (path, audio_path)
        return (path, None)

    async def get_duration(self, path: str) -> int:
        """Return the duration for the file.

        Args:
            path: The path to the file

        Returns:
            The duration in seconds

        """
        if not PYMEDIAINFO_AVAILABLE:
            return 180

        def _get_duration(file: str) -> int:
            info: str | MediaInfo = MediaInfo.parse(file)
            if isinstance(info, str):
                return 180
            duration: int = int(float(info.audio_tracks[0].to_data()["duration"]))
            return duration // 1000

        video_path, audio_path = self.get_video_audio_split(path)

        check_path = audio_path if audio_path is not None else video_path
        duration = await asyncio.to_thread(_get_duration, check_path)

        return duration
