import asyncio
import locale
import sys
from typing import Iterable, Optional, cast
from qrcode.main import QRCode
import mpv
import os


from .entry import Entry

__dirname__ = os.path.dirname(__file__)


class Player:
    def __init__(self) -> None:
        locale.setlocale(locale.LC_ALL, "C")
        self.mpv = mpv.MPV(ytdl=True, input_default_bindings=True, input_vo_keyboard=True, osc=True)
        self.mpv.keep_open = "yes"
        self.qr_overlay: Optional[mpv.ImageOverlay] = None
        qr = QRCode(box_size=5, border=1)
        qr.add_data("https://syng.rocks/")
        qr.make()
        self.qr = qr.make_image().convert("RGBA")

        self.mpv.play(
            f"{__dirname__}/static/background.png",
        )

        self.default_options = {
            "scale": "bilinear",
        }

        self.mpv.observe_property("osd-width", self.osd_size_handler)
        self.mpv.observe_property("osd-height", self.osd_size_handler)

    def osd_size_handler(self, attribute: str, value: int) -> None:
        if self.qr_overlay:
            self.mpv.remove_overlay(self.qr_overlay.overlay_id)

        osd_width: int = cast(int, self.mpv.osd_width)
        osd_height: int = cast(int, self.mpv.osd_height)

        x_pos = osd_width - self.qr.width - 10
        y_pos = osd_height - self.qr.height - 10

        self.qr_overlay = self.mpv.create_image_overlay(self.qr, pos=(x_pos, y_pos))

    async def queue_next(self, entry: Entry) -> None:
        loop = asyncio.get_running_loop()
        self.play_image(f"{__dirname__}/static/background20perc.png", 3)

        frame = sys._getframe()
        stream_name = f"__python_mpv_play_generator_{hash(frame)}"

        @self.mpv.python_stream(stream_name)
        def preview() -> Iterable[bytes]:
            subtitle: str = f"""1
00:00:00,00 --> 00:05:00,00
{entry.artist} - {entry.title}
{entry.performer}"""
            yield subtitle.encode()
            preview.unregister()

        self.mpv.sub_pos = 50
        self.mpv.sub_add(f"python://{stream_name}")

        await loop.run_in_executor(None, self.mpv.wait_for_property, "eof-reached")

    def play_image(self, image: str, duration: int) -> None:
        for property, value in self.default_options.items():
            self.mpv[property] = value
        self.mpv.image_display_duration = duration
        self.mpv.keep_open = "yes"
        self.mpv.play(image)
        self.mpv.pause = False

    async def play(
        self,
        video: str,
        audio: Optional[str] = None,
        override_options: Optional[dict[str, str]] = None,
    ) -> None:
        if override_options is None:
            override_options = {}
        for property, value in self.default_options.items():
            self.mpv[property] = value

        for property, value in override_options.items():
            self.mpv[property] = value

        loop = asyncio.get_running_loop()
        self.mpv.pause = True
        self.mpv.play(video)
        await loop.run_in_executor(None, self.mpv.wait_for_event, "file-loaded")
        if audio:
            self.mpv.audio_add(audio)
        self.mpv.pause = False
        await loop.run_in_executor(None, self.mpv.wait_for_property, "eof-reached")
        self.mpv.play(f"{__dirname__}/static/background.png")

    def skip_current(self) -> None:
        self.mpv.playlist_append(
            f"{__dirname__}/static/background.png",
        )
        self.mpv.playlist_next()
