from typing import Any, Callable, Iterable, Optional, Protocol

from PIL.Image import Image

class ShutdownError(Exception):
    pass

class Unregisterable(Protocol):
    def unregister(self) -> None: ...

class ImageOverlay:
    overlay_id: int
    def remove(self) -> None: ...

class MpvEvent:
    def as_dict(self) -> dict[str, bytes]: ...

class MPV:
    pause: bool
    keep_open: str
    image_display_duration: int
    sub_pos: int
    osd_width: str
    osd_height: str
    title: str

    def __init__(
        self, ytdl: bool, input_default_bindings: bool, input_vo_keyboard: bool, osc: bool
    ) -> None: ...
    def terminate(self) -> None: ...
    def play(self, file: str) -> None: ...
    def playlist_append(self, file: str) -> None: ...
    def wait_for_property(self, property: str) -> None: ...
    def playlist_next(self) -> None: ...
    def audio_add(self, file: str) -> None: ...
    def wait_for_event(self, event: str) -> None: ...
    def python_stream(
        self, stream_name: str
    ) -> Callable[[Callable[[], Iterable[bytes]]], Unregisterable]: ...
    def sub_add(self, file: str) -> None: ...
    def create_image_overlay(self, image: Image, pos: tuple[int, int]) -> ImageOverlay: ...
    def remove_overlay(self, overlay_id: int) -> None: ...
    def observe_property(self, property: str, callback: Callable[[str, Any], None]) -> None: ...
    def loadfile(
        self, file: str, audio_file: Optional[str] = None, sub_file: Optional[str] = None
    ) -> None: ...
    def register_event_callback(self, callback: Callable[..., Any]) -> None: ...
    def __setitem__(self, key: str, value: str) -> None: ...
    def __getitem__(self, key: str) -> str: ...