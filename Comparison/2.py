import threading
import time
from collections import deque


class QueueFull(Exception):
    """队列已满时抛出的异常"""
    pass


class QueueEmpty(Exception):
    """队列为空时抛出的异常"""
    pass


class BoundedBlockingQueue:
    """线程安全的有界阻塞队列"""

    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._queue = deque()
        self._capacity = capacity
        self._condition = threading.Condition()   # 条件变量（内置锁）

    def put(self, item, block=True, timeout=None):
        """
        将元素放入队列。
        :param item: 待放入的元素
        :param block: 是否阻塞等待，默认为 True
        :param timeout: 阻塞等待的最大秒数，仅当 block=True 时有效
        :raises QueueFull: 队列满且不阻塞，或超时后仍无法放入
        """
        with self._condition:
            if not block:
                if len(self._queue) >= self._capacity:
                    raise QueueFull
            else:
                if timeout is None:
                    # 无限等待直到队列有空位
                    while len(self._queue) >= self._capacity:
                        self._condition.wait()
                else:
                    if timeout < 0:
                        raise ValueError("timeout must be non-negative")
                    end_time = time.time() + timeout
                    while len(self._queue) >= self._capacity:
                        remaining = end_time - time.time()
                        if remaining <= 0:
                            raise QueueFull
                        # 等待剩余时间，被通知后会重新检查条件
                        self._condition.wait(remaining)
            # 队列有空位，放入元素
            self._queue.append(item)
            # 通知可能在等待取元素的线程
            self._condition.notify()

    def get(self, block=True, timeout=None):
        """
        从队列中取出元素。
        :param block: 是否阻塞等待，默认为 True
        :param timeout: 阻塞等待的最大秒数，仅当 block=True 时有效
        :return: 队列中的元素
        :raises QueueEmpty: 队列空且不阻塞，或超时后仍无法取出
        """
        with self._condition:
            if not block:
                if len(self._queue) == 0:
                    raise QueueEmpty
            else:
                if timeout is None:
                    # 无限等待直到队列非空
                    while len(self._queue) == 0:
                        self._condition.wait()
                else:
                    if timeout < 0:
                        raise ValueError("timeout must be non-negative")
                    end_time = time.time() + timeout
                    while len(self._queue) == 0:
                        remaining = end_time - time.time()
                        if remaining <= 0:
                            raise QueueEmpty
                        self._condition.wait(remaining)
            item = self._queue.popleft()
            # 通知可能在等待放元素的线程
            self._condition.notify()
            return item

    def qsize(self):
        """返回队列当前元素个数"""
        with self._condition:
            return len(self._queue)

    def empty(self):
        """返回队列是否为空"""
        with self._condition:
            return len(self._queue) == 0

    def full(self):
        """返回队列是否已满"""
        with self._condition:
            return len(self._queue) >= self._capacity