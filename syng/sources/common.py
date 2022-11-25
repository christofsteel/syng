from __future__ import annotations
import asyncio


async def play_mpv(
        video: str, audio: str | None, options: list[str] = list()
) -> asyncio.subprocess.Process:
    args = ["--fullscreen", *options, video] + ([f"--audio-file={audio}"] if audio else [])

    mpv_process = asyncio.create_subprocess_exec("mpv", *args)
    return await mpv_process


def kill_mpv(mpv: asyncio.subprocess.Process):
    mpv.terminate()
