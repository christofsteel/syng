from __future__ import annotations
from dataclasses import dataclass, field
from uuid import uuid4, UUID
from typing import TYPE_CHECKING, Any, Optional
from datetime import datetime

if TYPE_CHECKING:
    from .sources import Source


@dataclass
class Entry:
    id: str
    source: str
    duration: int
    title: str
    artist: str
    album: str
    performer: str
    failed: bool = False
    skip: bool = False
    uuid: UUID = field(default_factory=uuid4)
    started_at: Optional[float] = None

    @staticmethod
    async def from_source(performer: str, ident: str, source: Source) -> Entry:
        return await source.get_entry(performer, ident)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": str(self.uuid),
            "id": self.id,
            "source": self.source,
            "duration": self.duration,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "performer": self.performer,
            "skip": self.skip,
            "started_at": self.started_at,
        }

    @staticmethod
    def from_dict(entry_dict: dict[str, Any]) -> Entry:
        return Entry(**entry_dict)

    def update(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)
