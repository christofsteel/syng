import tempfile
from typing import Optional
from qrcode.main import QRCode
import mpv
import os
from PIL.Image import Image


from .entry import Entry

__dirname__ = os.path.dirname(__file__)


class Player:
    def osd_size_handler(self, *args):
        if self.qr_overlay:
            self.mpv.remove_overlay(self.qr_overlay.overlay_id)

        osd_width: int = self.mpv.osd_width
        osd_height: int = self.mpv.osd_height

        x_pos = osd_width - self.qr.width - 10
        y_pos = osd_height - self.qr.height - 10

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
        if self.mpv.filename not in ["background.png", "background20perc.png"]:
            self.callback()

    def __init__(self):
        self.mpv = mpv.MPV(ytdl=True, input_default_bindings=True, input_vo_keyboard=True, osc=True)
        self.mpv.keep_open = "yes"
        self.audio = None
        self.qr_overlay = None
        qr = QRCode(box_size=5, border=1)
        qr.add_data("https://syng.rocks/")
        qr.make()
        self.qr = qr.make_image().convert("RGBA")

        self.mpv.play(
            f"{__dirname__}/static/background.png",
        )
        self.callback = lambda: None

        self.mpv.register_event_callback(self.event_handler)
        self.mpv.observe_property("eof-reached", self.eof_handler)
        self.mpv.observe_property("osd-width", self.osd_size_handler)
        self.mpv.observe_property("osd-height", self.osd_size_handler)

    def play_entry(self, entry: Entry, video: str, audio: Optional[str] = None):
        self.queue_next(entry)
        self.play(video, audio)

    def queue_next(self, entry: Entry):
        self.play_image(f"{__dirname__}/static/background20perc.png", 3)
        subtitle: str = f"""1
00:00:00,00 --> 00:05:00,00
{entry.artist} - {entry.title}
{entry.performer}"""
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            print(tmpfile.name)
            tmpfile.write(subtitle.encode())
            tmpfile.flush()
            self.mpv.sub_pos = 50
            self.mpv.sub_add(tmpfile.name)

    def play_image(self, image: str, duration: int):
        self.mpv.image_display_duration = duration
        self.mpv.keep_open = "yes"
        self.mpv.play(image)
        self.mpv.pause = False

    def play(self, video: str, audio: Optional[str] = None):
        self.audio = audio
        self.mpv.pause = True
        self.mpv.play(video)
        self.mpv.pause = False
