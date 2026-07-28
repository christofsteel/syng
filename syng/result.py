"""Module for search results."""

from __future__ import annotations

import re
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
    title: str | None
    artist: str | None
    album: str | None
    duration: str | None = None

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
            match_string.replace(".", "\\.").replace("{", "(?P<").replace("}", ">.+)"), ident
        )
        if m is not None:
            return m.groupdict()
        return {}

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
        match_string = "{artist} - {title} - {collection}.{extension}"

        matched = Result.__match_re__(match_string, filename)

        album: str | None
        try:
            artist = matched["artist"].strip()
            title = matched["title"].strip()
            album = matched["collection"].strip()
            return cls(ident=filename, source=source, title=title, artist=artist, album=album)
        except KeyError:
            album = "YouTube" if source == "youtube" else None
            return cls(ident=filename, source=source, title=None, artist=None, album=album)

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
            ident=values.get("ident", ""),
            source=values.get("source", ""),
            title=values.get("title", ""),
            artist=values.get("artist", ""),
            album=values.get("album", ""),
            duration=values.get("duration", ""),
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
            "title": self.title if self.title is not None else self.ident,
        }
        if self.album is not None:
            output["album"] = self.album
        if self.artist is not None:
            output["artist"] = self.artist
        if self.duration is not None:
            output["duration"] = self.duration
        return output
