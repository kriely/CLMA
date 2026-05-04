import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Type


# ===================== 事件基类 =====================
class Event:
    """领域事件基类"""
    def __init__(self, aggregate_id: str, event_id: Optional[str] = None,
                 timestamp: Optional[str] = None):
        self.aggregate_id = aggregate_id
        self.event_id = event_id or str(uuid.uuid4())
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'event_type': self.__class__.__name__,
            'aggregate_id': self.aggregate_id,
            'event_id': self.event_id,
            'timestamp': self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """从字典反序列化（需要子类覆盖或使用注册表）"""
        # 默认实现：通过 event_type 找到正确的子类
        event_type = data['event_type']
        if event_type in _event_registry:
            return _event_registry[event_type].from_dict(data)
        raise ValueError(f"Unknown event type: {event_type}")


# 事件类型注册表（用于反序列化）
_event_registry: Dict[str, Type[Event]] = {}


def register_event(cls: Type[Event]) -> Type[Event]:
    """装饰器：将事件类注册到全局注册表"""
    _event_registry[cls.__name__] = cls
    return cls


# ===================== 具体事件 =====================
@register_event
class Deposited(Event):
    def __init__(self, aggregate_id: str, amount: float,
                 event_id=None, timestamp=None):
        super().__init__(aggregate_id, event_id, timestamp)
        self.amount = amount

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data['amount'] = self.amount
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Deposited':
        return cls(
            aggregate_id=data['aggregate_id'],
            amount=data['amount'],
            event_id=data.get('event_id'),
            timestamp=data.get('timestamp')
        )


@register_event
class Withdrawn(Event):
    def __init__(self, aggregate_id: str, amount: float,
                 event_id=None, timestamp=None):
        super().__init__(aggregate_id, event_id, timestamp)
        self.amount = amount

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data['amount'] = self.amount
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Withdrawn':
        return cls(
            aggregate_id=data['aggregate_id'],
            amount=data['amount'],
            event_id=data.get('event_id'),
            timestamp=data.get('timestamp')
        )


@register_event
class Frozen(Event):
    def __init__(self, aggregate_id: str, reason: str = "",
                 event_id=None, timestamp=None):
        super().__init__(aggregate_id, event_id, timestamp)
        self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data['reason'] = self.reason
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Frozen':
        return cls(
            aggregate_id=data['aggregate_id'],
            reason=data.get('reason', ''),
            event_id=data.get('event_id'),
            timestamp=data.get('timestamp')
        )


@register_event
class Unfrozen(Event):
    def __init__(self, aggregate_id: str, reason: str = "",
                 event_id=None, timestamp=None):
        super().__init__(aggregate_id, event_id, timestamp)
        self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data['reason'] = self.reason
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Unfrozen':
        return cls(
            aggregate_id=data['aggregate_id'],
            reason=data.get('reason', ''),
            event_id=data.get('event_id'),
            timestamp=data.get('timestamp')
        )


# ===================== 内存事件存储 =====================
class EventStore:
    """内存事件存储，支持乐观锁"""
    def __init__(self):
        # 按 aggregate_id 存储事件列表
        self._events: Dict[str, List[Event]] = {}

    def save_events(self, aggregate_id: str, events: List[Event],
                    expected_version: int) -> None:
        """
        保存事件列表，使用乐观锁。
        expected_version 是当前聚合根已持久化的事件数量。
        """
        current_events = self._events.get(aggregate_id, [])
        if len(current_events) != expected_version:
            raise ConcurrencyException(
                f"Version conflict for aggregate {aggregate_id}: "
                f"expected {expected_version}, actual {len(current_events)}"
            )
        # 追加新事件
        self._events.setdefault(aggregate_id, []).extend(events)

    def get_events(self, aggregate_id: str) -> List[Event]:
        """获取指定聚合的所有事件（按存储顺序）"""
        return list(self._events.get(aggregate_id, []))

    def get_event_count(self, aggregate_id: str) -> int:
        """获取已存储的事件数量"""
        return len(self._events.get(aggregate_id, []))


class ConcurrencyException(Exception):
    """并发冲突异常"""
    pass


# ===================== 聚合根基类 =====================
class AggregateRoot:
    """聚合根基类，提供事件重放和未提交事件管理"""
    def __init__(self, aggregate_id: str):
        self.id = aggregate_id
        self.version = 0
        self.uncommitted_events: List[Event] = []

    def _apply(self, event: Event) -> None:
        """应用事件到内部状态，由子类实现具体逻辑"""
        raise NotImplementedError

    def apply_event(self, event: Event) -> None:
        """应用事件并增加版本（用于重放历史）"""
        self._apply(event)
        self.version += 1

    def apply_and_append(self, event: Event) -> None:
        """
        应用新生成的业务事件，并添加到未提交列表。
        注意：不增加 version，因为还未持久化。
        """
        self._apply(event)
        self.uncommitted_events.append(event)

    @classmethod
    def load_from_history(cls, aggregate_id: str,
                          events: List[Event]) -> 'AggregateRoot':
        """从事件历史重建聚合根"""
        obj = cls(aggregate_id)
        for event in events:
            obj.apply_event(event)
        # 确保 version 等于已重放事件数
        assert obj.version == len(events)
        return obj

    def to_dict(self) -> Dict[str, Any]:
        """可选的序列化方法，用于调试"""
        return {
            'id': self.id,
            'version': self.version,
            'state': self._state_to_dict(),
        }

    def _state_to_dict(self) -> Dict[str, Any]:
        """子类重写以导出状态"""
        return {}


