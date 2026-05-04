import json
from datetime import datetime, timezone
from uuid import uuid4


# ──────────────────────────────────────────────
# 1. 事件注册与基类
# ──────────────────────────────────────────────
_event_registry = {}

def register_event(cls):
    """装饰器：将事件类注册到全局字典中，用于反序列化。"""
    _event_registry[cls.__name__] = cls
    return cls


class Event:
    """所有事件的基类，提供序列化 / 反序列化通用逻辑。"""
    def __init__(self, aggregate_id, event_id=None, timestamp=None):
        self.event_id = event_id or str(uuid4())
        self.aggregate_id = aggregate_id
        self.timestamp = timestamp or datetime.now(timezone.utc)

    def to_dict(self):
        return {
            'event_type': type(self).__name__,
            'event_id': self.event_id,
            'aggregate_id': self.aggregate_id,
            'timestamp': self.timestamp.isoformat(),
            'payload': self.payload()
        }

    @staticmethod
    def from_dict(d):
        event_type = d['event_type']
        cls = _event_registry[event_type]
        return cls.from_payload(
            aggregate_id=d['aggregate_id'],
            payload=d['payload'],
            event_id=d['event_id'],
            timestamp=datetime.fromisoformat(d['timestamp'])
        )

    def payload(self):
        """子类必须实现，返回需要持久化的业务数据字典。"""
        raise NotImplementedError

    @classmethod
    def from_payload(cls, aggregate_id, payload, event_id, timestamp):
        """子类必须实现，根据 payload 构造事件实例。"""
        raise NotImplementedError


# ──────────────────────────────────────────────
# 2. 内存事件存储
# ──────────────────────────────────────────────
class ConcurrencyError(Exception):
    """乐观锁冲突异常。"""
    pass


class EventStore:
    """基于内存的事件存储，支持乐观并发控制。"""
    def __init__(self):
        self._streams = {}          # aggregate_id -> list of Event
        self._snapshots = {}        # (optional) 可扩展快照

    def save_events(self, aggregate_id, events, expected_version):
        """保存新事件。expected_version 应为当前已持久化的事件数量。"""
        stream = self._streams.get(aggregate_id, [])
        if len(stream) != expected_version:
            raise ConcurrencyError(
                f"Concurrency conflict on '{aggregate_id}': "
                f"expected version {expected_version}, actual {len(stream)}"
            )
        self._streams[aggregate_id] = stream + list(events)

    def get_events(self, aggregate_id, after_version=None):
        """获取某个聚合的事件流，可选择从指定版本之后开始。"""
        stream = self._streams.get(aggregate_id, [])
        if after_version is not None:
            return stream[after_version:]
        return list(stream)


# ──────────────────────────────────────────────
# 3. 聚合根基类（重放机制）
# ──────────────────────────────────────────────
class AggregateRoot:
    """支持事件溯源的聚合根基类。"""
    def __init__(self, aggregate_id):
        self.aggregate_id = aggregate_id
        self.version = 0          # 已应用的事件总数
        self.changes = []         # 尚未持久化的事件

    def apply_change(self, event):
        """内部调用：应用事件并暂存到 changes 列表。"""
        self._apply(event)
        self.changes.append(event)
        self.version += 1

    def _apply(self, event):
        """根据事件类型名动态调用 apply_{EventName} 方法。"""
        handler_name = f'apply_{type(event).__name__}'
        handler = getattr(self, handler_name, None)
        if handler:
            handler(event)

    def load_from_history(self, events):
        """从历史事件流重建聚合状态（重放）。"""
        for event in events:
            self._apply(event)
            self.version += 1

    @classmethod
    def from_history(cls, aggregate_id, events):
        """工厂方法：根据事件历史创建聚合实例。"""
        obj = cls(aggregate_id)
        obj.load_from_history(events)
        return obj

    def clear_changes(self):
        """持久化后清空未提交事件列表。"""
        self.changes.clear()

    @property
    def expected_version(self):
        """持久化时应传入的 version（即当前已持久化的事件数）。"""
        return self.version - len(self.changes)


# ──────────────────────────────────────────────
# 4. 银行账户领域事件
# ──────────────────────────────────────────────
@register_event
class AccountOpened(Event):
    def __init__(self, aggregate_id, owner, initial_balance, event_id=None, timestamp=None):
        super().__init__(aggregate_id, event_id, timestamp)
        self.owner = owner
        self.initial_balance = initial_balance

    def payload(self):
        return {'owner': self.owner, 'initial_balance': self.initial_balance}

    @classmethod
    def from_payload(cls, aggregate_id, payload, event_id, timestamp):
        return cls(aggregate_id, payload['owner'], payload['initial_balance'], event_id, timestamp)


