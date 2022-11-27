from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import os.path


@dataclass
class Result:
    id: str | int
    source: str
    title: str
    artist: str
    album: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
        }

    @staticmethod
    def from_filename(filename, source) -> Optional[Result]:
        try:
            splitfile = os.path.basename(filename[:-4]).split(" - ")
            ident = filename
            artist = splitfile[0].strip()
            title = splitfile[1].strip()
            album = splitfile[2].strip()
            return Result(ident, source, title, artist, album)
        except IndexError:
            return None
