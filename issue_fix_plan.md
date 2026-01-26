# AethelumCoreLite 项目质量改进计划

## 概述

本计划旨在解决 AethelumCoreLite 项目中的并发安全性问题和依赖可复现性问题，全面提升系统的稳定性和可维护性。

**用户选择的改进重点**：
- ✅ 并发与线程安全性（高危）
- ✅ 依赖可复现性
- ✅ 全面修复方案
- ✅ 增强README（不生成独立文档）

---

## 一、并发安全性修复（全面修复）

### 1.1 高危问题修复（优先级：最高）

#### 问题 1: WorkerMonitor 完全无锁访问 ⚠️ 严重

**文件**: `aethelum_core_lite/core/worker_monitor.py`

**问题**：
- 三个并发线程（指标收集、健康检查、告警处理）同时访问共享数据
- `_metrics_history`, `_current_metrics`, `_active_alerts` 完全无锁保护
- 可能导致数据损坏、告警丢失、统计错误

**修复方案**：
```python
# 在 __init__ 方法中添加（约第 160 行）
self._metrics_lock = threading.RLock()  # 保护指标数据
self._alerts_lock = threading.RLock()   # 保护告警数据

# 修改 _record_metric 方法（第 466-507 行）
def _record_metric(self, name, value, metric_type, labels=None, unit="", description=""):
    timestamp = time.time()
    metric = MetricValue(...)

    with self._metrics_lock:  # ← 添加锁保护
        self._current_metrics[name] = metric
        if name not in self._metrics_history:
            self._metrics_history[name] = deque(maxlen=self.max_metrics_history)
        self._metrics_history[name].append(metric)
        self._stats.total_metrics_collected += 1
        self._stats.last_collection_time = timestamp

# 修改 _create_alert 方法（第 636-687 行）
def _create_alert(self, level, title, message, source, worker_id=None, ...):
    alert = Alert(...)

    with self._alerts_lock:  # ← 添加锁保护
        self._active_alerts[alert_id] = alert
        self._alert_history.append(alert)
        self._stats.total_alerts_generated += 1
        self._stats.active_alerts = len(self._active_alerts)
        self._notify_alert_callbacks(alert)

# 修改 _process_auto_recovery 方法（第 701-735 行）
def _process_auto_recovery(self):
    with self._alerts_lock:  # ← 添加锁保护
        for alert_id, alert in list(self._active_alerts.items()):
            # 处理逻辑...
            if recovered:
                del self._active_alerts[alert_id]
                self._stats.active_alerts = len(self._active_alerts)
                self._stats.resolved_alerts += 1

# 修改 get_active_alerts 方法（第 779-785 行）
def get_active_alerts(self):
    with self._alerts_lock:  # ← 添加锁保护
        return self._active_alerts.copy()  # 返回副本
```

**影响**：性能损失 < 1%（仅元数据操作）

---

#### 问题 2: SynapticQueue 非原子 put/get 操作 ⚠️ 严重

**文件**: `aethelum_core_lite/core/queue.py`

**问题**：
- `put` 操作：队列已放入但统计未更新，存在窗口期
- `get` 操作：消息已取出但统计未更新，可能读到不一致状态
- `_log1_buffer.append` 和 `_log2_buffer.append` 在锁外执行

**修复方案**：
```python
# 修改 put 方法（第 158-173 行）
def put(self, impulse, priority=5, block=True, timeout=None):
    if self._closed:
        return False

    if self._is_expired(impulse):
        return False

    message_id = str(uuid.uuid4())
    impulse.metadata["message_id"] = message_id
    impulse.metadata["queue_timestamp"] = time.time()
    impulse.metadata["priority"] = priority

    item = (priority, time.time(), message_id, impulse)

    # 将所有操作放在锁内，确保原子性
    with self._lock:
        try:
            self._queue.put(item, block=block, timeout=timeout)

            self._message_map[message_id] = impulse
            self._stats.total_messages += 1
            self._stats.last_activity = time.time()
            self._stats.queue_size = self._queue.qsize()

            priority_key = f"priority_{priority}"
            self._stats.priority_distribution[priority_key] = \
                self._stats.priority_distribution.get(priority_key, 0) + 1

            # 持久化操作也在锁内
            if self.enable_persistence:
                self._log1_buffer.append((message_id, priority, impulse))

            return True
        except queue.Full:
            return False

# 修改 get 方法（第 193-212 行）
def get(self, block=True, timeout=None):
    if self._closed:
        return None

    with self._lock:  # ← 确保原子性
        try:
            # 使用非阻塞的 get_nowait 避免在锁内等待
            if self._queue.empty():
                if not block or timeout == 0:
                    return None
                # 释放锁，等待队列有元素
                self._lock.release()
                try:
                    item = self._queue.get(block=block, timeout=timeout)
                finally:
                    self._lock.acquire()
            else:
                item = self._queue.get_nowait()

            priority, timestamp, message_id, impulse = item

            if self._is_expired(impulse):
                self._queue.task_done()
                return self.get(block, timeout)

            processing_start = time.time()

            # 更新状态
            if message_id in self._message_map:
                del self._message_map[message_id]
            self._stats.queue_size = self._queue.qsize()
            self._stats.last_activity = time.time()

            # 持久化操作在锁内
            if self.enable_persistence:
                self._log2_buffer.append(message_id)

            return impulse

        except queue.Empty:
            return None
```

**注意**：此方案简化了实现，实际可能需要使用条件变量来避免锁内阻塞。

**影响**：性能损失约 8-10%（从 46,000 msg/s 降至 ~42,000 msg/s）

---

#### 问题 3: 示例代码响应收集字典无锁 ⚠️ 严重

**文件**:
- `aethelum_core_lite/examples/basic_example.py`（第 89-90 行）
- `aethelum_core_lite/examples/advanced_example.py`（第 169 行）

**问题**：
- `collected_responses` 字典被多个 worker 线程并发写入
- 可能导致响应丢失或数据竞争

**修复方案**（basic_example.py）：
```python
# 在文件开头添加锁（约第 89 行）
response_lock = threading.Lock()
collected_responses = {}

# 修改 handle_response 函数（第 89-114 行）
def handle_response(impulse, source_queue):
    readable_content = impulse.get_text_content()
    logger.info(f"收集响应: '{readable_content}' (会话ID: {impulse.session_id})")

    response_data = {
        'content': readable_content,
        'session_id': impulse.session_id,
        'timestamp': time.time()
    }

    with response_lock:  # ← 添加锁保护
        collected_responses[impulse.session_id] = response_data

    if impulse.session_id in response_events:
        response_events[impulse.session_id].set()

    impulse.action_intent = "Done"
    return impulse

# 修改读取响应的地方（第 209-210 行）
def get_collected_responses():
    with response_lock:  # ← 添加锁保护
        return collected_responses.copy()

# 主循环中使用
while len(get_collected_responses()) < successful_sends:
    time.sleep(0.1)
```

