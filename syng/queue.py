"""A async queue with synchronization."""

import asyncio
from collections import deque
from collections.abc import Callable, Iterable
from typing import Any
from typing import Optional
from uuid import UUID

from .entry import Entry


class Queue:
    """A async queue with synchronization.

    This queue keeps track of the amount of entries by using a semaphore.

    :param initial_entries: Initial list of entries to add to the queue
    :type initial_entries: list[Entry]
    """

    def __init__(self, initial_entries: list[Entry]):
        """
        Construct the queue. And initialize the internal lock and semaphore.

        :param initial_entries: Initial list of entries to add to the queue
        :type initial_entries: list[Entry]
        """
        self._queue = deque(initial_entries)

        self.num_of_entries_sem = asyncio.Semaphore(len(self._queue))
        self.readlock = asyncio.Lock()

    def append(self, entry: Entry) -> None:
        """
        Append an entry to the queue, increase the semaphore.

        :param entry: The entry to add
        :type entry: Entry
        :rtype: None
        """
        self._queue.append(entry)
        self.num_of_entries_sem.release()

    def try_peek(self) -> Optional[Entry]:
        """Return the first entry in the queue, if it exists."""
        if len(self._queue) > 0:
            return self._queue[0]
        return None

    async def peek(self) -> Entry:
        """
        Return the first entry in the queue.

        If the queue is empty, wait until the queue has at least one entry.

        :returns: First entry of the queue
        :rtype: Entry
        """
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            item = self._queue[0]
            self.num_of_entries_sem.release()
        return item

    async def popleft(self) -> Entry:
        """
        Remove the first entry in the queue and return it.

        Decreases the semaphore. If the queue is empty, wait until the queue
        has at least one entry.

        :returns: First entry of the queue
        :rtype: Entry
        """
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            item = self._queue.popleft()
        return item

    def to_list(self) -> list[Entry]:
        """
        Return all entries in a list.

        This is done, so that the entries can be converted to a JSON object,
        when sending it to the web or playback client.

        :returns: A list with all the entries.
        :rtype: list[Entry]
        """
        return list(self._queue)  # [item for item in self._queue]

    def update(self, uuid: UUID | str, updater: Callable[[Entry], None]) -> None:
        """
        Update entries in the queue, identified by their uuid.

        If an entry with that uuid is not in the queue, nothing happens.

        :param uuid: The uuid of the entry to update
        :type uuid: UUID | str
        :param updater: A function, that updates the entry
        :type updater: Callable[[Entry], None]
        :rtype: None
        """
        for item in self._queue:
            if item.uuid == uuid or str(item.uuid) == uuid:
                updater(item)

    def find_by_name(self, name: str) -> Optional[Entry]:
        """
        Find an entry by its performer and return it.

        :param name: The name of the performer to search for.
        :type name: str
        :returns: The entry with the performer or `None` if no such entry exists
        :rtype: Optional[Entry]
        """
        for item in self._queue:
            if item.shares_performer(name):
                return item
        return None

    def find_by_uuid(self, uuid: UUID | str) -> Optional[Entry]:
        """
        Find an entry by its uuid and return it.

        :param uuid: The uuid to search for.
        :type uuid: UUID | str
        :returns: The entry with the uuid or `None` if no such entry exists
        :rtype: Optional[Entry]
        """
        for item in self._queue:
            if item.uuid == uuid or str(item.uuid) == uuid:
                return item
        return None

    def find_by_uid(self, uid: str) -> Iterable[Entry]:
        """
        Find all entries for a given user id
        """

        for item in self._queue:
            if item.uid == uid:
                yield item

    def fold(self, func: Callable[[Entry, Any], Any], start_value: Any) -> Any:
        """Call ``func`` on each entry and accumulate the result."""
        for item in self._queue:
            start_value = func(item, start_value)
        return start_value

    async def remove(self, entry: Entry) -> None:
        """
        Remove an entry, if it exists. Decrease the semaphore.

        :param entry: The entry to remove
        :type entry: Entry
        :rtype: None
        """
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            self._queue.remove(entry)

    async def move_up(self, uuid: str) -> None:
        """
        Move an :py:class:`syng.entry.Entry` with the uuid up in the queue.

        If it is called on the first two elements, nothing will happen.

        :param uuid: The uuid of the entry.
        :type uuid: str
        :rtype: None
        """
        async with self.readlock:
            uuid_idx = 0
            for idx, item in enumerate(self._queue):
                if item.uuid == uuid or str(item.uuid) == uuid:
                    uuid_idx = idx

            if uuid_idx > 1:
                tmp = self._queue[uuid_idx]
                self._queue[uuid_idx] = self._queue[uuid_idx - 1]
                self._queue[uuid_idx - 1] = tmp

    async def move_to(self, uuid: str, target: int) -> None:
        """
        Move an :py:class:`syng.entry.Entry` with the uuid to a specific position.

        :param uuid: The uuid of the entry.
        :type uuid: str
        :param target: The target position.
        :type target: int
        :rtype: None
        """

        async with self.readlock:
            uuid_idx = 0
            for idx, item in enumerate(self._queue):
                if item.uuid == uuid or str(item.uuid) == uuid:
                    uuid_idx = idx

            if uuid_idx != target:
                entry = self._queue[uuid_idx]
                self._queue.remove(entry)

                if target > uuid_idx:
                    target = target - 1
                self._queue.insert(target, entry)
