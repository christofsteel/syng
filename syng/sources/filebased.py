"""Module for an abstract filebased Source."""

import asyncio
import os
from typing import TYPE_CHECKING, Any, Optional


try:
    from pymediainfo import MediaInfo

    PYMEDIAINFO_AVAILABLE = True
except ImportError:
    if TYPE_CHECKING:
        from pymediainfo import MediaInfo
    PYMEDIAINFO_AVAILABLE = False

from .source import Source
from ..config import ListStrOption, ConfigOption


class FileBasedSource(Source):
    """
    A abstract source for indexing and playing songs based on files.

    Config options are:
        -``extensions``, list of filename extensions
    """

    config_schema = Source.config_schema | {
        "extensions": ConfigOption(
            ListStrOption(),
            "List of filename extensions\n(mp3+cdg, mp4, ...)",
            ["mp3+cdg"],
        )
    }

    def __init__(self, config: dict[str, Any]):
        """Initialize the file module."""
        super().__init__(config)

        self.extensions: list[str] = config["extensions"] if "extensions" in config else ["mp3+cdg"]
        self.extra_mpv_arguments = ["--scale=oversample"]

    def has_correct_extension(self, path: Optional[str]) -> bool:
        """
        Check if a `path` has a correct extension.

        For A+B type extensions (like mp3+cdg) only the latter halve is checked

        :param path: The path to check.
        :type path: Optional[str]
        :return: True iff path has correct extension.
        :rtype: bool
        """
        return path is not None and os.path.splitext(path)[1][1:] in [
            ext.rsplit("+", maxsplit=1)[-1] for ext in self.extensions
        ]

    def get_video_audio_split(self, path: str) -> tuple[str, Optional[str]]:
        """
        Returns path for audio and video file, if filetype is marked as split.

        If the file is not marked as split, the second element of the tuple will be None.

        :params: path: The path to the file
        :type path: str
        :return: Tuple with path to video and audio file
        :rtype: tuple[str, Optional[str]]
        """
        extension_of_path = os.path.splitext(path)[1][1:]
        splitted_extensions = [ext.split("+") for ext in self.extensions if "+" in ext]
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