**影响**：无性能影响（仅示例代码）

---

### 1.2 中危问题修复（优先级：高）

#### 问题 4: WorkerScheduler 轮询索引竞态

**文件**: `aethelum_core_lite/core/worker_scheduler.py`

**问题**：多个调度线程可能同时修改 `_round_robin_index`

**修复方案**：
```python
# 在 __init__ 中添加（约第 111 行）
self._rr_lock = threading.Lock()

# 修改 _select_worker_round_robin 方法（第 243-258 行）
def _select_worker_round_robin(self, available_workers):
    if not available_workers:
        return None

    with self._rr_lock:  # ← 添加锁保护
        self._round_robin_index = (self._round_robin_index + 1) % len(available_workers)
        return available_workers[self._round_robin_index].worker_id
```

---

#### 问题 5: AxonWorker 统计数据无锁更新

**文件**: `aethelum_core_lite/core/worker.py`

**问题**：`_stats` 对象的多个字段可能被并发修改

**修复方案**：
```python
# 在 __init__ 中添加（约第 117 行）
self._stats_lock = threading.Lock()

# 修改 _update_stats 方法（第 369 行）
def _update_stats(self, processing_time, success):
    with self._stats_lock:  # ← 添加锁保护
        if success:
            self._stats.processed_messages += 1
        else:
            self._stats.failed_messages += 1

        self._stats.total_processing_time += processing_time
        total_messages = self._stats.processed_messages + self._stats.failed_messages

        if total_messages > 0:
            self._stats.average_processing_time = \
                self._stats.total_processing_time / total_messages
            self._stats.success_rate = \
                (self._stats.processed_messages / total_messages) * 100

        self._stats.uptime = time.time() - self._stats.start_time

# 修改 get_stats 方法，返回副本
def get_stats(self):
    with self._stats_lock:
        self._stats.uptime = time.time() - self._stats.start_time
        self._stats.state = self._state
        # 返回副本而非引用
        return WorkerStats(
            worker_id=self._stats.worker_id,
            name=self._stats.name,
            state=self._stats.state,
            start_time=self._stats.start_time,
            last_activity=self._stats.last_activity,
            processed_messages=self._stats.processed_messages,
            failed_messages=self._stats.failed_messages,
            total_processing_time=self._stats.total_processing_time,
            average_processing_time=self._stats.average_processing_time,
            success_rate=self._stats.success_rate,
            uptime=self._stats.uptime
        )
```

---

#### 问题 6: WorkerManager 遍历时修改字典

**文件**: `aethelum_core_lite/core/worker_manager.py`

**问题**：`_check_workers_health` 遍历 `_workers` 时可能修改字典

**修复方案**：
```python
# 修改 _check_workers_health 方法（第 467-505 行）
def _check_workers_health(self):
    # 创建快照，避免遍历时修改
    workers_snapshot = list(self._workers.items())

    for worker_id, worker in workers_snapshot:
        if worker_id not in self._workers:
            continue  # 已被删除

        # ... 健康检查逻辑 ...

        if recovered and self.start_worker(worker_id):
            self._stats.auto_restarts += 1
```

---

### 1.3 低危问题修复（优先级：中）

#### 问题 7: Router execute_hooks 非原子执行

**文件**: `aethelum_core_lite/core/router.py`

**问题**：hooks 列表可能在执行时被修改

**修复方案**：
```python
# 修改 execute_hooks 方法（第 329 行）
def execute_hooks(self, impulse, queue_name, hook_type=HookType.PRE_PROCESS):
    hooks = self.get_hooks(queue_name, hook_type)  # 获取快照
    if not hooks:
        return impulse

    start_time = time.time()

    try:
        for hook in hooks:
            impulse = hook(impulse, queue_name)  # 逐个执行
    except Exception as e:
        self.logger.error(f"执行 {hook_type.value} Hook时出错: {e}")
        # ... 错误处理
    finally:
        # 记录执行时间（线程安全）
        execution_time = time.time() - start_time
        with self._lock:  # ← 添加锁保护
            if queue_name not in self._performance_metrics['hook_execution_times']:
                self._performance_metrics['hook_execution_times'][queue_name] = {}
            if hook_type not in self._performance_metrics['hook_execution_times'][queue_name]:
                self._performance_metrics['hook_execution_times'][queue_name][hook_type] = []

            times_list = self._performance_metrics['hook_execution_times'][queue_name][hook_type]
            times_list.append(execution_time)
            if len(times_list) > 100:
                times_list.pop(0)

    return impulse
```

---

## 二、依赖可复现性改进

### 2.1 使用 pip-compile 生成锁文件（推荐方案）

**原因**：保持现有工具链（setuptools + pip），团队学习成本低

#### 步骤 1: 安装 pip-tools

```bash
pip install pip-tools
```

#### 步骤 2: 创建 .in 文件

**文件**: `requirements/base.in`
```
requests>=2.25.0
protobuf>=3.20.0
```

**文件**: `requirements/dev.in`
```
-r base.in
pytest>=6.0.0
pytest-asyncio>=0.21.0
black>=22.0.0
flake8>=4.0.0
mypy>=0.991
```

**文件**: `requirements/performance.in`
```
msgpack>=1.0.0
```

#### 步骤 3: 生成锁文件

```bash
# 在项目根目录执行
pip-compile requirements/base.in --output-file=requirements/base-lock.txt
pip-compile requirements/dev.in --output-file=requirements/dev-lock.txt
pip-compile requirements/performance.in --output-file=requirements/performance-lock.txt
```

#### 步骤 4: 更新 .gitignore

确保 `.in` 文件被版本控制，但临时文件被忽略：

```
# requirements/
*.in
*-lock.txt
```

**实际上应该**：提交 `.in` 和 `-lock.txt` 文件！

```gitignore
# 不要忽略这些文件
!requirements/*.in
!requirements/*-lock.txt
```

#### 步骤 5: 更新安装文档

在 README.md 中添加：

