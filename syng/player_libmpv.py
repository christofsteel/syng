from typing import Optional
from qrcode.main import QRCode
import mpv
import os
import ctypes

__dirname__ = os.path.dirname(__file__)


class Player:
    def osd_size_handler(self, *args):
        if self.qr_overlay:
            self.mpv.remove_overlay(self.qr_overlay.overlay_id)

        osd_width = self.mpv.osd_width
        osd_height = self.mpv.osd_height

        x_pos = osd_width - self.qr.width - 20
        y_pos = osd_height - self.qr.height - 20

        print(osd_width, osd_height)
        print(x_pos, y_pos)

        self.qr_overlay = self.mpv.create_image_overlay(self.qr, pos=(x_pos, y_pos))

    def event_handler(self, event):
        devent = event.as_dict()
        if devent["event"] == b"file-loaded":
            print(self.audio)
            if self.audio:
                self.mpv.audio_add(self.audio)

    def eof_handler(self, *args):
        print("EOF", args)

    def __init__(self):
        self.mpv = mpv.MPV(ytdl=True, input_default_bindings=True, input_vo_keyboard=True, osc=True)
        self.mpv.keep_open = "yes"
        self.audio = None
        self.qr_overlay = None
        qr = QRCode(box_size=10, border=2)
        qr.add_data("https://syng.rocks/")
        qr.make()
        self.qr = qr.make_image().convert("RGBA")

        self.mpv.play(
            f"{__dirname__}/static/syng.png",
        )

        self.mpv.register_event_callback(self.event_handler)
        self.mpv.observe_property("eof-reached", self.eof_handler)
        self.mpv.observe_property("osd-width", self.osd_size_handler)
        self.mpv.observe_property("osd-height", self.osd_size_handler)

    def play(self, video: str, audio: Optional[str] = None):
        self.audio = audio
        self.mpv.pause = True
        self.mpv.play(video)
        self.mpv.pause = False
