"""Contains classes to set and track the lifecycle of syngs components."""

from asyncio import Lock
from enum import Enum

from syng.log import logger


class Lifecycle(Enum):
    """Representation of the lifecycle of a component.

    A component can be STARTING, STARTED, ENDING or ENDED.
    """

    STARTING = 0
    STARTED = 1
    ENDING = 2
    ENDED = 3


class RunningState:
    """Combination of lifecycles of syngs components.

    The components are:
        - The MPV player
        - The connection to the server
        - The client overall

    All components start in ENDED state.

    Access to the components is guarded by an async lock to guarantee async/thread-safety.
    """

    __connection_state__ = Lifecycle.ENDED
    __mpv_state__ = Lifecycle.ENDED
    __client_running__ = Lifecycle.ENDED

    def __init__(self) -> None:
        """Initialize the locks."""
        self.__connection_lock__ = Lock()
        self.__mpv_lock__ = Lock()
        self.__client_lock__ = Lock()

    async def set_connection_state(self, state: Lifecycle) -> None:
        """Set the connection state.

        Guarded by a connection lock.

        Args:
            state: New connection state

        """
        async with self.__connection_lock__:
            self.__connection_state__ = state
            logger.debug("Connection State: %s", self.__connection_state__)

    def set_connection_state_no_lock(self, state: Lifecycle) -> None:
        """Set the connection state.

        THIS IS THE NON-GUARDED VERSION

        Args:
            state: New connection state

        """
        self.__connection_state__ = state
        logger.debug("Connection State: %s", self.__connection_state__)

    async def set_mpv_state(self, state: Lifecycle) -> None:
        """Set the MPV state.

        Guarded by a MPV lock.

        Args:
            state: New MPV state

        """
        async with self.__mpv_lock__:
            self.__mpv_state__ = state
            logger.debug("MPV State: %s", self.__mpv_state__)

    def set_mpv_state_no_lock(self, state: Lifecycle) -> None:
        """Set the MPV state.

        THIS IS THE NON-GUARDED VERSION

        Args:
            state: New MPV state

        """
        self.__mpv_state__ = state
        logger.debug("mpv State: %s", self.__mpv_state__)

    async def set_client_state(self, state: Lifecycle) -> None:
        """Set the client state.

        Guarded by a client lock.

        Args:
            state: New client state

        """
        async with self.__client_lock__:
            self.__client_state__ = state
            logger.debug("Client State: %s", self.__client_state__)

    def set_client_state_no_lock(self, state: Lifecycle) -> None:
        """Set the client state.

        THIS IS THE NON-GUARDED VERSION

        Args:
            state: New client state

        """
        self.__client_state__ = state
        logger.debug("client State: %s", self.__client_state__)

    async def connection_is(self, states: list[Lifecycle]) -> bool:
        """Check if connection state is one of the given states.

        Guarded by a connection lock.

        Args:
            states: List of states to check against.

        Returns:
            True, if connection state is one of the states, False otherwise

        """
        async with self.__connection_lock__:
            return self.__connection_state__ in states

    async def mpv_is(self, states: list[Lifecycle]) -> bool:
        """Check if MPV state is one of the given states.

        Guarded by a MPV lock.

        Args:
            states: List of states to check against.

        Returns:
            True, if MPV state is one of the states, False otherwise

        """
        async with self.__mpv_lock__:
            return self.__mpv_state__ in states

    async def client_is(self, states: list[Lifecycle]) -> bool:
        """Check if client state is one of the given states.

        Guarded by a client lock.

        Args:
            states: List of states to check against.

        Returns:
            True, if client state is one of the states, False otherwise

        """
        async with self.__client_lock__:
            return self.__client_state__ in states
