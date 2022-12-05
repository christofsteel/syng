"""Module for search results."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import os.path


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

    @staticmethod
    def from_filename(filename: str, source: str) -> Optional[Result]:
        """
        Infere most attributes from the filename.

        The filename must be in this form::

            {artist} - {title} - {album}.cdg

        Although the extension (cdg) is not required

        If parsing failes, ``None`` is returned. Otherwise a Result object with
        those attributes is created.

        :param filename: The filename to parse
        :type filename: str
        :param source: The name of the source
        :type source: str
        :return: see above
        :rtype: Optional[Result]
        """
        try:
            splitfile = os.path.basename(filename[:-4]).split(" - ")
            ident = filename
            artist = splitfile[0].strip()
            title = splitfile[1].strip()
            album = splitfile[2].strip()
            return Result(ident, source, title, artist, album)
        except IndexError:
            return None
