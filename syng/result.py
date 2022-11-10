from dataclasses import dataclass


@dataclass
class Result:
    id: str | int
    source: str
    title: str
    artist: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "artist": self.artist,
        }
