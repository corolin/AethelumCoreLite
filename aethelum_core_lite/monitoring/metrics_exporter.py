"""
Prometheus指标导出器

将系统指标导出到Prometheus格式。
"""

import logging
import json
import ast
import time
from pathlib import Path
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PrometheusMetricsExporter:
    """Prometheus指标导出器"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8000,
                 persist_state: bool = True,
                 state_file: str = "prometheus_state.json"):
        self.host = host
        self.port = port
        self.persist_state = persist_state
        self.state_file = Path(state_file)

        # 记录上次的Counter值（用于计算增量）
        self._last_processed_counts: Dict[tuple, int] = {}
        self._last_failed_counts: Dict[tuple, int] = {}

        # 记录 Counter 的累积总值（用于持久化）
        self._counter_values: Dict[str, Dict[tuple, int]] = {
            "processed": {},
            "failed": {}
        }

        # Counter指标（先创建 Counter 对象）
        self.messages_processed = Counter(
            'aethelum_messages_processed_total',
            'Total number of messages processed',
            ['queue_name', 'worker_id']
        )

        self.messages_failed = Counter(
            'aethelum_messages_failed_total',
            'Total number of failed messages',
            ['queue_name', 'worker_id']
        )

        # 从文件加载状态（如果启用）
        # 注意：必须在创建 Counter 之后加载状态，以便恢复 Counter 的值
        if self.persist_state:
            self._load_state()

        # Gauge指标
        self.queue_size = Gauge(
            'aethelum_queue_size',
            'Current queue size',
            ['queue_name']
        )

        self.queue_usage_percent = Gauge(
            'aethelum_queue_usage_percent',
            'Queue usage percentage',
            ['queue_name']
        )

        self.worker_health_score = Gauge(
            'aethelum_worker_health_score',
            'Worker health score (0-100)',
            ['worker_id', 'worker_name']
        )

        self.worker_processing_time_avg = Gauge(
            'aethelum_worker_processing_time_avg_seconds',
            'Average message processing time',
            ['worker_id']
        )

        # Histogram指标
        self.message_processing_duration = Histogram(
            'aethelum_message_processing_duration_seconds',
            'Message processing duration',
            ['queue_name', 'worker_id'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )

    def start_server(self):
        """启动Prometheus HTTP服务器"""
        start_http_server(addr=self.host, port=self.port)
        logger.info(f"[Prometheus] Server started on http://{self.host}:{self.port}/metrics")

    def _load_state(self):
        """从文件加载Counter状态并恢复Counter值"""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            # 恢复 processed counts（用于增量计算）
            for key_str, value in state.get("last_processed_counts", {}).items():
                key = ast.literal_eval(key_str)  # 安全地将字符串转回元组
                self._last_processed_counts[key] = value

            # 恢复 failed counts（用于增量计算）
            for key_str, value in state.get("last_failed_counts", {}).items():
                key = ast.literal_eval(key_str)
                self._last_failed_counts[key] = value

            # ✅ 关键修复：恢复 Counter 的累积总值
            # 这样可以解决 metrics_exporter 进程重启后 Counter 重置的问题
            counter_values = state.get("counter_values", {})
            if counter_values:
                # 恢复 processed counter 的值
                for key_str, value in counter_values.get("processed", {}).items():
                    key = ast.literal_eval(key_str)
                    self._counter_values["processed"][key] = value
                    # 设置 Counter 的初始值（使用 Prometheus 内部 API）
                    try:
                        queue_name, worker_id = key
                        self.messages_processed.labels(
                            queue_name=queue_name,
                            worker_id=worker_id
                        )._value.set(value)
                    except Exception as e:
                        logger.warning(f"[Prometheus] Failed to restore processed counter for {key}: {e}")

                # 恢复 failed counter 的值
                for key_str, value in counter_values.get("failed", {}).items():
                    key = ast.literal_eval(key_str)
                    self._counter_values["failed"][key] = value
                    # 设置 Counter 的初始值
                    try:
                        queue_name, worker_id = key
                        self.messages_failed.labels(
                            queue_name=queue_name,
                            worker_id=worker_id
                        )._value.set(value)
                    except Exception as e:
                        logger.warning(f"[Prometheus] Failed to restore failed counter for {key}: {e}")

            logger.info("[Prometheus] State loaded from file (including counter values)")
        except Exception as e:
            logger.error(f"[Prometheus] Failed to load state: {e}")

    def _save_state(self):
        """保存Counter状态到文件（包括Counter的实际累积值）"""
        if not self.persist_state:
            return

        try:
            # 将元组键转换为字符串（JSON序列化）
            processed_counts_str = {
                str(key): value
                for key, value in self._last_processed_counts.items()
            }
            failed_counts_str = {
                str(key): value
                for key, value in self._last_failed_counts.items()
            }

            # ✅ 关键修复：收集并保存 Counter 的实际累积值
            # 而不是只保存 _last_processed_counts
            counter_values_str = {
                "processed": {
                    str(key): value
                    for key, value in self._counter_values.get("processed", {}).items()
                },
                "failed": {
                    str(key): value
                    for key, value in self._counter_values.get("failed", {}).items()
                }
            }

            state = {
                "last_processed_counts": processed_counts_str,
                "last_failed_counts": failed_counts_str,
                "counter_values": counter_values_str,  # ✅ 保存 Counter 实际值
                "timestamp": time.time()
            }

            # 原子写入（使用临时文件）
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(state, f, indent=2)

            # 原子替换
            temp_file.replace(self.state_file)

            logger.debug("[Prometheus] State saved to file (including counter values)")
        except Exception as e:
            logger.error(f"[Prometheus] Failed to save state: {e}")

    def shutdown(self):
        """关闭导出器，保存状态"""
        self._save_state()
        logger.info("[Prometheus] Exporter shut down, state saved")

    def export_from_memory(self, metrics_data: Dict[str, Any]):
        """从内存导出指标到Prometheus"""
        # 导出队列指标
        queues = metrics_data.get("queues", {})
        for queue_id, queue_metrics in queues.items():
            self.queue_size.labels(queue_name=queue_id).set(queue_metrics.get("size", 0))
            self.queue_usage_percent.labels(queue_name=queue_id).set(
                queue_metrics.get("usage_percent", 0)
            )

        # 导出Worker指标
        workers = metrics_data.get("workers", {})
        for worker_id, worker_metrics in workers.items():
            self.worker_health_score.labels(
                worker_id=worker_id,
                worker_name=worker_metrics.get("worker_name", "unknown")
            ).set(worker_metrics.get("health_score", 0))

            self.worker_processing_time_avg.labels(
                worker_id=worker_id
            ).set(worker_metrics.get("average_processing_time", 0))

            # Counter指标（计算增量并累加）
            processed = worker_metrics.get("processed_messages", 0)
            queue_name = worker_metrics.get("queue_id", "unknown")
            key = (queue_name, worker_id)

            last_count = self._last_processed_counts.get(key, 0)

            # ✅ 改进的计数器回滚检测逻辑
            if processed < last_count:
                # 检测到计数器回滚（工作器进程重启）
                # delta 应该是 processed 本身（从0重新开始计数）
                delta = processed
                if delta > 0:
                    logger.info(
                        f"[Prometheus] Worker {worker_id} counter rollback detected: "
                        f"{last_count} -> {processed}, adding {delta} new messages"
                    )
            else:
                # 正常情况：计算增量
                delta = processed - last_count

            if delta > 0:
                # 累加到 Prometheus Counter
                self.messages_processed.labels(
                    queue_name=queue_name,
                    worker_id=worker_id
                ).inc(delta)

                # ✅ 同步更新 _counter_values（用于持久化）
                current_total = self._counter_values["processed"].get(key, 0)
                self._counter_values["processed"][key] = current_total + delta

                # 更新 last_processed_counts（用于下次计算增量）
                self._last_processed_counts[key] = processed

            failed = worker_metrics.get("failed_messages", 0)
            failed_key = (queue_name, worker_id)

            last_failed = self._last_failed_counts.get(failed_key, 0)

            # ✅ 改进的失败计数回滚检测
            if failed < last_failed:
                failed_delta = failed
                if failed_delta > 0:
                    logger.info(
                        f"[Prometheus] Worker {worker_id} failed counter rollback detected: "
                        f"{last_failed} -> {failed}, adding {failed_delta} new failures"
                    )
            else:
                failed_delta = failed - last_failed

            if failed_delta > 0:
                # 累加到 Prometheus Counter
                self.messages_failed.labels(
                    queue_name=queue_name,
                    worker_id=worker_id
                ).inc(failed_delta)

                # ✅ 同步更新 _counter_values（用于持久化）
                current_total = self._counter_values["failed"].get(failed_key, 0)
                self._counter_values["failed"][failed_key] = current_total + failed_delta

                # 更新 last_failed_counts
                self._last_failed_counts[failed_key] = failed

        # 定期保存状态（在导出完成后）
        self._save_state()
