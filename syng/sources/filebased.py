"""Module for an abstract filebased Source."""

import asyncio
import os
from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from syng.entry import Entry

try:
    from pymediainfo import MediaInfo

    PYMEDIAINFO_AVAILABLE = True
except ImportError:
    if TYPE_CHECKING:
        from pymediainfo import MediaInfo
    PYMEDIAINFO_AVAILABLE = False

from syng.config import SourceConfig
from syng.sources.source import Source


@dataclass
class FileBasedConfig(SourceConfig):
    extensions: list[str] = field(
        default_factory=lambda: ["mp3+cdg"],
        metadata={"desc": "List of filename extensions\n(mp3+cdg, mp4, ...)"},
    )


@dataclass
class FileBasedSource(Source, ABC):
    """
    A abstract source for indexing and playing songs based on files.

    Config options are:
        -``extensions``, list of filename extensions
    """

    config: FileBasedConfig

    def __post_init__(self) -> None:
        super().__post_init__()
        self.build_index = True
        self.extra_mpv_options = {"scale": "oversample"}

    def is_valid(self, entry: Entry) -> bool:
        return entry.ident in self._index and entry.source == self.source_name

    def has_correct_extension(self, path: str | None) -> bool:
        """
        Check if a `path` has a correct extension.

        For A+B type extensions (like mp3+cdg) only the latter half is checked

        :param path: The path to check.
        :type path: Optional[str]
        :return: True iff path has correct extension.
        :rtype: bool
        """
        return path is not None and os.path.splitext(path)[1][1:] in [
            ext.rsplit("+", maxsplit=1)[-1] for ext in self.config.extensions
        ]

    def get_video_audio_split(self, path: str) -> tuple[str, str | None]:
        """
        Returns path for audio and video file, if filetype is marked as split.

        If the file is not marked as split, the second element of the tuple will be None.

        :params: path: The path to the file
        :type path: str
        :return: Tuple with path to video and audio file
        :rtype: tuple[str, Optional[str]]
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
        """
        Return the duration for the file.

        :param path: The path to the file
        :type path: str
        :return: The duration in seconds
        :rtype: int
        """
        if not PYMEDIAINFO_AVAILABLE:
            return 180

        def _get_duration(file: str) -> int:
            info: str | MediaInfo = MediaInfo.parse(file)
            if isinstance(info, str):
                return 180
            duration: int = info.audio_tracks[0].to_data()["duration"]
            return duration // 1000

        video_path, audio_path = self.get_video_audio_split(path)

        check_path = audio_path if audio_path is not None else video_path
        duration = await asyncio.to_thread(_get_duration, check_path)

        return duration
