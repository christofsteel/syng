from __future__ import annotations
from dataclasses import dataclass, field
from uuid import uuid4, UUID


@dataclass
class Entry:
    id: str
    source: str
    duration: int
    title: str
    artist: str
    performer: str
    failed: bool = False
    uuid: UUID = field(default_factory=uuid4)

    @staticmethod
    async def from_source(performer: str, ident: str, source: Source) -> Entry:
        return await source.get_entry(performer, ident)

    def to_dict(self) -> dict:
        return {
            "uuid": str(self.uuid),
            "id": self.id,
            "source": self.source,
            "duration": self.duration,
            "title": self.title,
            "artist": self.artist,
            "performer": self.performer,
        }

    @staticmethod
    def from_dict(entry_dict):
        return Entry(**entry_dict)

    def update(self, **kwargs):
        self.__dict__.update(kwargs)
