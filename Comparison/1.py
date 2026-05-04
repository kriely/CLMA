import threading
from collections import deque
import time

class Full(Exception):
    """Raised when the queue is full and no space is available."""
    pass

class Empty(Exception):
    """Raised when the queue is empty and no item is available."""
    pass

class BoundedBlockingQueue:
    """A thread-safe bounded blocking queue with timeout support."""
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("Capacity must be positive")
        self.capacity = capacity
        self.queue = deque()
        # Use a single lock shared by two conditions
        self.lock = threading.Lock()
        self.not_empty = threading.Condition(self.lock)
        self.not_full = threading.Condition(self.lock)

    def qsize(self) -> int:
        """Return the approximate size of the queue."""
        with self.lock:
            return len(self.queue)

    def full(self) -> bool:
        """Return True if the queue is full."""
        with self.lock:
            return len(self.queue) == self.capacity

    def empty(self) -> bool:
        """Return True if the queue is empty."""
        with self.lock:
            return len(self.queue) == 0

    def put(self, item, block: bool = True, timeout: float = None) -> None:
        """
        Put an item into the queue.

        If block is True and timeout is None, blocks until a slot is available.
        If block is True and timeout is a positive number, blocks at most timeout
        seconds and raises Full if no slot becomes available.
        If block is False, raises Full if the queue is full immediately.
        """
        with self.not_full:
            if not block:
                if len(self.queue) >= self.capacity:
                    raise Full
            else:
                remaining = timeout
                while len(self.queue) >= self.capacity:
                    if remaining is not None and remaining <= 0:
                        raise Full
                    start = time.monotonic()
                    self.not_full.wait(remaining)
                    elapsed = time.monotonic() - start
                    if remaining is not None:
                        remaining -= elapsed
            # Space is now available
            self.queue.append(item)
            self.not_empty.notify()

    def get(self, block: bool = True, timeout: float = None):
        """
        Remove and return an item from the queue.

        If block is True and timeout is None, blocks until an item is available.
        If block is True and timeout is a positive number, blocks at most timeout
        seconds and raises Empty if no item becomes available.
        If block is False, raises Empty if the queue is empty immediately.
        """
        with self.not_empty:
            if not block:
                if len(self.queue) == 0:
                    raise Empty
            else:
                remaining = timeout
                while len(self.queue) == 0:
                    if remaining is not None and remaining <= 0:
                        raise Empty
                    start = time.monotonic()
                    self.not_empty.wait(remaining)
                    elapsed = time.monotonic() - start
                    if remaining is not None:
                        remaining -= elapsed
            # An item is now available
            item = self.queue.popleft()
            self.not_full.notify()
            return item