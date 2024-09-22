"""Module for search results."""

from __future__ import annotations
from dataclasses import dataclass
import os.path
from typing import Optional


@dataclass
class Result:
    """This models a search result.

    :param ident: The identifier of the entry in the source
    :type ident: str
    :param source: The name of the source of the entry
    :type source: str
    :param title: The title of the song
    :type title: str
    :param artist: The artist of the song
    :type artist: str
    :param album: The name of the album or compilation, this particular
        version is from.
    :type album: str
    """

    ident: str
    source: str
    title: str
    artist: str
    album: str
    duration: Optional[str] = None

    @classmethod
    def from_filename(cls, filename: str, source: str) -> Result:
        """
        Infer most attributes from the filename.

        The filename must be in this form::

            {artist} - {title} - {album}.ext

        If parsing failes, the filename will be used as the title and the
        artist and album will be set to "Unknown".

        :param filename: The filename to parse
        :type filename: str
        :param source: The name of the source
        :type source: str
        :return: see above
        :rtype: Optional[Result]
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
            return cls(
                ident=filename, source=source, title=basename, artist="Unknown", album="Unknown"
            )

    @classmethod
    def from_dict(cls, values: dict[str, str]) -> Result:
        """
        Create a Result object from a dictionary.

        The dictionary must have the following keys:
          - ident (str)
          - source (str)
          - title (str)
          - artist (str)
          - album (str)
          - duration (int, optional)

        :param values: The dictionary with the values
        :type values: dict[str, str]
        :return: The Result object
        :rtype: Result
        """
        return cls(
            ident=values["ident"],
            source=values["source"],
            title=values["title"],
            artist=values["artist"],
            album=values["album"],
            duration=values.get("duration", None),
        )

    def to_dict(self) -> dict[str, str]:
        """
        Convert the Result object to a dictionary.

        The dictionary will have the following keys:
          - ident (str)
          - source (str)
          - title (str)
          - artist (str)
          - album (str)
          - duration (str, if available)

        :return: The dictionary with the values
        :rtype: dict[str, str]
        """
        output = {
            "ident": self.ident,
            "source": self.source,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
        }
        if self.duration is not None:
            output["duration"] = self.duration
        return output
