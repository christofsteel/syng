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
    def __init__(self, qr_string: str, quit_callback) -> None:
        locale.setlocale(locale.LC_ALL, "C")
        self.mpv = mpv.MPV(ytdl=True, input_default_bindings=True, input_vo_keyboard=True, osc=True)
        self.mpv.title = "Syng - Player"
        self.mpv.keep_open = "yes"
        self.qr_overlay: Optional[mpv.ImageOverlay] = None
        self.update_qr(
            qr_string,
        )

        self.mpv.play(
            f"{__dirname__}/static/background.png",
        )

        self.default_options = {
            "scale": "bilinear",
        }
        self.quit_callback = quit_callback

        self.mpv.observe_property("osd-width", self.osd_size_handler)
        self.mpv.observe_property("osd-height", self.osd_size_handler)
        self.mpv.register_event_callback(self.event_callback)

    def event_callback(self, event):
        e = event.as_dict()
        if e["event"] == b"shutdown":
            self.quit_callback()

    def update_qr(self, qr_string: str) -> None:
        qr = QRCode(box_size=5, border=1)
        qr.add_data(qr_string)
        qr.make()
        self.qr = qr.make_image().convert("RGBA")

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
        self.play_image(
            f"{__dirname__}/static/background20perc.png", 3, sub_file=f"python://{stream_name}"
        )

        try:
            await loop.run_in_executor(None, self.mpv.wait_for_property, "eof-reached")
        except mpv.ShutdownError:
            self.quit_callback()

    def play_image(self, image: str, duration: int, sub_file: Optional[str] = None) -> None:
        for property, value in self.default_options.items():
            self.mpv[property] = value
        self.mpv.image_display_duration = duration
        self.mpv.keep_open = "yes"
        if sub_file:
            self.mpv.loadfile(image, sub_file=sub_file)
        else:
            self.mpv.loadfile(image)
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
        if audio:
            self.mpv.loadfile(video, audio_file=audio)
        else:
            self.mpv.loadfile(video)
        self.mpv.pause = False
        try:
            await loop.run_in_executor(None, self.mpv.wait_for_property, "eof-reached")
            self.mpv.image_display_duration = 0
            self.mpv.play(f"{__dirname__}/static/background.png")
        except mpv.ShutdownError:
            self.quit_callback()

    def skip_current(self) -> None:
        self.mpv.image_display_duration = 0
        self.mpv.play(
            f"{__dirname__}/static/background.png",
        )
        # self.mpv.playlist_next()
