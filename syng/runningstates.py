from asyncio import Lock
from enum import Enum

from syng.log import logger


class Lifecycle(Enum):
    STARTING = 0
    STARTED = 1
    ENDING = 2
    ENDED = 3


class RunningState:
    __connection_state__ = Lifecycle.ENDED
    __mpv_state__ = Lifecycle.ENDED
    __client_running__ = Lifecycle.ENDED

    def __init__(self) -> None:
        self.__connection_lock__ = Lock()
        self.__mpv_lock__ = Lock()
        self.__client_lock__ = Lock()

    async def set_connection_state(self, state: Lifecycle) -> None:
        async with self.__connection_lock__:
            self.__connection_state__ = state
            logger.debug("Connection State: %s", self.__connection_state__)

    def set_connection_state_no_lock(self, state: Lifecycle) -> None:
        self.__connection_state__ = state
        logger.debug("Connection State: %s", self.__connection_state__)

    async def set_mpv_state(self, state: Lifecycle) -> None:
        async with self.__mpv_lock__:
            self.__mpv_state__ = state
            logger.debug("MPV State: %s", self.__mpv_state__)

    def set_mpv_state_no_lock(self, state: Lifecycle) -> None:
        self.__mpv_state__ = state
        logger.debug("mpv State: %s", self.__mpv_state__)

    async def set_client_state(self, state: Lifecycle) -> None:
        async with self.__client_lock__:
            self.__client_state__ = state
            logger.debug("Client State: %s", self.__client_state__)

    def set_client_state_no_lock(self, state: Lifecycle) -> None:
        self.__client_state__ = state
        logger.debug("client State: %s", self.__client_state__)

    async def connection_is(self, states: list[Lifecycle]) -> bool:
        async with self.__connection_lock__:
            return self.__connection_state__ in states

    async def mpv_is(self, states: list[Lifecycle]) -> bool:
        async with self.__mpv_lock__:
            return self.__mpv_state__ in states

    async def client_is(self, states: list[Lifecycle]) -> bool:
        async with self.__client_lock__:
            return self.__client_state__ in states