```markdown
## 安装

### 开发环境（推荐使用锁文件）

```bash
# 使用锁文件安装，确保依赖版本完全一致
pip install -r requirements/dev-lock.txt

# 或使用性能优化依赖
pip install -r requirements/performance-lock.txt
```

### 添加新依赖

1. 编辑 `requirements/*.in` 文件
2. 运行 `pip-compile requirements/xxx.in --output-file=requirements/xxx-lock.txt`
3. 提交两个文件到版本控制
```

---

## 三、README 增强

### 3.1 添加并发安全性章节

在 README.md 中添加新章节（在"安全特性"之后）：

```markdown
## 并发安全性

### 线程安全保证

AethelumCoreLite 核心组件已实现全面的线程安全保护：

#### ✅ 已保护的组件

1. **SynapticQueue (突触队列)**
   - 使用 `threading.RLock` 保护内部状态
   - put/get 操作原子性保证
   - 统计信息线程安全更新

2. **WorkerMonitor (工作器监控器)**
   - `_metrics_lock` 保护指标数据
   - `_alerts_lock` 保护告警数据
   - 多线程环境下的数据一致性保证

3. **AxonWorker (轴突工作器)**
   - `_stats_lock` 保护统计信息
   - 健康检查线程安全

4. **WorkerScheduler (工作器调度器)**
   - `_rr_lock` 保护轮询索引
   - 负载信息更新线程安全

### 使用最佳实践

#### ✅ 推荐做法

```python
# 1. 使用线程安全的数据结构
import threading

# 使用锁保护的字典
data_lock = threading.Lock()
shared_data = {}

def thread_safe_write(key, value):
    with data_lock:
        shared_data[key] = value

def thread_safe_read():
    with data_lock:
        return shared_data.copy()

# 2. 避免在锁内执行耗时操作
with lock:
    data = modify_data()  # ✅ 快速操作

# 不要这样做
with lock:
    result = slow_network_call()  # ❌ 阻塞其他线程

# 3. 使用 RLock 支持重入
class MyClass:
    def __init__(self):
        self._lock = threading.RLock()

    def method1(self):
        with self._lock:
            self.method2()  # ✅ 可以重入

    def method2(self):
        with self._lock:
            # 临界区
            pass
```

#### ❌ 常见陷阱

```python
# 1. 字典无锁并发修改
responses = {}  # ❌ 不安全

def handler(impulse):
    responses[impulse.id] = impulse  # 多线程写入会丢失数据

# 正确做法
responses_lock = threading.Lock()
responses = {}

def handler(impulse):
    with responses_lock:
        responses[impulse.id] = impulse

# 2. 返回共享状态的引用
class Queue:
    def get_stats(self):
        return self._stats  # ❌ 返回引用，外部可修改

# 正确做法
def get_stats(self):
    with self._lock:
        return QueueStats(
            total_messages=self._stats.total_messages,
            # ... 返回副本
        )
```
```

---

### 3.2 添加故障排查章节

在 README.md 中添加：

```markdown
## 故障排查

### 并发相关问题

#### 症状1: 数据丢失或不一致

**可能原因**:
- 共享数据结构无锁保护
- 返回了内部状态的引用而非副本

**诊断方法**:
```python
# 添加调试日志
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def thread_safe_operation():
    logger.debug(f"Thread {threading.current_thread().name} acquiring lock")
    with lock:
        logger.debug(f"Thread {threading.current_thread().name} in critical section")
        # 操作
    logger.debug(f"Thread {threading.current_thread().name} released lock")
```

**解决方案**:
- 为所有共享状态添加锁保护
- 使用 `dict.copy()` 返回副本

#### 症状2: 性能突然下降

**可能原因**:
- 锁竞争严重
- 死锁或活锁

**诊断方法**:
```python
import threading
import time

class LockMonitor:
    def __init__(self, lock):
        self._lock = lock
        self._wait_times = []

    def __enter__(self):
        start = time.time()
        self._lock.acquire()
        wait_time = time.time() - start
        self._wait_times.append(wait_time)
        if wait_time > 1.0:  # 等待超过1秒
            logging.warning(f"Long lock wait: {wait_time:.2f}s")
        return self

    def __exit__(self, *args):
        self._lock.release()

# 使用
monitor = LockMonitor(lock)
with monitor:
    # 临界区
    pass
```

**解决方案**:
- 减小锁粒度
- 使用读写锁分离读写操作
- 考虑无锁数据结构

### 依赖问题

#### 症状: 环境差异导致的行为不一致

**解决方案**:
```bash
# 1. 使用锁文件安装依赖
pip install -r requirements/base-lock.txt

# 2. 验证依赖版本
pip list

# 3. 检查依赖冲突
pip check

# 4. 安全扫描
pip-audit
```
```

---

## 四、验证测试

### 4.1 并发安全测试

创建测试文件: `tests/test_thread_safety.py`

```python
import threading
import time
import pytest
from aethelum_core_lite import SynapticQueue, NeuralImpulse

def test_concurrent_queue_operations():
    """测试队列的并发安全性"""
    queue = SynapticQueue("test_queue", max_size=1000)
    num_producers = 5
    num_consumers = 5
    messages_per_producer = 100

    produced_count = [0]
    consumed_count = [0]
    errors = []

    def producer():
        for i in range(messages_per_producer):
            try:
                impulse = NeuralImpulse(
                    session_id=f"session-{i}",
                    action_intent="TEST",
                    source_agent="Producer",
                    content=f"Message {i}"
                )
                queue.put(impulse, priority=5)
                produced_count[0] += 1
            except Exception as e:
                errors.append(f"Producer error: {e}")

    def consumer():
        while True:
            try:
                impulse = queue.get(block=True, timeout=5.0)
                if impulse is None:
                    break
                consumed_count[0] += 1
                queue.task_done()
            except Exception as e:
                if "Empty" not in str(e):
                    errors.append(f"Consumer error: {e}")
                break

    # 启动生产者和消费者
    producers = [threading.Thread(target=producer) for _ in range(num_producers)]
    consumers = [threading.Thread(target=consumer) for _ in range(num_consumers)]

    for p in producers:
        p.start()
    for c in consumers:
        c.start()

    # 等待生产者完成
    for p in producers:
        p.join()

    # 等待队列清空
    queue.join()

    # 停止消费者
    time.sleep(0.5)

    # 验证结果
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert produced_count[0] == num_producers * messages_per_producer
    assert consumed_count[0] == produced_count[0], \
        f"Lost messages: produced={produced_count[0]}, consumed={consumed_count[0]}"

    queue.close()
```

### 4.2 运行测试

```bash
# 运行并发安全测试
pytest tests/test_thread_safety.py -v

# 运行所有测试
pytest tests/ -v

# 生成覆盖率报告
pytest tests/ --cov=aethelum_core_lite --cov-report=html
```

---

## 五、实施步骤

### 阶段 1: 高危并发问题修复（1-2天）

1. **WorkerMonitor 添加锁**
   - 文件: `aethelum_core_lite/core/worker_monitor.py`
   - 修改: 添加 `_metrics_lock` 和 `_alerts_lock`
   - 测试: 运行 `pytest tests/test_worker_monitor.py -v`

2. **SynapticQueue 原子化操作**
   - 文件: `aethelum_core_lite/core/queue.py`
   - 修改: put/get 方法添加原子性保护
   - 测试: 运行 `pytest tests/test_queue.py -v`

3. **示例代码添加锁**
   - 文件: `aethelum_core_lite/examples/basic_example.py`
   - 文件: `aethelum_core_lite/examples/advanced_example.py`
   - 修改: 添加 `response_lock`
   - 测试: 运行示例代码验证

### 阶段 2: 中低危并发问题修复（1天）

4. **WorkerScheduler 轮询索引锁**
   - 文件: `aethelum_core_lite/core/worker_scheduler.py`
   - 修改: 添加 `_rr_lock`
   - 测试: `pytest tests/test_worker_scheduler.py -v`

5. **AxonWorker 统计锁**
   - 文件: `aethelum_core_lite/core/worker.py`
   - 修改: 添加 `_stats_lock`
   - 测试: 运行 worker 相关测试

6. **WorkerManager 快照遍历**
   - 文件: `aethelum_core_lite/core/worker_manager.py`
   - 修改: `_check_workers_health` 使用快照
   - 测试: 运行集成测试

7. **Router execute_hooks 原子化**
   - 文件: `aethelum_core_lite/core/router.py`
   - 修改: 添加锁保护性能指标记录
   - 测试: 运行 router 测试

### 阶段 3: 依赖可复现性改进（0.5天）

8. **安装 pip-tools**
   ```bash
   pip install pip-tools
   ```

9. **创建 .in 文件**
   - 创建 `requirements/base.in`
   - 创建 `requirements/dev.in`
   - 创建 `requirements/performance.in`

10. **生成锁文件**
    ```bash
    pip-compile requirements/base.in --output-file=requirements/base-lock.txt
    pip-compile requirements/dev.in --output-file=requirements/dev-lock.txt
    pip-compile requirements/performance.in --output-file=requirements/performance-lock.txt
    ```

11. **更新 README.md**
    - 添加锁文件安装说明
    - 添加依赖管理流程

### 阶段 4: 文档完善（0.5天）

12. **README.md 添加并发安全性章节**
    - 位置: 在"安全特性"之后
    - 内容: 线程安全保证、最佳实践、常见陷阱

13. **README.md 添加故障排查章节**
    - 位置: 在"开发指南"之后
    - 内容: 并发问题诊断、依赖问题解决

14. **创建并发安全测试**
    - 文件: `tests/test_thread_safety.py`
    - 内容: 队列并发测试、监控器线程安全测试

### 阶段 5: 验证和优化（0.5天）

15. **运行完整测试套件**
    ```bash
    pytest tests/ -v --cov=aethelum_core_lite --cov-report=html
    ```

16. **性能基准测试**
    ```bash
    python performance_benchmark.py
    ```
    - 对比修复前后的吞吐量
    - 确保性能损失在可接受范围内（< 10%）

17. **代码审查**
    - 检查所有锁的使用是否正确
    - 确认无死锁风险
    - 验证返回副本而非引用

---

## 六、关键文件清单

### 需要修改的文件（按优先级）

1. **aethelum_core_lite/core/worker_monitor.py** ⚠️ 最高危
   - 添加 `_metrics_lock` 和 `_alerts_lock`
   - 修改 5 个方法

2. **aethelum_core_lite/core/queue.py** ⚠️ 最高危
   - 修改 `put` 和 `get` 方法确保原子性

3. **aethelum_core_lite/examples/basic_example.py** ⚠️ 最高危
   - 添加 `response_lock`

4. **aethelum_core_lite/examples/advanced_example.py** ⚠️ 最高危
   - 添加 `response_lock`

5. **aethelum_core_lite/core/worker_scheduler.py** ⚠️ 高危
   - 添加 `_rr_lock`

6. **aethelum_core_lite/core/worker.py** ⚠️ 高危
   - 添加 `_stats_lock`

7. **aethelum_core_lite/core/worker_manager.py** ⚠️ 高危
   - 修改 `_check_workers_health` 使用快照

8. **aethelum_core_lite/core/router.py** ⚠️ 中危
   - 修改 `execute_hooks` 添加锁保护

9. **requirements/base.in** ✨ 新增
   - 定义核心依赖

10. **requirements/dev.in** ✨ 新增
    - 定义开发依赖

11. **requirements/performance.in** ✨ 新增
    - 定义性能依赖

12. **requirements/base-lock.txt** ✨ 新增（自动生成）
13. **requirements/dev-lock.txt** ✨ 新增（自动生成）
14. **requirements/performance-lock.txt** ✨ 新增（自动生成）

15. **README.md** 📝 增强
    - 添加"并发安全性"章节
    - 添加"故障排查"章节
    - 更新安装说明

16. **tests/test_thread_safety.py** ✨ 新增
    - 并发安全测试用例

---

## 七、验证标准

### 并发安全性验证

✅ **所有测试通过**
```bash
pytest tests/ -v
# 预期: 0 失败
```

✅ **并发压力测试无数据丢失**
```bash
python tests/test_thread_safety.py
# 预期: produced_count == consumed_count
```

✅ **无死锁发生**
- 所有测试都能正常完成
- 无线程挂起现象

### 性能验证

✅ **吞吐量下降 < 10%**
- 修复前: ~46,000 msg/s
- 修复后: > 41,000 msg/s

✅ **无显著性能退化**
- 响应时间 P99 < 100ms
- CPU 使用率无明显增加

### 依赖可复现性验证

✅ **锁文件生成成功**
```bash
ls requirements/*-lock.txt
# 应该看到 3 个文件
```

✅ **重复安装结果一致**
```bash
# 虚拟环境 A
pip install -r requirements/dev-lock.txt
pip list | grep protobuf

# 虚拟环境 B
pip install -r requirements/dev-lock.txt
pip list | grep protobuf

# 版本号应该完全相同
```

---

## 八、风险评估

### 并发修复风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 死锁 | 低 | 高 | 使用 RLock，统一锁顺序，添加超时 |
| 性能下降 | 中 | 中 | 细粒度锁，减少临界区，基准测试验证 |
| 引入新bug | 低 | 中 | 充分测试，代码审查，逐步部署 |

### 依赖锁文件风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 锁文件冲突 | 中 | 低 | 团队规范，单一责任人，定期同步 |
| 依赖升级困难 | 低 | 低 | 保留 .in 文件，文档化升级流程 |

---

## 九、时间估算

| 阶段 | 任务 | 预估时间 |
|------|------|---------|
| 阶段 1 | 高危并发问题修复 | 1-2 天 |
| 阶段 2 | 中低危并发问题修复 | 1 天 |
| 阶段 3 | 依赖可复现性改进 | 0.5 天 |
| 阶段 4 | 文档完善 | 0.5 天 |
| 阶段 5 | 验证和优化 | 0.5 天 |
| **总计** | | **3.5-4.5 天** |

---

## 十、成功标准

✅ **所有识别的并发安全问题都已修复**
✅ **所有测试通过，无新增失败**
✅ **性能下降在可接受范围内（< 10%）**
✅ **依赖锁文件生成并纳入版本控制**
✅ **README 包含并发安全性和故障排查章节**
✅ **并发压力测试验证无数据丢失**

---

## 附录：锁设计原则

本计划中的所有锁设计遵循以下原则：

1. **使用 RLock 而非 Lock**
   - 允许同一线程重入
   - 避免死锁

2. **细粒度锁**
   - 不同资源使用不同锁
   - 减少锁竞争

3. **最小化临界区**
   - 只在必要时持锁
   - 避免在锁内执行耗时操作

4. **返回副本而非引用**
   - 防止外部修改内部状态
   - 保证数据一致性

5. **统一锁顺序**
   - 避免循环等待
   - 预防死锁

---

## 十一、来自 issue.md 的额外改进项

根据项目 issue.md 文件，以下额外问题需要处理：

### 11.1 BaseHook 统计与错误隔离改进（优先级：中）

**文件**: `aethelum_core_lite/hooks/base_hook.py`

**问题**：
- 缺少可靠的统计更新机制
- 错误隔离不够完善
- 缺少 `__call__` 兼容性

**修复方案**：

```python
# 在 __init__ 中添加线程锁
self._lock = threading.Lock()

# 统计信息字典
self._stats = {
    'total_processed': 0,
    'total_errors': 0,
    'total_skipped': 0,
    'avg_processing_time': 0.0,
    'last_processed_at': None,
    'execution_count': 0,
    'total_execution_time': 0.0
}

# 添加 __call__ 方法
def __call__(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
    """使 Hook 实例可直接作为 callable 被调用"""
    return self.execute(impulse, source_queue)

# 改进 execute 方法
def execute(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
    if not self.enabled:
        self.logger.debug(f"Hook {self.hook_name} 已禁用，跳过处理")
        with self._lock:
            self._stats['total_skipped'] += 1
        return impulse

    start_time = time.time()
    try:
        result = self.process(impulse, source_queue)
        processing_time = time.time() - start_time
        self._update_stats(success=True, elapsed=processing_time)
        return result
    except Exception as e:
        processing_time = time.time() - start_time
        self.logger.exception(f"Hook {self.hook_name} 处理时发生异常: {e}")
        self._update_stats(success=False, elapsed=processing_time)
        return impulse  # 不重新抛出，保持钩子可用

# 添加 _update_stats 方法
def _update_stats(self, success: bool, elapsed: float) -> None:
    with self._lock:
        self._stats['execution_count'] += 1
        self._stats['total_execution_time'] += elapsed
        self._stats['avg_processing_time'] = (
            self._stats['total_execution_time'] / self._stats['execution_count']
            if self._stats['execution_count'] > 0 else 0.0
        )
        self._stats['last_processed_at'] = time.time()
        if success:
            self._stats['total_processed'] += 1
        else:
            self._stats['total_errors'] += 1

# 改进 get_stats 方法
def get_stats(self) -> Dict[str, Any]:
    with self._lock:
        return dict(self._stats)  # 返回副本
```

---

### 11.2 NeuralImpulse 序列化增强（优先级：中）

**文件**: `aethelum_core_lite/core/message.py`

**问题**：
- `from_dict` 健壮性不足
- 缺少 `get_text_content` / `set_text_content` 方法
- 缺少 `copy()` 方法
- 没有内容大小限制，可能导致 OOM

**修复方案**：

```python
# 添加常量
MAX_CONTENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# 改进 to_dict 方法
def to_dict(self) -> Dict[str, Any]:
    """将脉冲转换为 JSON-友好的字典"""
    content = self.content
    # 如果 content 是 protobuf 对象，转换处理
    try:
        if hasattr(content, '__class__') and ProtoBufManager.is_available():
            try:
                content_dict = ProtoBufManager.proto_to_dict(content)
                content = content_dict
            except Exception:
                content = str(content)
    except Exception:
        content = str(content)

    return {
        "session_id": self.session_id,
        "action_intent": self.action_intent,
        "source_agent": self.source_agent,
        "input_source": self.input_source,
        "content": content,
        "metadata": self.metadata,
        "routing_history": list(self.routing_history),
        "timestamp": self.timestamp
    }

# 改进 from_dict 方法
@classmethod
def from_dict(cls, data: Dict[str, Any]) -> 'NeuralImpulse':
    """更健壮的从字典创建实例"""
    if not isinstance(data, dict):
        raise TypeError("from_dict: data must be a dict")

    session_id = data.get("session_id")
    action_intent = data.get("action_intent", "Q_AUDIT_INPUT")
    source_agent = data.get("source_agent", "SYSTEM")
    input_source = data.get("input_source", "USER")
    content = data.get("content")
    metadata = data.get("metadata", {}) or {}
    routing_history = data.get("routing_history", []) or []

    # 防止 content 过大
    try:
        if isinstance(content, (str, bytes)):
            size = len(content) if isinstance(content, (bytes, bytearray)) else len(content.encode('utf-8'))
            if size > MAX_CONTENT_SIZE_BYTES:
                metadata.setdefault('_content_truncated', True)
                content = content[:MAX_CONTENT_SIZE_BYTES]
    except Exception:
        pass

    return cls(
        session_id=session_id,
        action_intent=action_intent,
        source_agent=source_agent,
        input_source=input_source,
        content=content,
        metadata=metadata,
        routing_history=routing_history
    )

# 添加 copy 方法
def copy(self) -> 'NeuralImpulse':
    """浅拷贝用于创建响应/中间脉冲"""
    return NeuralImpulse(
        session_id=self.session_id,
        action_intent=self.action_intent,
        source_agent=self.source_agent,
        input_source=self.input_source,
        content=self.content,
        metadata=dict(self.metadata),
        routing_history=list(self.routing_history)
    )

# 添加 get_text_content 方法
def get_text_content(self) -> str:
    """尝试从 content 中提取文本内容"""
    if self.content is None:
        return ""
    if isinstance(self.content, str):
        return self.content
    try:
        if ProtoBufManager.is_available():
            return ProtoBufManager.content_to_text(self.content)
    except Exception:
        pass
    return str(self.content)

# 添加 set_text_content 方法
def set_text_content(self, text: str) -> None:
    """设置文本内容"""
    self.content = text
```

---

### 11.3 Validators 扩展（优先级：低）

**文件**: `aethelum_core_lite/utils/validators.py`

**问题**：
- `VALID_ACTION_INTENTS` 列表不完整
- 缺少 `validate_or_raise` 便捷方法

**修复方案**：

```python
# 扩展 VALID_ACTION_INTENTS
VALID_ACTION_INTENTS = {
    'Q_AUDIT_INPUT',
    'Q_AUDITED_INPUT',
    'Q_AUDIT_OUTPUT',
    'Q_PROCESS_INPUT',
    'Q_RESPONSE_SINK',
    'Q_DONE',
    'Q_ERROR_HANDLER',
    'Q_PROCESS_OUTPUT'
}

VALID_INPUT_SOURCES = {
    'USER', 'API', 'WEBSOCKET', 'CLI', 'SYSTEM', 'INTERNAL'
}

# 添加便捷方法
@classmethod
def validate_or_raise(cls, impulse: NeuralImpulse, strict: bool = True) -> None:
    """验证失败时抛出异常"""
    errors = cls.validate(impulse, strict=strict)
    if errors:
        raise ValidationError("; ".join(errors))

# 改进错误信息
if strict and ai not in cls.VALID_ACTION_INTENTS:
    errors.append(f"无效的 action_intent: {ai}. 建议使用: {sorted(list(cls.VALID_ACTION_INTENTS))[:5]} ...")
```

---

### 11.4 Error Handler 改进（优先级：低）

**文件**: `aethelum_core_lite/core/hooks.py`

**问题**：
- 错误处理时缺少足够的元数据
- Router 难以识别错误来源

**修复方案**：

```python
def create_default_error_handler():
    def handle_error(impulse, source_queue):
        # 添加错误元数据
        impulse.metadata.setdefault('_error_forwarded', True)
        impulse.metadata.setdefault('_error_time', time.time())
        impulse.metadata.setdefault('original_session_id',
            impulse.metadata.get('original_session_id', impulse.session_id))
        impulse.update_source("ErrorHandler")
        impulse.action_intent = "Done"
        return impulse
    return handle_error
```

---

### 11.5 Examples 非交互模式支持（优先级：中）

**文件**: `aethelum_core_lite/examples/main.py`

**问题**：
- 大量 `input()` 调用阻塞 CI/自动化
- 无法在 CI 环境中运行

**修复方案**：

```python
import os

# 检测非交互模式
NONINTERACTIVE = os.getenv("AETHELUM_NONINTERACTIVE") == "1" or os.getenv("CI") == "1"

def main():
    if NONINTERACTIVE:
        # 非交互模式：运行默认示例
        logger.info("非交互模式：运行 basic_example")
        self.run_basic_example()
        return

    # 否则继续交互式菜单
    while True:
        # ... 原有交互逻辑
```

**文档更新**：在 README 中添加：

```markdown
## CI/CD 集成

### 非交互模式运行示例

```bash
# 设置环境变量启用非交互模式
export AETHELUM_NONINTERACTIVE=1

# 或在 CI 环境中自动启用
export CI=1

# 运行示例（不会阻塞等待输入）
python -m aethelum_core_lite.examples.main
```
```

---

### 11.6 Tests 稳定化和 pytest 风格（优先级：中）

**文件**: `tests/test_core_components.py` 和其他测试文件

**问题**：
- 测试脚本使用 `sleep()` 等待，不稳定
- 未使用 pytest 风格断言

**修复方案**：

```python
# 将 sleep 替换为 Event
from threading import Event

# 旧代码
time.sleep(1)  # 不稳定

# 新代码
event = Event()
# ... 在另一个线程中
event.set()
# ... 等待
event.wait(timeout=5.0)

# 使用 pytest 断言
def test_queue_operations():
    queue = SynapticQueue("test")
    impulse = NeuralImpulse(content="test")

    # pytest 风格断言
    assert queue.put(impulse) is True
    assert queue.qsize() == 1

    result = queue.get()
    assert result is not None
    assert result.content == "test"
```

---

### 11.7 额外文件清单

**需要修改的额外文件**：

17. **aethelum_core_lite/hooks/base_hook.py** 🔧 改进
    - 添加 `_lock` 和线程安全统计
    - 添加 `__call__` 方法
    - 改进 `execute` 和 `_update_stats` 方法

18. **aethelum_core_lite/core/message.py** 🔧 改进
    - 添加 `MAX_CONTENT_SIZE_BYTES` 常量
    - 改进 `to_dict` 和 `from_dict` 方法
    - 添加 `copy()`, `get_text_content()`, `set_text_content()` 方法

19. **aethelum_core_lite/utils/validators.py** 🔧 改进
    - 扩展 `VALID_ACTION_INTENTS` 列表
    - 添加 `validate_or_raise()` 方法
    - 改进错误信息

20. **aethelum_core_lite/core/hooks.py** 🔧 改进
    - 改进 `create_default_error_handler()` 函数
    - 添加错误元数据

21. **aethelum_core_lite/examples/main.py** 🔧 改进
    - 添加非交互模式支持
    - 检测 `AETHELUM_NONINTERACTIVE` 和 `CI` 环境变量

22. **tests/test_core_components.py** 🔧 改进
    - 将 `sleep()` 替换为 `Event`
    - 使用 pytest 风格断言

23. **README.md** 📝 更新
    - 添加 CI/CD 集成章节
    - 说明非交互模式运行示例

---

### 11.8 额外实施步骤

**阶段 6: 代码质量增强（1天）**

18. **BaseHook 改进**
    - 文件: `aethelum_core_lite/hooks/base_hook.py`
    - 修改: 添加线程安全统计和 `__call__` 方法
    - 测试: 运行 hooks 测试

19. **NeuralImpulse 增强**
    - 文件: `aethelum_core_lite/core/message.py`
    - 修改: 添加新方法，改进序列化
    - 测试: 运行 message 测试

20. **Validators 扩展**
    - 文件: `aethelum_core_lite/utils/validators.py`
    - 修改: 扩展 intents 列表，添加便捷方法
    - 测试: 运行验证器测试

21. **Error Handler 改进**
    - 文件: `aethelum_core_lite/core/hooks.py`
    - 修改: 增强错误元数据
    - 测试: 手动验证错误处理

22. **Examples 非交互模式**
    - 文件: `aethelum_core_lite/examples/main.py`
    - 修改: 添加环境变量检测
    - 测试: `CI=1 python -m aethelum_core_lite.examples.main`

23. **Tests 稳定化**
    - 文件: `tests/test_core_components.py` 等
    - 修改: 替换 sleep 为 Event，使用 pytest 断言
    - 测试: `pytest tests/ -v`

---

### 11.9 更新后的时间估算

| 阶段 | 任务 | 预估时间 |
|------|------|---------|
| 阶段 1 | 高危并发问题修复 | 1-2 天 |
| 阶段 2 | 中低危并发问题修复 | 1 天 |
| 阶段 3 | 依赖可复现性改进 | 0.5 天 |
| 阶段 4 | 文档完善 | 0.5 天 |
| 阶段 5 | 验证和优化 | 0.5 天 |
| 阶段 6 | 代码质量增强 | 1 天 |
| **总计** | | **4.5-5.5 天** |

---

### 11.10 更新后的成功标准

✅ **所有识别的并发安全问题都已修复**
✅ **所有测试通过，无新增失败**
✅ **性能下降在可接受范围内（< 10%）**
✅ **依赖锁文件生成并纳入版本控制**
✅ **README 包含并发安全性和故障排查章节**
✅ **并发压力测试验证无数据丢失**
✅ **BaseHook 具有线程安全的统计机制**
✅ **NeuralImpulse 支持健壮的序列化和 copy**
✅ **Examples 支持 CI/CD 非交互模式**
✅ **Tests 稳定化，使用 pytest 风格**

---

## 十二、Examples 重构：使用模拟 AI 调用（优先级：高）

### 12.1 背景

**问题**：
- 当前 examples 依赖真实的 AI 客户端（OpenAI、智谱AI等）
- 需要 API keys 才能运行，增加使用门槛
- 受到 AI client 绑定的质疑
- 无法在 CI/CD 中自动运行

**目标**：
- 使用模拟 AI 调用（Mock AI Service）
- 移除对真实 API 的依赖
- 让 examples 开箱即用
- 清晰展示框架核心功能

### 12.2 实施方案

#### 创建 Mock AI 服务模块

**新文件**: `aethelum_core_lite/examples/mock_ai_service.py`

```python
"""
模拟 AI 服务用于示例演示

不依赖任何真实的 AI API，展示框架核心功能。
"""

import time
import random
from typing import Dict, Any, List

class MockAIClient:
    """模拟 AI 客户端"""

    def __init__(self, response_delay: float = 0.1):
        """
        初始化模拟客户端

        Args:
            response_delay: 模拟响应延迟（秒）
        """
        self.response_delay = response_delay
        self.request_count = 0

        # 预定义的模拟响应
        self.audit_responses = [
            "内容安全，符合规范",
            "发现潜在风险：内容涉及敏感话题",
            "建议修改：表述不够准确",
            "审核通过：内容质量良好"
        ]

        self.processing_responses = [
            "已处理您的请求",
            "任务完成，结果已生成",
            "处理成功：数据已更新",
            "操作完成：状态已同步"
        ]

    def audit_content(self, content: str) -> Dict[str, Any]:
        """
        模拟内容审核

        Args:
            content: 待审核内容

        Returns:
            审核结果字典
        """
        self.request_count += 1
        time.sleep(self.response_delay)

        # 模拟审核逻辑
        is_safe = len(content) < 1000  # 简单模拟
        audit_result = random.choice(self.audit_responses)

        return {
            "safe": is_safe,
            "result": audit_result,
            "confidence": random.uniform(0.8, 0.99),
            "request_id": self.request_count
        }

    def process_content(self, content: str) -> Dict[str, Any]:
        """
        模拟内容处理

        Args:
            content: 待处理内容

        Returns:
            处理结果字典
        """
        self.request_count += 1
        time.sleep(self.response_delay)

        processing_result = random.choice(self.processing_responses)

        return {
            "success": True,
            "result": processing_result,
            "processed_content": f"[已处理] {content}",
            "request_id": self.request_count
        }

    def chat_completion(self, messages: List[Dict[str, str]]) -> str:
        """
        模拟对话补全

        Args:
            messages: 消息列表

        Returns:
            AI 响应文本
        """
        self.request_count += 1
        time.sleep(self.response_delay)

        responses = [
            "这是一个很好的问题！",
            "根据我的分析，建议您...",
            "让我为您详细解释。",
            "这个话题很有趣，我认为..."
        ]

        return random.choice(responses)

    def get_stats(self) -> Dict[str, Any]:
        """获取客户端统计信息"""
        return {
            "total_requests": self.request_count,
            "avg_delay": self.response_delay
        }
```

#### 重构示例文件结构

**新的示例结构**：
```
aethelum_core_lite/examples/
├── __init__.py
├── mock_ai_service.py          # 新增：Mock AI 服务
├── basic_example.py            # 重构：使用 Mock AI
├── advanced_example.py         # 重构：使用 Mock AI
├── batch_processing_example.py # 新增：批量处理示例
├── custom_hook_example.py      # 新增：自定义 Hook 示例
├── performance_demo.py         # 新增：性能演示
└── main.py                     # 重构：示例入口
```

#### 重构 basic_example.py

**主要改动**：
1. 移除真实 API keys 配置
2. 使用 MockAIClient 替代真实客户端
3. 简化配置流程
4. 增加注释说明

```python
"""
基础示例：使用 Mock AI 服务演示核心功能

本示例展示 AethelumCoreLite 的核心功能：
- 神经脉冲消息传递
- 队列管理
- Worker 处理
- Hook 机制

注意：使用模拟 AI 服务，不需要真实 API keys。
"""

import time
import threading
from aethelum_core_lite import (
    NeuralImpulse,
    SynapticQueue,
    AxonWorker,
    WorkerManager,
    Router
)
from aethelum_core_lite.examples.mock_ai_service import MockAIClient

# 创建模拟 AI 客户端
mock_ai = MockAIClient(response_delay=0.05)

def create_audit_handler():
    """创建审核处理器"""
    def handle(impulse, source_queue):
        content = impulse.get_text_content()
        result = mock_ai.audit_content(content)

        response = NeuralImpulse(
            session_id=impulse.session_id,
            action_intent="Q_AUDITED_INPUT",
            source_agent="AuditAgent",
            content=f"审核结果: {result['result']}",
            metadata={
                "safe": result["safe"],
                "confidence": result["confidence"]
            }
        )
        return response
    return handle

def run_basic_example():
    """运行基础示例"""
    print("=" * 60)
    print("AethelumCoreLite 基础示例（Mock AI 版本）")
    print("=" * 60)

    # 1. 创建路由器
    router = Router("demo_router")

    # 2. 创建队列
    input_queue = router.create_queue(
        "input",
        max_size=1000,
        enable_persistence=False  # 示例中不启用持久化
    )

    # 3. 注册审核处理器
    router.register_hook("input", "pre_process", create_audit_handler())

    # 4. 创建 Worker
    router.adjust_workers("input", target_count=2)

    # 5. 启动路由器
    router.start()

    # 6. 发送测试消息
    test_messages = [
        "这是一条测试消息",
        "请审核这段内容",
        "验证框架功能"
    ]

    print("\n发送测试消息...")
    for msg in test_messages:
        impulse = NeuralImpulse(
            action_intent="Q_AUDIT_INPUT",
            content=msg
        )
        input_queue.put(impulse)
        print(f"✓ 已发送: {msg}")

    # 7. 等待处理
    time.sleep(1)

    # 8. 停止路由器
    router.stop()

    # 9. 显示统计
    stats = router.get_stats()
    print(f"\n处理完成！")
    print(f"总消息数: {stats['total_messages']}")
    print(f"活跃 Worker: {stats['active_workers']}")

    print("\nMock AI 服务统计:")
    ai_stats = mock_ai.get_stats()
    print(f"总请求数: {ai_stats['total_requests']}")

    print("\n" + "=" * 60)
    print("示例运行完成！")
    print("=" * 60)

if __name__ == "__main__":
    run_basic_example()
```

#### 重构 advanced_example.py

**展示高级功能**：
- 并发处理
- 优先级队列
- 自定义 Hook
- 错误处理

#### 新增示例文件

**batch_processing_example.py**: 批量处理示例
**custom_hook_example.py**: 自定义 Hook 示例
**performance_demo.py**: 性能演示

### 12.3 更新的文件清单

**需要重构的文件**：

24. **aethelum_core_lite/examples/mock_ai_service.py** ✨ 新增
    - 创建 Mock AI 服务类
    - 提供模拟审核、处理、对话功能

25. **aethelum_core_lite/examples/basic_example.py** 🔄 重构
    - 移除真实 API 依赖
    - 使用 MockAIClient
    - 简化配置流程

26. **aethelum_core_lite/examples/advanced_example.py** 🔄 重构
    - 使用 MockAIClient
    - 展示高级功能

27. **aethelum_core_lite/examples/main.py** 🔄 重构
    - 更新示例入口
    - 移除 API keys 配置
    - 添加非交互模式

28. **aethelum_core_lite/examples/batch_processing_example.py** ✨ 新增
    - 批量消息处理示例

29. **aethelum_core_lite/examples/custom_hook_example.py** ✨ 新增
    - 自定义 Hook 开发示例

30. **aethelum_core_lite/examples/performance_demo.py** ✨ 新增
    - 性能基准测试演示

### 12.4 更新 README.md

在示例章节中说明：

```markdown
## 示例

所有示例均使用模拟 AI 服务，**不需要真实 API keys**，开箱即用。

### 运行基础示例

```bash
python -m aethelum_core_lite.examples.basic_example
```

### 示例列表

- **basic_example.py**: 基础功能演示
- **advanced_example.py**: 高级功能（并发、优先级、自定义 Hook）
- **batch_processing_example.py**: 批量处理
- **custom_hook_example.py**: 自定义 Hook 开发
- **performance_demo.py**: 性能基准测试

### 模拟 AI 服务

所有示例使用 `MockAIClient`，不依赖真实 API：
- 模拟审核结果
- 模拟处理延迟
- 模拟响应生成

如需使用真实 AI 服务，请参考 [集成真实 AI 客户端](#集成真实-ai-客户端) 章节。

### 集成真实 AI 客户端

示例代码展示了如何集成真实 AI 服务（OpenAI、智谱AI等）：
- 查看 `examples/real_ai_integration/` 目录
- 替换 MockAIClient 为真实客户端
- 配置相应的 API keys
```

### 12.5 更新后的时间估算

| 阶段 | 任务 | 预估时间 |
|------|------|---------|
| 阶段 1 | 高危并发问题修复 | 1-2 天 |
| 阶段 2 | 中低危并发问题修复 | 1 天 |
| 阶段 3 | 依赖可复现性改进 | 0.5 天 |
| 阶段 4 | 文档完善 | 0.5 天 |
| 阶段 5 | 验证和优化 | 0.5 天 |
| 阶段 6 | 代码质量增强 | 1 天 |
| 阶段 7 | Examples 重构（Mock AI） | 1 天 |
| **总计** | | **5.5-6.5 天** |

### 12.6 更新后的成功标准

✅ **所有识别的并发安全问题都已修复**
✅ **所有测试通过，无新增失败**
✅ **性能下降在可接受范围内（< 10%）**
✅ **依赖锁文件生成并纳入版本控制**
✅ **README 包含并发安全性和故障排查章节**
✅ **并发压力测试验证无数据丢失**
✅ **BaseHook 具有线程安全的统计机制**
✅ **NeuralImpulse 支持健壮的序列化和 copy**
✅ **Examples 支持 CI/CD 非交互模式**
✅ **Tests 稳定化，使用 pytest 风格**
✅ **所有示例使用 Mock AI，不依赖真实 API**
✅ **Examples 开箱即用，无需配置 API keys**
