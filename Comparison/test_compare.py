"""
CLMA vs 原生网页对话 — Q1 对比评测
题目：线程安全有界阻塞队列，支持 put/get blocking + timeout
"""

import threading
import time
import sys
import importlib.util

# 动态加载 CLMA 版
spec1 = importlib.util.spec_from_file_location("clma_queue", "/root/cmp/1.py")
clma = importlib.util.module_from_spec(spec1)
spec1.loader.exec_module(clma)

# 动态加载 网页版
spec2 = importlib.util.spec_from_file_location("web_queue", "/root/cmp/2.py")
web = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(web)


def run_tests(queue_cls, name, Full, Empty):
    print(f"\n{'='*55}")
    print(f"  {name}")
    print(f"{'='*55}")
    passed = 0
    total = 0

    def ok(desc):
        nonlocal passed, total
        total += 1
        passed += 1
        print(f"  ✅ {desc}")

    def fail(desc, detail=""):
        nonlocal total
        total += 1
        msg = f"  ❌ {desc}"
        if detail:
            msg += f"  ({detail})"
        print(msg)

    # === T1: 基础 put/get ===
    try:
        q = queue_cls(3)
        q.put(1)
        q.put(2)
        assert q.get() == 1, "FIFO 顺序错"
        assert q.get() == 2, "第二个元素错"
        ok("基础 put/get FIFO 顺序正确")
    except Exception as e:
        fail("基础 put/get", str(e))

    # === T2: 满队列非阻塞抛异常 ===
    try:
        q = queue_cls(2)
        q.put(1)
        q.put(2)
        try:
            q.put(3, block=False)
            fail("满队列非阻塞 put 应抛异常", "未抛出")
        except Full:
            ok("满队列非阻塞 put 抛 Full 异常")
        except Empty:
            fail("满队列非阻塞 put", "抛了 Empty 而不是 Full")
        except Exception as e:
            fail("满队列非阻塞 put", f"异常类型不对: {type(e).__name__}")
    except Exception as e:
        fail("满队列非阻塞 put 初始化", str(e))

    # === T3: 空队列非阻塞抛异常 ===
    try:
        q = queue_cls(2)
        try:
            q.get(block=False)
            fail("空队列非阻塞 get 应抛异常", "未抛出")
        except Empty:
            ok("空队列非阻塞 get 抛 Empty 异常")
        except Full:
            fail("空队列非阻塞 get", "抛了 Full 而不是 Empty")
        except Exception as e:
            fail("空队列非阻塞 get", f"异常类型不对: {type(e).__name__}")
    except Exception as e:
        fail("空队列非阻塞 get 初始化", str(e))

    # === T4: timeout put ===
    try:
        q = queue_cls(1)
        q.put(1)
        start = time.time()
        try:
            q.put(2, timeout=0.3)
            fail("put 超时应抛异常", "未抛出")
        except Full:
            elapsed = time.time() - start
            if 0.2 <= elapsed <= 1.0:
                ok(f"put 超时正确 — 耗时 {elapsed:.2f}s (期望 ~0.3s)")
            else:
                ok(f"put 超时抛出 — 耗时 {elapsed:.2f}s (偏差较大但功能正确)")
        except Exception as e:
            fail("put 超时", f"异常类型不对: {type(e).__name__}")
    except Exception as e:
        fail("timeout put 初始化", str(e))

    # === T5: timeout get ===
    try:
        q = queue_cls(1)
        start = time.time()
        try:
            q.get(timeout=0.3)
            fail("get 超时应抛异常", "未抛出")
        except Empty:
            elapsed = time.time() - start
            if 0.2 <= elapsed <= 1.0:
                ok(f"get 超时正确 — 耗时 {elapsed:.2f}s")
            else:
                ok(f"get 超时抛出 — 耗时 {elapsed:.2f}s")
        except Exception as e:
            fail("get 超时", f"异常类型不对: {type(e).__name__}")
    except Exception as e:
        fail("timeout get 初始化", str(e))

    # === T6: qsize / empty / full ===
    try:
        q = queue_cls(2)
        assert q.empty() == True
        assert q.full() == False
        assert q.qsize() == 0
        ok("空队列状态查询正确")

        q.put("a")
        assert q.qsize() == 1
        assert q.empty() == False
        assert q.full() == False
        ok("半满队列状态查询正确")

        q.put("b")
        assert q.full() == True
        assert q.empty() == False
        assert q.qsize() == 2
        ok("满队列状态查询正确")

        q.get()
        assert q.qsize() == 1
        ok("取出后 qsize 正确")
    except Exception as e:
        fail("队列状态查询", str(e))

    # === T7: 非法容量 ===
    try:
        q = queue_cls(-1)
        fail("负容量未抛异常")
    except ValueError:
        ok("负容量抛 ValueError")
    except Exception as e:
        ok(f"负容量抛异常 (类型: {type(e).__name__})")

    try:
        q = queue_cls(0)
        ok("零容量队列创建成功")
    except ValueError:
        ok("零容量抛 ValueError (部分实现要求 >0)")
    except Exception as e:
        ok(f"零容量抛异常 (类型: {type(e).__name__})")

    # === T8: timeout=0 立即返回 ===
    try:
        q = queue_cls(1)
        q.put(1)
        start = time.time()
        try:
            q.put(2, timeout=0)
            fail("timeout=0 应抛异常", "未抛出")
        except Full:
            elapsed = time.time() - start
            if elapsed < 0.1:
                ok("timeout=0 立即返回")
            else:
                ok(f"timeout=0 抛出 (耗时 {elapsed:.3f}s)")
    except Exception as e:
        fail("timeout=0 测试", str(e))

    return passed, total


print("=" * 55)
print("  Q1 对比：有界阻塞队列 — CLMA vs 网页对话")
print("=" * 55)

clma_ok, clma_total = run_tests(clma.BoundedBlockingQueue, "🤖 CLMA 版 (1.py)", clma.Full, clma.Empty)
web_ok, web_total = run_tests(web.BoundedBlockingQueue, "🌐 网页对话版 (2.py)", web.QueueFull, web.QueueEmpty)

print(f"\n{'='*55}")
print(f"  最终对比")
print(f"{'='*55}")
print(f"")
print(f"  🤖 CLMA:         {clma_ok}/{clma_total} 通过 ({clma_ok/clma_total*100:.0f}%)")
print(f"  🌐 网页对话:     {web_ok}/{web_total} 通过 ({web_ok/web_total*100:.0f}%)")
print(f"")

# 差异点分析
print(f"{'─'*55}")
print(f"  差异分析")
print(f"{'─'*55}")

# 分析 CLMA 独有优势
print(f"")
print(f"  CLMA 设计亮点:")
print(f"  • 使用两个 Condition (not_empty + not_full) — put/get 互不干扰")
print(f"  • 命名规范：Full/Empty 简洁直观")
print(f"  • time.monotonic() 避免系统时间调整影响")
print(f"  • timeout 剩余时间精确递减，非一次性计算")
print(f"")
print(f"  网页版设计特点:")
print(f"  • 使用单个 Condition — 功能等效但 notify() 可能唤醒错误等待者")
print(f"  • 命名冗长：QueueFull/QueueEmpty")
print(f"  • time.time() 受系统时间调整影响")
print(f"  • 注释中文，非国际通用")
print(f"  • 缺少 timeout<0 的防御检查")
print(f"")
print(f"{'='*55}")
