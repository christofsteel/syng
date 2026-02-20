"""Module for search results."""

from __future__ import annotations

import os.path
from dataclasses import dataclass


@dataclass
class Result:
    """A single search result.

    Attributes:
        ident: The identifier of the entry in the source
        source: The name of the source of the entry
        title: The title of the song
        artist: The artist of the song
        album: The name of the album or compilation, this particular version is from.
        duration: The duration of the song

    """

    ident: str
    source: str
    title: str
    artist: str | None
    album: str | None
    duration: str | None = None

    @classmethod
    def from_filename(cls, filename: str, source: str) -> Result:
        """Infer some attributes from the filename.

        The filename must be in this form::

            {artist} - {title} - {album}.ext

        If parsing failes, the filename will be used as the title and the
        artist and album will be set to "Unknown".

        Args:
            filename: The filename to parse
            source: The name of the source

        Returns:
            A ``Result`` with the parsed results

        """
        basename = os.path.splitext(filename)[0]
        try:
            splitfile = os.path.basename(basename).split(" - ")
            ident = filename
            artist = splitfile[0].strip()
            title = splitfile[1].strip()
            album = splitfile[2].strip()
            return cls(ident=ident, source=source, title=title, artist=artist, album=album)
        except IndexError:
            return cls(ident=filename, source=source, title=basename, artist=None, album=None)

    @classmethod
    def from_dict(cls, values: dict[str, str]) -> Result:
        """Create a Result object from a dictionary.

        The dictionary must have the following keys:
          - ident (str)
          - source (str)
          - title (str)
          - artist (str)
          - album (str)
          - duration (int, optional)

        Args:
            values: The dictionary with the values

        Returns:
            A ``Result`` containg the information if the dict.

        """
        return cls(
            ident=values["ident"],
            source=values["source"],
            title=values["title"],
            artist=values["artist"],
            album=values["album"],
            duration=values.get("duration"),
        )

    def to_dict(self) -> dict[str, str]:
        """Convert the Result object to a dictionary.

        The dictionary will have the following keys:
          - ident (str)
          - source (str)
          - title (str)
          - album (str, if available)
          - artist (str, if available)
          - duration (str, if available)

        Returns:
            The dictionary with the values

        """
        output: dict[str, str] = {
            "ident": self.ident,
            "source": self.source,
            "title": self.title,
        }
        if self.album is not None:
            output["album"] = self.album
        if self.artist is not None:
            output["artist"] = self.artist
        if self.duration is not None:
            output["duration"] = self.duration
        return output
