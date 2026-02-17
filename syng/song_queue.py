"""A async queue with synchronization."""

import asyncio
from collections import deque
from collections.abc import Callable, Iterable
from uuid import UUID

from syng.entry import Entry


class Queue:
    """A async queue with synchronization.

    This queue keeps track of the amount of entries by using a semaphore.

    Attributes:
        initial_entries: Initial list of entries to add to the queue

    """

    def __init__(self, initial_entries: list[Entry]) -> None:
        """Construct the queue. And initialize the internal lock and semaphore.

        Args:
            initial_entries: Initial list of entries to add to the queue

        """
        self._queue = deque(initial_entries)

        self.num_of_entries_sem = asyncio.Semaphore(len(self._queue))
        self.readlock = asyncio.Lock()

    def extend(self, entries: Iterable[Entry]) -> None:
        """Extend the queue with a list of entries and increase the semaphore.

        Args:
            entries: The entries to add

        """
        for entry in entries:
            self.append(entry)

    def append(self, entry: Entry) -> None:
        """Append an entry to the queue, increase the semaphore.

        Args:
            entry: The entry to add

        """
        self._queue.append(entry)
        self.num_of_entries_sem.release()

    def try_peek(self) -> Entry | None:
        """Return the first entry in the queue, if it exists.

        Returns:
            The first entry in the queue, if it exists.

        """
        if len(self._queue) > 0:
            return self._queue[0]
        return None

    async def peek(self) -> Entry:
        """Return the first entry in the queue.

        If the queue is empty, wait until the queue has at least one entry.

        Returns:
            First entry of the queue

        """
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            item = self._queue[0]
            self.num_of_entries_sem.release()
        return item

    async def popleft(self) -> Entry:
        """Remove the first entry in the queue and return it.

        Decreases the semaphore. If the queue is empty, wait until the queue
        has at least one entry.

        Returns:
            First entry of the queue

        """
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            item = self._queue.popleft()
        return item

    def to_list(self) -> list[Entry]:
        """Return all entries in a list.

        This is done, so that the entries can be converted to a JSON object,
        when sending it to the web or playback client.

        Returns:
            A list with all the entries.

        """
        return list(self._queue)  # [item for item in self._queue]

    def update(self, uuid: UUID | str, updater: Callable[[Entry], None]) -> None:
        """Update entries in the queue, identified by their uuid.

        If an entry with that uuid is not in the queue, nothing happens.

        Args:
            uuid: The uuid of the entry to update
            updater: A function, that updates the entry

        """
        for item in self._queue:
            if item.uuid == uuid or str(item.uuid) == uuid:
                updater(item)

    def find_by_name(self, name: str) -> Entry | None:
        """Find the first entry by its performer and return it.

        Args:
            name: The name of the performer to search for.

        Returns:
            The entry with the performer or `None` if no such entry exists

        """
        for item in self._queue:
            if item.shares_performer(name):
                return item
        return None

    def find_all_by_name(self, name: str) -> Iterable[Entry]:
        """Find all entries by their performer and return them as an iterable.

        Args:
            name: The name of the performer to search for.

        Yields:
            The entries with the performer.

        """
        for item in self._queue:
            if item.shares_performer(name):
                yield item

    def find_by_uuid(self, uuid: UUID | str) -> Entry | None:
        """Find an entry by its uuid and return it.

        Args:
            uuid: The uuid to search for.

        Returns:
            The entry with the uuid or `None` if no such entry exists

        """
        for item in self._queue:
            if item.uuid == uuid or str(item.uuid) == uuid:
                return item
        return None

    def find_by_uid(self, uid: str) -> Iterable[Entry]:
        """Find all entries for a given user id.

        Args:
            uid: User id

        Yields:
            All entries for the uid

        """
        for item in self._queue:
            if item.uid == uid:
                yield item

    def fold[T](self, func: Callable[[Entry, T], T], start_value: T) -> T:
        """Call ``func`` on each entry and accumulate the result.

        Type Args:
            T: Type of the result

        Args:
            func: Folding function
            start_value: Initial Value of the accumulator

        Returns:
            Accumulated result of the fold.

        """
        for item in self._queue:
            start_value = func(item, start_value)
        return start_value

    async def remove(self, entry: Entry) -> None:
        """Remove an entry, if it exists. Decrease the semaphore.

        Args:
            entry: The entry to remove

        """
        async with self.readlock:
            await self.num_of_entries_sem.acquire()
            self._queue.remove(entry)

    async def move_up(self, uuid: str) -> None:
        """Move an :py:class:`syng.entry.Entry` with the uuid up in the queue.

        If it is called on the first two elements, nothing will happen.

        Args:
            uuid: The uuid of the entry.

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
        """Move an :py:class:`syng.entry.Entry` with the uuid to a specific position.

        Args:
            uuid: The uuid of the entry.
            target: The target position.

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
