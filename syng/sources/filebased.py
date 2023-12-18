"""Module for an abstract filebased Source."""
import asyncio
import os
from typing import Any, Optional

from pymediainfo import MediaInfo

from .source import Source


class FileBasedSource(Source):
    """A source for indexing and playing songs from a local folder.

    Config options are:
        -``dir``, dirctory to index and server from.
    """

    config_schema = Source.config_schema | {
        "extensions": (
            list,
            "List of filename extensions\n(mp3+cdg, mp4, ...)",
            ["mp3+cdg"],
        )
    }

    def __init__(self, config: dict[str, Any]):
        """Initialize the file module."""
        super().__init__(config)

        self.extensions: list[str] = (
            config["extensions"] if "extensions" in config else ["mp3+cdg"]
        )
        self.extra_mpv_arguments = ["--scale=oversample"]

    def has_correct_extension(self, path: str) -> bool:
        """Check if a `path` has a correct extension.

        For A+B type extensions (like mp3+cdg) only the latter halve is checked

        :return: True iff path has correct extension.
        :rtype: bool
        """
        return os.path.splitext(path)[1][1:] in [
            ext.split("+")[-1] for ext in self.extensions
        ]

    def get_video_audio_split(self, path: str) -> tuple[str, Optional[str]]:
        extension_of_path = os.path.splitext(path)[1][1:]
        splitted_extensions = [ext.split("+") for ext in self.extensions if "+" in ext]
        splitted_extensions_dict = {
            video: audio for [audio, video] in splitted_extensions
        }

        if extension_of_path in splitted_extensions_dict:
            audio_path = (
                os.path.splitext(path)[0]
                + "."
                + splitted_extensions_dict[extension_of_path]
            )
            return (path, audio_path)
        return (path, None)

    async def get_duration(self, path: str) -> int:
        def _get_duration(file: str) -> int:
            print(file)
            info: str | MediaInfo = MediaInfo.parse(file)
            if isinstance(info, str):
                return 180
            duration: int = info.audio_tracks[0].to_data()["duration"]
            return duration // 1000

        video_path, audio_path = self.get_video_audio_split(path)

        check_path = audio_path if audio_path is not None else video_path
        duration = await asyncio.to_thread(_get_duration, check_path)

        return duration
