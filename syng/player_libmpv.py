"""Capsules the mpv based player."""

import asyncio
import locale
import os
import sys
from collections.abc import Callable, Iterable
from typing import cast

import mpv
from qrcode.main import QRCode

from syng.config import ClientConfig, QRPosition
from syng.entry import Entry
from syng.runningstates import Lifecycle, RunningState


class Player:
    """MPV based player to play the media.

    This communicates with mpv through libmpv. The player itself runs in a seperate process.
    It also generates and shows a qr code in a corner.

    The player window should be open for as long, as a connection to the server exists. If no song
    is currently playing, it will show a static image. Before every song, a "Next up" screen is
    shown for some seconds. When the window is closed, the client also disconnects.

    At the end of every song, the next song is previewed through a pop up.
    """

    def __init__(
        self,
        config: ClientConfig,
        quit_callback: Callable[[], None],
        connection_state: RunningState,
        queue: list[Entry] | None = None,
    ) -> None:
        """Initialize the class and set internal attributes.

        This sets the livecycle of MPV to STARTING.

        Args:
            config: The configuration of the client. This is mainly used to render the qr code
            quit_callback: Function, that is called, when the player window is closed.
            connection_state: Reference to the state of the components of syng. Will be
                manipulated by this class.
            queue: Reference to the queue of the client for the "next up" pop-up

        """
        locale.setlocale(locale.LC_ALL, "C")
        qr_string = f"{config.general.server}/{config.general.room}"
        self.connection_state = connection_state
        self.connection_state.set_mpv_state_no_lock(Lifecycle.STARTING)

        self.queue = queue if queue is not None else []
        self.base_dir = f"{os.path.dirname(__file__)}/static"
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            self.base_dir = sys._MEIPASS
        self.mpv: mpv.MPV | None = None
        self.qr_overlay: mpv.ImageOverlay | None = None
        self.qr_box_size = 1 if config.ui.qr_box_size < 1 else config.ui.qr_box_size
        self.qr_position = config.ui.qr_position
        self.next_up_time = config.ui.next_up_time
        self.update_qr(
            qr_string,
        )

        self.default_options = {
            "scale": "bilinear",
        }
        self.quit_callback = quit_callback
        self.callback_audio_load: str | None = None

    def start(self) -> None:
        """Start the mpv process.

        This also sets and registers some internal callbacks. At the end of the method the
        lifecycle of MPV ist STARTED.
        """
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
        self.connection_state.set_mpv_state_no_lock(Lifecycle.STARTED)

    def playtime_remaining_handler(self, attribute: str, value: float) -> None:
        """Update the "next up" pop-up, if at the end of a song.

        This handles animation by setting the y position according to the playtime remaining.
        If this is the last song in the queue, this does nothing.

        Args:
            attribute: Unused
            value: `playtime-remaining` as a float in seconds.

        """
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
            data=f"{{\\pos({1920 // 2},{self.next_up_y_pos})}}Next Up: {entry.short_str()}",
            res_x=1920,
            res_y=1080,
            z=0,
            hidden=hidden,
            format="ass-events",
        )

    def event_callback(self, event: mpv.MpvEvent) -> None:
        """Handle events of MPV.

        This listens on the ``shutdown`` and ``file-loaded`` event.
        For ``shutdown``, it calls the quit_callback function, for ``file-loaded``, it ensures, that
        accompaning audio tracks are also loaded, when an entry has a seperate audio and
        video file.

        Args:
            event: MPV event.

        """
        e = event.as_dict()
        if e["event"] == b"shutdown":
            self.quit_callback()
        elif (
            e["event"] == b"file-loaded"
            and self.callback_audio_load is not None
            and self.mpv is not None
        ):
            self.mpv.audio_add(self.callback_audio_load)
            self.callback_audio_load = None

    def update_qr(self, qr_string: str) -> None:
        """Update the QR code.

        Args:
            qr_string: String, that will be shown as the qr code.

        """
        qr = QRCode(box_size=self.qr_box_size, border=1)
        qr.add_data(qr_string)
        qr.make()
        self.qr = qr.make_image().convert("RGBA")

    def osd_size_handler(self, attribute: str, value: int) -> None:
        """Handle resize events of the player.

        Ensures, that the position of the qr code is always in a corner.

        Args:
            attribute: Unused
            value: Unused

        """
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
        """Generate and show the "next up" screen.

        This is done by showing a static image and printing subtitles with the appropriate
        information in the middle of the screen, for a (configurable) number of seconds.

        This function blocks, until the screen is done showing.

        Args:
            entry: The entry, that is next.

        """
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

    def play_image(self, image: str, duration: int, sub_file: str | None = None) -> None:
        """Play a static image.

        Args:
            image: Path to the image
            duration: Duration to show the image
            sub_file: Path to a subtitle file, or ``None``

        """
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
        audio: str | None = None,
        override_options: dict[str, str] | None = None,
    ) -> None:
        """Play a video file.

        If given, use ``audio`` as the audio track. Otherwise use the audio from the video.

        Args:
            video: Path to the video file
            audio: Path to the audio file or ``None``
            override_options: Dictionary with mpv configurations, that will be applied for this
                playback, or ``None``

        """
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
        """Skip the currently playing entry."""
        if self.mpv is None:
            print("MPV is not initialized", file=sys.stderr)
            return

        self.mpv.image_display_duration = 0
        self.mpv.play(
            f"{self.base_dir}/background.png",
        )
