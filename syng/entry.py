"""Module for the entry of the queue."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import re
from typing import Any
from typing import Optional
from uuid import UUID
from uuid import uuid4


@dataclass
class Entry:
    """This represents a song in the queue.

    :param ident: An identifier, that uniquely identifies the song in its
        source.
    :type ident: str
    :param source: The name of the source, this will be played from.
    :type source: str
    :param duration: The duration of the song in seconds.
    :type duration: int
    :param title: The title of the song.
    :type title: Optional[str]
    :param artist: The name of the original artist.
    :type artist: Optional[str]
    :param album: The name of the album or compilation, this particular
        version is from.
    :type album: str
    :param performer: The person, that will sing this song.
    :type performer: str
    :param failed: A flag, that indecates, that something went wrong. E.g.
        buffering was canceled, the file could not be read from disc etc.
        The exact meaning can differ from source to source. Default is false.
    :type failed: bool
    :param skip: A flag indicating, that this song is marked for skipping.
    :type skip: bool
    :param uuid: The UUID, that identifies this exact entry in the queue.
        Will be automatically assigned on creation.
    :type uuid: UUID
    :param uid: ID of the user that added this song to the queue.
    :type uid: Optional[str]
    :param started_at: The timestamp this entry began playing. ``None``, if it
        is yet to be played.
    :type started_at: Optional[float]
    """

    # pylint: disable=too-many-instance-attributes

    ident: str
    source: str
    duration: int
    title: Optional[str]
    artist: Optional[str]
    album: str
    performer: str
    failed: bool = False
    skip: bool = False
    uuid: UUID = field(default_factory=uuid4)
    uid: Optional[str] = None
    started_at: Optional[float] = None
    incomplete_data: bool = False

    def update(self, **kwargs: Any) -> None:
        """
        Update the attributes with given substitutions.

        :param \\*\\*kwargs: Keywords taken from the list of attributes.
        :type \\*\\*kwargs: Any
        :rtype: None
        """
        self.__dict__.update(kwargs)

    def shares_performer(self, other_performer: str) -> bool:
        """
        Check if this entry shares a performer with another entry.

        :param other_performer: The performer to check against.
        :type other_performer: str
        :return: True if the performers intersect, False otherwise.
        :rtype: bool
        """

        def normalize(performers: str) -> set[str]:
            return set(
                filter(
                    lambda x: len(x) > 0 and x not in ["der", "die", "das", "alle", "und"],
                    re.sub(
                        r"[^a-zA-Z0-9\s]",
                        "",
                        re.sub(
                            r"\s",
                            " ",
                            performers.lower().replace(".", " ").replace(",", " "),
                        ),
                    ).split(" "),
                )
            )

        e1_split_names = normalize(self.performer)
        e2_split_names = normalize(other_performer)

        return len(e1_split_names.intersection(e2_split_names)) > 0
