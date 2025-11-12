import asyncio
from enum import Enum
import locale
import sys
from typing import Any, Callable, Iterable, Optional, cast
from qrcode.main import QRCode
import mpv
import os

from .entry import Entry


class QRPosition(Enum):
    TOP_LEFT = 1
    TOP_RIGHT = 2
    BOTTOM_LEFT = 3
    BOTTOM_RIGHT = 4

    @staticmethod
    def from_string(value: str) -> "QRPosition":
        match value:
            case "top-left":
                return QRPosition.TOP_LEFT
            case "top-right":
                return QRPosition.TOP_RIGHT
            case "bottom-left":
                return QRPosition.BOTTOM_LEFT
            case "bottom-right":
                return QRPosition.BOTTOM_RIGHT
            case _:
                return QRPosition.BOTTOM_RIGHT


class Player:
    def __init__(
        self,
        config: dict[str, Any],
        quit_callback: Callable[[], None],
        queue: Optional[list[Entry]] = None,
    ) -> None:
        locale.setlocale(locale.LC_ALL, "C")
        qr_string = f"{config['server']}/{config['room']}"

        self.queue = queue if queue is not None else []
        self.base_dir = f"{os.path.dirname(__file__)}/static"
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            self.base_dir = getattr(sys, "_MEIPASS")
        self.closing = False
        self.mpv: Optional[mpv.MPV] = None
        self.qr_overlay: Optional[mpv.ImageOverlay] = None
        self.qr_box_size = 1 if config["qr_box_size"] < 1 else config["qr_box_size"]
        self.qr_position = QRPosition.from_string(config["qr_position"])
        self.next_up_time = config.get("next_up_time", 20)
        self.update_qr(
            qr_string,
        )

        self.default_options = {
            "scale": "bilinear",
        }
        self.quit_callback = quit_callback
        self.callback_audio_load: Optional[str] = None

    def start(self) -> None:
        self.mpv = mpv.MPV(
            ytdl=True,
            input_default_bindings=True,
            input_vo_keyboard=True,
            osc=True,
            osd_border_style="background-box",
            osd_back_color="#E0008000",
            osd_color="#E0FFFFFF",
            osd_outline_color="#50000000",
            osd_shadow_offset=10,
            osd_align_x="center",
            osd_align_y="top",
        )
        self.next_up_overlay_id = self.mpv.allocate_overlay_id()
        self.next_up_y_pos = -120
        self.mpv.title = "Syng.Rocks! - Player"
        self.mpv.keep_open = "yes"
        self.mpv.play(
            f"{self.base_dir}/background.png",
        )
        self.mpv.observe_property("osd-width", self.osd_size_handler)
        self.mpv.observe_property("osd-height", self.osd_size_handler)
        self.mpv.observe_property("playtime-remaining", self.playtime_remaining_handler)
        self.mpv.register_event_callback(self.event_callback)

    def playtime_remaining_handler(self, attribute: str, value: float) -> None:
        if self.mpv is None:
            print("MPV is not initialized", file=sys.stderr)
            return
        hidden = value is None or value > self.next_up_time

        if len(self.queue) < 2:
            return
        if not hidden:
            if self.next_up_y_pos < 0:
                self.next_up_y_pos += 5
        else:
            self.next_up_y_pos = -120
        entry = self.queue[1]

        self.mpv.command(
            "osd_overlay",
            id=self.next_up_overlay_id,
            data=f"{{\\pos({1920 // 2},{self.next_up_y_pos})}}Next Up: {entry.artist} - {entry.title} ({entry.performer})",
            res_x=1920,
            res_y=1080,
            z=0,
            hidden=hidden,
            format="ass-events",
        )

    def event_callback(self, event: mpv.MpvEvent) -> None:
        e = event.as_dict()
        if e["event"] == b"shutdown":
            if not self.closing:
                self.closing = True
                self.quit_callback()
        elif e["event"] == b"file-loaded":
            if self.callback_audio_load is not None and self.mpv is not None:
                self.mpv.audio_add(self.callback_audio_load)
                self.callback_audio_load = None

    def update_qr(self, qr_string: str) -> None:
        qr = QRCode(box_size=self.qr_box_size, border=1)
        qr.add_data(qr_string)
        qr.make()
        self.qr = qr.make_image().convert("RGBA")

    def osd_size_handler(self, attribute: str, value: int) -> None:
        if self.mpv is None:
            print("MPV is not initialized", file=sys.stderr)
            return
        if self.qr_overlay:
            self.mpv.remove_overlay(self.qr_overlay.overlay_id)

        osd_width: int = cast(int, self.mpv.osd_width)
        osd_height: int = cast(int, self.mpv.osd_height)

        match self.qr_position:
            case QRPosition.BOTTOM_RIGHT:
                x_pos = osd_width - self.qr.width - 10
                y_pos = osd_height - self.qr.height - 10
            case QRPosition.BOTTOM_LEFT:
                x_pos = 10
                y_pos = osd_height - self.qr.height - 10
            case QRPosition.TOP_RIGHT:
                x_pos = osd_width - self.qr.width - 10
                y_pos = 10
            case QRPosition.TOP_LEFT:
                x_pos = 10
                y_pos = 10

        self.qr_overlay = self.mpv.create_image_overlay(self.qr, pos=(x_pos, y_pos))

    async def queue_next(self, entry: Entry) -> None:
        if self.mpv is None:
            print("MPV is not initialized", file=sys.stderr)
            return

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
            f"{self.base_dir}/background20perc.png", 3, sub_file=f"python://{stream_name}"
        )

        try:
            await loop.run_in_executor(None, self.mpv.wait_for_property, "eof-reached")
        except mpv.ShutdownError:
            self.quit_callback()

    def play_image(self, image: str, duration: int, sub_file: Optional[str] = None) -> None:
        if self.mpv is None:
            print("MPV is not initialized", file=sys.stderr)
            return

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
        if self.mpv is None:
            print("MPV is not initialized", file=sys.stderr)
            return

        if override_options is None:
            override_options = {}
        for property, value in self.default_options.items():
            self.mpv[property] = value

        for property, value in override_options.items():
            self.mpv[property] = value

        loop = asyncio.get_running_loop()
        self.mpv.pause = True
        if audio:
            self.callback_audio_load = audio
            self.mpv.loadfile(video)
        else:
            self.mpv.loadfile(video)
        self.mpv.pause = False
        try:
            await loop.run_in_executor(None, self.mpv.wait_for_property, "eof-reached")
            self.mpv.image_display_duration = 0
            self.mpv.play(f"{self.base_dir}/background.png")
        except mpv.ShutdownError:
            self.quit_callback()

    def skip_current(self) -> None:
        if self.mpv is None:
            print("MPV is not initialized", file=sys.stderr)
            return

        self.mpv.image_display_duration = 0
        self.mpv.play(
            f"{self.base_dir}/background.png",
        )