@register_event
class MoneyDeposited(Event):
    def __init__(self, aggregate_id, amount, event_id=None, timestamp=None):
        super().__init__(aggregate_id, event_id, timestamp)
        self.amount = amount

    def payload(self):
        return {'amount': self.amount}

    @classmethod
    def from_payload(cls, aggregate_id, payload, event_id, timestamp):
        return cls(aggregate_id, payload['amount'], event_id, timestamp)


@register_event
class MoneyWithdrawn(Event):
    def __init__(self, aggregate_id, amount, event_id=None, timestamp=None):
        super().__init__(aggregate_id, event_id, timestamp)
        self.amount = amount

    def payload(self):
        return {'amount': self.amount}

    @classmethod
    def from_payload(cls, aggregate_id, payload, event_id, timestamp):
        return cls(aggregate_id, payload['amount'], event_id, timestamp)


@register_event
class AccountFrozen(Event):
    def __init__(self, aggregate_id, event_id=None, timestamp=None):
        super().__init__(aggregate_id, event_id, timestamp)

    def payload(self):
        return {}

    @classmethod
    def from_payload(cls, aggregate_id, payload, event_id, timestamp):
        return cls(aggregate_id, event_id, timestamp)


# ──────────────────────────────────────────────
# 5. 银行账户聚合
# ──────────────────────────────────────────────
class Account(AggregateRoot):
    """银行账户聚合根，支持存款、取款、冻结。"""
    def __init__(self, account_id):
        super().__init__(account_id)
        self.owner = None
        self.balance = 0
        self.frozen = False

    # ── 工厂方法：创建新账户 ──
    @classmethod
    def create(cls, account_id, owner, initial_balance=0):
        account = cls(account_id)
        account.apply_change(AccountOpened(account_id, owner, initial_balance))
        return account

    # ── 命令 ──
    def deposit(self, amount):
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        if self.frozen:
            raise ValueError("Cannot deposit into a frozen account")
        self.apply_change(MoneyDeposited(self.aggregate_id, amount))

    def withdraw(self, amount):
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if self.frozen:
            raise ValueError("Cannot withdraw from a frozen account")
        if self.balance < amount:
            raise ValueError("Insufficient balance")
        self.apply_change(MoneyWithdrawn(self.aggregate_id, amount))

    def freeze(self):
        if self.frozen:
            raise ValueError("Account is already frozen")
        self.apply_change(AccountFrozen(self.aggregate_id))

    # ── 事件应用方法（状态变更） ──
    def apply_AccountOpened(self, event):
        self.owner = event.owner
        self.balance = event.initial_balance

    def apply_MoneyDeposited(self, event):
        self.balance += event.amount

    def apply_MoneyWithdrawn(self, event):
        self.balance -= event.amount

    def apply_AccountFrozen(self, event):
        self.frozen = True


# ──────────────────────────────────────────────
# 6. 使用示例
# ──────────────────────────────────────────────
if __name__ == "__main__":
    store = EventStore()
    
    # 创建账户
    account = Account.create("acc-1", "Alice", 100)
    print(f"Opened:   owner={account.owner}, balance={account.balance}, version={account.version}")
    store.save_events("acc-1", account.changes, account.expected_version)
    account.clear_changes()

    # 存款 50
    account.deposit(50)
    print(f"Deposit:  balance={account.balance}, version={account.version}")
    store.save_events("acc-1", account.changes, account.expected_version)
    account.clear_changes()

    # 取款 30
    account.withdraw(30)
    print(f"Withdraw: balance={account.balance}, version={account.version}")
    store.save_events("acc-1", account.changes, account.expected_version)
    account.clear_changes()

    # 冻结账户
    account.freeze()
    print(f"Freeze:   frozen={account.frozen}, version={account.version}")
    store.save_events("acc-1", account.changes, account.expected_version)
    account.clear_changes()

    # 试图存款 → 应抛出异常
    try:
        account.deposit(20)
    except ValueError as e:
        print(f"Deposit after freeze error: {e}")

    # ── 从事件存储重建账户 ──
    events = store.get_events("acc-1")
    reconstructed = Account.from_history("acc-1", events)
    print(f"\nReconstructed from store:")
    print(f"  owner={reconstructed.owner}, balance={reconstructed.balance}, frozen={reconstructed.frozen}, version={reconstructed.version}")

    # ── 验证事件序列化 / 反序列化 ──
    event_dicts = [e.to_dict() for e in events]
    restored_events = [Event.from_dict(d) for d in event_dicts]
    replayed = Account.from_history("acc-1", restored_events)
    print(f"Replayed from serialized events: balance={replayed.balance}, frozen={replayed.frozen}")