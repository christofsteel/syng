import asyncio
import socketio
from traceback import print_exc

from .sources import YoutubeSource
from .entry import Entry

sio = socketio.AsyncClient()

sources = {"youtube": YoutubeSource()}

currentLock = asyncio.Semaphore(0)
state = {
    "current": None,
    "all_entries": {},
}


async def playerTask():
    """
    This task loops forever, and plays the first item in the queue in the appropriate player. Then it removes the first item in the queue and starts over. If no element is in the queue, it waits
    """

    while True:
        await sio.emit("get-next", {})
        print("Waiting for current")
        await currentLock.acquire()
        try:
            await sources[state["current"].source].play(state["current"].id)
        except Exception:
            print_exc()
        print("Finished playing")


async def bufferTask():
    pass


# class BufferThread(Thread):
#    """
#    This thread tries to buffer the first not-yet buffered entry in the queue in a loop.
#    """
#    def run(self):
#        while (True):
#            for entry in self.queue:
#                if entry.ready.is_set():
#                    continue
#                try:
#                    entry.source.buffer(entry.id)
#                except Exception:
#                    print_exc()
#                    entry.failed = True
#                entry.ready.set()
#


@sio.on("skip")
async def handle_skip():
    print("Skipping current")
    await sources[state["current"].source].skip_current()


@sio.on("next")
async def handle_next(data):
    state["current"] = Entry(**data)
    currentLock.release()
    print("released lock")


@sio.on("state")
async def handle_state(data):
    state["all_entries"] = {entry["uuid"]: Entry(**entry) for entry in data}


@sio.on("connect")
async def handle_connect():
    print("Connected to server")
    await sio.emit("register-client", {"secret": "test"})


@sio.on("register-client")
async def handle_register(data):
    if data["success"]:
        print("Registered")
        asyncio.create_task(playerTask())
        asyncio.create_task(bufferTask())
    else:
        print("Registration failed")
        await sio.disconnect()


async def main():
    await sio.connect("http://127.0.0.1:8080")
    await sio.wait()


if __name__ == "__main__":
    asyncio.run(main())