# ===================== 银行账户聚合根 =====================
class BankAccount(AggregateRoot):
    def __init__(self, aggregate_id: str):
        super().__init__(aggregate_id)
        self.balance: float = 0.0
        self.is_frozen: bool = False

    def _apply(self, event: Event) -> None:
        if isinstance(event, Deposited):
            self.balance += event.amount
        elif isinstance(event, Withdrawn):
            self.balance -= event.amount
        elif isinstance(event, Frozen):
            self.is_frozen = True
        elif isinstance(event, Unfrozen):
            self.is_frozen = False
        else:
            raise ValueError(f"Unknown event type: {type(event)}")

    # ---- 业务命令 ----
    def deposit(self, amount: float) -> None:
        """存款"""
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        # 冻结期间也可以存款（业务规则可调整）
        event = Deposited(aggregate_id=self.id, amount=amount)
        self.apply_and_append(event)

    def withdraw(self, amount: float) -> None:
        """取款"""
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if self.is_frozen:
            raise ValueError("Account is frozen, cannot withdraw")
        if self.balance < amount:
            raise ValueError("Insufficient balance")
        event = Withdrawn(aggregate_id=self.id, amount=amount)
        self.apply_and_append(event)

    def freeze(self, reason: str = "") -> None:
        """冻结账户"""
        if self.is_frozen:
            raise ValueError("Account already frozen")
        event = Frozen(aggregate_id=self.id, reason=reason)
        self.apply_and_append(event)

    def unfreeze(self, reason: str = "") -> None:
        """解冻账户"""
        if not self.is_frozen:
            raise ValueError("Account is not frozen")
        event = Unfrozen(aggregate_id=self.id, reason=reason)
        self.apply_and_append(event)

    def _state_to_dict(self) -> Dict[str, Any]:
        return {
            'balance': self.balance,
            'is_frozen': self.is_frozen,
        }


# ===================== 使用示例 =====================
def main():
    # 初始化事件存储
    store = EventStore()

    # 1. 创建账户并执行操作
    account_id = "acc-001"
    account = BankAccount(account_id)

    # 存款和取款
    account.deposit(100.0)
    account.withdraw(30.0)
    account.freeze("Suspicious activity")

    # 保存未提交事件（乐观锁 expected_version = 当前已持久化版本 0）
    store.save_events(account.id, account.uncommitted_events, expected_version=0)
    account.version += len(account.uncommitted_events)
    account.uncommitted_events.clear()

    print("=== 第一次保存后 ===")
    print(f"Version: {account.version}, Balance: {account.balance}, Frozen: {account.is_frozen}")

    # 2. 再次加载账户，验证重放
    events = store.get_events(account_id)
    restored_account = BankAccount.load_from_history(account_id, events)

    print("=== 从历史重建后 ===")
    print(f"Version: {restored_account.version}, Balance: {restored_account.balance}, Frozen: {restored_account.is_frozen}")

    # 3. 继续操作：解冻并存款
    restored_account.unfreeze("False alarm")
    restored_account.deposit(200.0)

    # 保存（expected_version = 当前已持久化版本 3）
    store.save_events(restored_account.id,
                      restored_account.uncommitted_events,
                      expected_version=restored_account.version)
    restored_account.version += len(restored_account.uncommitted_events)
    restored_account.uncommitted_events.clear()

    print("=== 第二次保存后 ===")
    print(f"Version: {restored_account.version}, Balance: {restored_account.balance}, Frozen: {restored_account.is_frozen}")

    # 4. 再次完全重建
    all_events = store.get_events(account_id)
    final_account = BankAccount.load_from_history(account_id, all_events)
    print("=== 最终状态 ===")
    print(f"Version: {final_account.version}, Balance: {final_account.balance}, Frozen: {final_account.is_frozen}")

    # 5. 测试序列化/反序列化
    print("\n=== 事件序列化测试 ===")
    serialized = [event.to_dict() for event in all_events]
    print("序列化后的字典：")
    for d in serialized:
        print(json.dumps(d, indent=2))

    deserialized_events = [Event.from_dict(d) for d in serialized]
    print("\n反序列化后的事件类型：")
    for e in deserialized_events:
        print(f"  {type(e).__name__}: amount/reason = {getattr(e, 'amount', getattr(e, 'reason', 'N/A'))}")

    # 6. 测试乐观锁冲突
    print("\n=== 乐观锁冲突测试 ===")
    try:
        # 故意使用错误的 expected_version
        conflict_account = BankAccount(account_id)
        conflict_account.deposit(10)
        store.save_events(account_id, conflict_account.uncommitted_events, expected_version=0)
    except ConcurrencyException as e:
        print(f"捕获到乐观锁异常: {e}")


if __name__ == "__main__":
    main()
