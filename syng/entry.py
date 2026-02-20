"""Module for the entry of the queue."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass
class Entry:
    """Representation of a song in the queue.

    Attributes:
        ident: An identifier, that uniquely identifies the song in its
            source.
        source: The name of the source, this will be played from.
           duration: The duration of the song in seconds.
        title: The title of the song.
        artist: The name of the original artist.
        album: The name of the album or compilation, this particular
            version is from.
        performer: The person, that will sing this song.
        collab_mode: Collaboration mode, one of 'single', 'group;, ``None``
        skip: A flag indicating, that this song is marked for skipping.
        uuid: The UUID, that identifies this exact entry in the queue.
            Will be automatically assigned on creation.
        uid: ID of the user that added this song to the queue.
        started_at: The timestamp this entry began playing. ``None``, if it
            is yet to be played.
        incomplete_data: Flag, if additional metadata needs to be read from the playbackclient.
    """

    ident: str
    source: str
    duration: int
    title: str | None
    artist: str | None
    album: str
    performer: str
    collab_mode: str | None = None
    skip: bool = False
    uuid: UUID = field(default_factory=uuid4)
    uid: str | None = None
    started_at: float | None = None
    incomplete_data: bool = False

    def short_str(self) -> str:
        """Get a short string representation of this entry.

        Returns:
            A short string representation.
        """
        return f"{self.artist} - {self.title} ({self.performer})"

    def update(self, **kwargs: Any) -> None:
        """Update the attributes with given substitutions.

        Args:
            kwargs: Keywords taken from the list of attributes.

        """
        self.__dict__.update(kwargs)

    def shares_performer(self, other_performer: str) -> bool:
        """Check if this entry shares a performer with another entry.

        Args:
            other_performer: The performer to check against.

        Returns:
            True if the performers intersect, False otherwise.

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
