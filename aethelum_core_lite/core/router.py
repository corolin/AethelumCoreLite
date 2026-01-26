"""
神经胞体路由器 (NeuralSomaRouter)

核心编排组件，负责整合和分发神经信号，管理队列和工作器的生命周期。
"""

import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Set, Any, Union
from enum import Enum
from dataclasses import asdict
from .message import NeuralImpulse
from .queue import SynapticQueue
from .worker import AxonWorker


class QueuePriority(Enum):
    """队列优先级枚举"""
    CRITICAL = 1  # 关键队列，如错误处理
    HIGH = 2      # 高优先级队列
    NORMAL = 3    # 普通优先级队列
    LOW = 4       # 低优先级队列


class HookType(Enum):
    """Hook类型枚举"""
    PRE_PROCESS = "pre_process"  # 预处理Hook
    POST_PROCESS = "post_process"  # 后处理Hook
    ERROR_HANDLER = "error_handler"  # 错误处理Hook
    TRANSFORM = "transform"  # 转换Hook


class NeuralSomaRouter:
    """
    神经胞体路由器 - 整合和分发神经信号的核心组件

    基于设计文档的CoreLiteRouter实现：
    - 维护队列实例和钩子映射
    - 管理Worker线程的生命周期
    - 提供神经系统的启动/激活接口
    - 支持可选的安全审计流程
    - 支持队列优先级管理
    - 支持多个Hook注册和执行
    - 支持动态调整队列和工作器
    - 提供详细的性能监控
    """

    # 强制性核心队列
    MANDATORY_QUEUES = {
        'Q_AUDIT_INPUT': {'priority': QueuePriority.HIGH, 'description': '输入审查队列'},
        'Q_AUDIT_OUTPUT': {'priority': QueuePriority.HIGH, 'description': '输出审查队列'},
        'Q_RESPONSE_SINK': {'priority': QueuePriority.CRITICAL, 'description': '响应汇聚队列'},
        'Q_DONE': {'priority': QueuePriority.NORMAL, 'description': '完成队列'},
        'Q_ERROR': {'priority': QueuePriority.CRITICAL, 'description': '错误处理队列'}
    }

    # 队列默认优先级
    QUEUE_PRIORITIES = {
        'Q_AUDIT_INPUT': QueuePriority.HIGH,
        'Q_AUDIT_OUTPUT': QueuePriority.HIGH,
        'Q_RESPONSE_SINK': QueuePriority.CRITICAL,
        'Q_DONE': QueuePriority.NORMAL,
        'Q_ERROR': QueuePriority.CRITICAL,
        'Q_PROCESS_INPUT': QueuePriority.HIGH,
        'Q_ERROR_HANDLER': QueuePriority.HIGH
    }

    def __init__(self, enable_logging: bool = True):
        """
        初始化神经胞体路由器

        Args:
            enable_logging: 是否启用日志记录
        """
        # 队列管理
        self._queues: Dict[str, SynapticQueue] = {}
        self._queue_priorities: Dict[str, QueuePriority] = {}
        self._lock = threading.RLock()

        # Hook映射：队列名 -> {HookType: [Hook函数]}
        self._hooks: Dict[str, Dict[HookType, List[Callable]]] = {}

        # Worker管理
        self._workers: Dict[str, List[AxonWorker]] = {}
        self._router_active = False

        # 性能监控
        self._performance_metrics = {
            'queue_processing_times': {},  # 队列名 -> [处理时间列表]
            'hook_execution_times': {},    # 队列名 -> {HookType: [执行时间列表]}
            'worker_utilization': {},      # 队列名 -> [工作器利用率列表]
            'last_metrics_update': time.time()
        }

        # 统计信息
        self._stats = {
            'created_at': time.time(),
            'activated_at': None,
            'total_impulses_processed': 0,
            'total_hooks_registered': 0,
            'total_queues_created': 0,
            'total_workers_created': 0,
            'total_errors': 0
        }

        # 日志设置
        if enable_logging:
            logging.basicConfig(
                level=logging.DEBUG,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        self.logger = logging.getLogger("NeuralSomaRouter")

        self.logger.info("神经胞体路由器初始化完成")

    def create_queue(
        self,
        name: str,
        max_size: Optional[int] = None,
        durable: bool = False,
        auto_delete: bool = False,
        priority: Optional[QueuePriority] = None
    ) -> SynapticQueue:
        """
        创建突触队列

        Args:
            name: 队列名称
            max_size: 最大容量
            durable: 是否持久化
            auto_delete: 是否自动删除
            priority: 队列优先级

        Returns:
            SynapticQueue: 创建的队列实例
        """
        with self._lock:
            if name in self._queues:
                self.logger.warning(f"队列 {name} 已存在，返回现有实例")
                return self._queues[name]

            queue = SynapticQueue(
                queue_id=name,
                max_size=max_size if max_size is not None else 0,
                enable_persistence=durable
            )

            self._queues[name] = queue
            # 设置队列优先级，如果未指定则使用默认值
            if priority is None:
                priority = self.QUEUE_PRIORITIES.get(name, QueuePriority.NORMAL)
            self._queue_priorities[name] = priority
            
            # 初始化性能指标
            self._performance_metrics['queue_processing_times'][name] = []
            self._performance_metrics['worker_utilization'][name] = []
            
            self._stats['total_queues_created'] += 1

            self.logger.debug(f"创建突触队列: {name}, 优先级: {priority.name}")
            return queue

    def get_queue(self, name: str) -> Optional[SynapticQueue]:
        """获取队列实例"""
        with self._lock:
            return self._queues.get(name)

    def get_queue_priority(self, name: str) -> Optional[QueuePriority]:
        """获取队列优先级"""
        with self._lock:
            return self._queue_priorities.get(name)

    def set_queue_priority(self, name: str, priority: QueuePriority) -> bool:
        """设置队列优先级"""
        with self._lock:
            if name not in self._queues:
                self.logger.error(f"队列 {name} 不存在")
                return False
            
            old_priority = self._queue_priorities[name]
            self._queue_priorities[name] = priority
            self.logger.debug(f"队列 {name} 优先级从 {old_priority.name} 更改为 {priority.name}")
            return True

    def register_hook(
        self,
        queue_name: str,
        hook_function: Callable[[NeuralImpulse, str], NeuralImpulse],
        hook_type: HookType = HookType.PRE_PROCESS,
        replace: bool = False
    ) -> None:
        """
        注册Hook函数到指定队列

        Args:
            queue_name: 队列名称
            hook_function: Hook函数
            hook_type: Hook类型
            replace: 是否替换同类型的所有现有Hook

        Raises:
            ValueError: 如果尝试向不存在的队列注册Hook
        """
        with self._lock:
            if queue_name not in self._queues:
                raise ValueError(f"队列 {queue_name} 不存在，请先创建队列")

            # 初始化队列的Hook字典（如果不存在）
            if queue_name not in self._hooks:
                self._hooks[queue_name] = {}
            
            # 初始化Hook类型的列表（如果不存在）
            if hook_type not in self._hooks[queue_name]:
                self._hooks[queue_name][hook_type] = []
                
            # 如果需要替换，则清空现有Hook
            if replace:
                self._hooks[queue_name][hook_type] = [hook_function]
            else:
                self._hooks[queue_name][hook_type].append(hook_function)
                
            self._stats['total_hooks_registered'] += 1

            self.logger.debug(f"注册 {hook_type.value} Hook到队列: {queue_name}")

    def unregister_hook(
        self,
        queue_name: str,
        hook_function: Optional[Callable] = None,
        hook_type: Optional[HookType] = None
    ) -> int:
        """
        从指定队列注销Hook函数

        Args:
            queue_name: 队列名称
            hook_function: 要注销的Hook函数（如果为None，则根据hook_type注销所有）
            hook_type: Hook类型（如果为None，则注销所有类型的Hook）

        Returns:
            int: 注销的Hook数量
        """
        with self._lock:
            if queue_name not in self._hooks:
                return 0
                
            removed_count = 0
            
            # 如果指定了hook_type
            if hook_type is not None:
                if hook_type in self._hooks[queue_name]:
                    hooks = self._hooks[queue_name][hook_type]
                    if hook_function is None:
                        # 注销该类型的所有Hook
                        removed_count = len(hooks)
                        del self._hooks[queue_name][hook_type]
                    else:
                        # 注销指定的Hook函数
                        try:
                            hooks.remove(hook_function)
                            removed_count = 1
                            if not hooks:  # 如果列表为空，删除该类型
                                del self._hooks[queue_name][hook_type]
                        except ValueError:
                            pass  # Hook函数不存在
            else:
                # 注销所有类型的Hook
                if hook_function is None:
                    for hooks in self._hooks[queue_name].values():
                        removed_count += len(hooks)
                    del self._hooks[queue_name]
                else:
                    # 在所有类型中查找并注销指定的Hook函数
                    for hook_type_key, hooks in list(self._hooks[queue_name].items()):
                        try:
                            hooks.remove(hook_function)
                            removed_count += 1
                            if not hooks:  # 如果列表为空，删除该类型
                                del self._hooks[queue_name][hook_type_key]
                        except ValueError:
                            pass  # Hook函数不存在
            
            self._stats['total_hooks_registered'] -= removed_count
            self.logger.debug(f"从队列 {queue_name} 注销了 {removed_count} 个Hook")
            return removed_count

    def get_hooks(
        self,
        queue_name: str,
        hook_type: Optional[HookType] = None
    ) -> Union[Dict[HookType, List[Callable]], List[Callable]]:
        """
        获取指定队列的Hook函数

        Args:
            queue_name: 队列名称
            hook_type: Hook类型（如果为None，则返回所有类型的Hook）

        Returns:
            Union[Dict[HookType, List[Callable]], List[Callable]]: Hook函数字典或列表
        """
        with self._lock:
            if queue_name not in self._hooks:
                return {} if hook_type is None else []
                
            if hook_type is not None:
                return self._hooks[queue_name].get(hook_type, [])
            else:
                return self._hooks[queue_name].copy()

    def execute_hooks(
        self,
        impulse: NeuralImpulse,
        queue_name: str,
        hook_type: HookType = HookType.PRE_PROCESS
    ) -> NeuralImpulse:
        """
        执行指定队列和类型的所有Hook函数

        Args:
            impulse: 神经脉冲
            queue_name: 队列名称
            hook_type: Hook类型

        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        hooks = self.get_hooks(queue_name, hook_type)
        if not hooks:
            return impulse
            
        start_time = time.time()
        
        try:
            for hook in hooks:
                impulse = hook(impulse, queue_name)
        except Exception as e:
            self.logger.error(f"执行 {hook_type.value} Hook时出错: {e}")
            self._stats['total_errors'] += 1
            # 可以选择将错误脉冲发送到错误队列
            if queue_name != 'Q_ERROR_HANDLER':
                self._send_to_queue('Q_ERROR_HANDLER', impulse)
        finally:
            # 记录Hook执行时间
            execution_time = time.time() - start_time
            if queue_name not in self._performance_metrics['hook_execution_times']:
                self._performance_metrics['hook_execution_times'][queue_name] = {}
            if hook_type not in self._performance_metrics['hook_execution_times'][queue_name]:
                self._performance_metrics['hook_execution_times'][queue_name][hook_type] = []
            
            # 只保留最近100次执行时间
            times_list = self._performance_metrics['hook_execution_times'][queue_name][hook_type]
            times_list.append(execution_time)
            if len(times_list) > 100:
                times_list.pop(0)
                
        return impulse

    def start_workers(
        self,
        queue_name: str,
        num_workers: int = 1,
        custom_hook: Optional[Callable] = None
    ) -> List[AxonWorker]:
        """
        为指定队列启动工作器

        Args:
            queue_name: 队列名称
            num_workers: 工作器数量
            custom_hook: 自定义Hook函数（覆盖已注册的Hook）

        Returns:
            List[AxonWorker]: 启动的工作器列表
        """
        with self._lock:
            if queue_name not in self._queues:
                raise ValueError(f"队列 {queue_name} 不存在")

            queue = self._queues[queue_name]
            hooks_list = []

            # 如果没有自定义Hook，则使用已注册的Hook
            if not custom_hook and queue_name in self._hooks:
                # 将字典中的所有Hook函数转换为BaseHook对象
                for hook_type, hook_functions in self._hooks[queue_name].items():
                    for hook_func in hook_functions:
                        # 使用函数式适配器而不是动态创建类
                        adapter = _create_hook_adapter(hook_func, hook_type, queue_name)
                        hooks_list.append(adapter)
            elif custom_hook:
                # 使用自定义Hook适配器
                adapter = _create_custom_hook_adapter(custom_hook, queue_name)
                hooks_list.append(adapter)

            # 创建工作器
            workers = []
            for i in range(num_workers):
                worker = AxonWorker(
                    name=f"{queue_name}-worker-{i}",
                    input_queue=queue,
                    hooks=hooks_list if hooks_list else None,
                    router=self
                )
                workers.append(worker)

            # 记录工作器
            if queue_name not in self._workers:
                self._workers[queue_name] = []
            self._workers[queue_name].extend(workers)

            self._stats['total_workers_created'] += num_workers

            # 启动工作器
            for worker in workers:
                worker.start()

            self.logger.debug(f"为队列 {queue_name} 启动了 {num_workers} 个工作器")
            return workers

    def adjust_workers(
        self,
        queue_name: str,
        target_count: int
    ) -> int:
        """
        动态调整指定队列的工作器数量

        Args:
            queue_name: 队列名称
            target_count: 目标工作器数量

        Returns:
            int: 实际调整的工作器数量（正数为增加，负数为减少）
        """
        with self._lock:
            if queue_name not in self._queues:
                raise ValueError(f"队列 {queue_name} 不存在")
                
            current_count = len(self._workers.get(queue_name, []))
            adjustment = target_count - current_count
            
            if adjustment == 0:
                return 0
                
            if adjustment > 0:
                # 增加工作器
                self.start_workers(queue_name, adjustment)
                self.logger.debug(f"为队列 {queue_name} 增加了 {adjustment} 个工作器")
            else:
                # 减少工作器
                workers_to_stop = abs(adjustment)
                workers = self._workers[queue_name][:workers_to_stop]
                
                for worker in workers:
                    worker.stop()
                    worker.join(timeout=5.0)
                    self._workers[queue_name].remove(worker)
                    
                self.logger.debug(f"为队列 {queue_name} 减少了 {workers_to_stop} 个工作器")
                
            return adjustment

    def get_queues_by_priority(self, priority: QueuePriority) -> List[str]:
        """
        获取指定优先级的所有队列名称

        Args:
            priority: 队列优先级

        Returns:
            List[str]: 队列名称列表
        """
        with self._lock:
            return [name for name, p in self._queue_priorities.items() if p == priority]

    def get_all_queues_sorted_by_priority(self) -> List[str]:
        """
        获取按优先级排序的所有队列名称

        Returns:
            List[str]: 按优先级排序的队列名称列表
        """
        with self._lock:
            return sorted(
                self._queues.keys(),
                key=lambda name: self._queue_priorities.get(name, QueuePriority.NORMAL).value
            )

    def activate(self) -> None:
        """
        激活整个神经系统

        自动创建所有强制性队列，启动必要的工作器。
        """
        with self._lock:
            if self._router_active:
                self.logger.warning("神经系统已经激活")
                return
            
            # 创建所有强制性队列
            for queue_name, queue_config in self.MANDATORY_QUEUES.items():
                if queue_name not in self._queues:
                    priority = queue_config['priority']
                    self.create_queue(queue_name, priority=priority)
                    self.logger.debug(f"创建强制性队列: {queue_name}")
            
            self._router_active = True
            self._stats['activated_at'] = time.time()
            self.logger.info("神经系统已激活")

    def _setup_builtin_done_handler(self) -> None:
        """设置内置的 Done 消息处理器"""
        logger = logging.getLogger("Builtin.DoneHandler")

        def handle_done(impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
            """内置 Done 消息处理器 - 消息的最终归宿"""
            # Done 队列是消息的最终归宿，只进行日志记录
            logger.debug(f"消息已终止: {impulse.session_id}")
            # 保持 action_intent = "Done" 防止进一步路由
            return impulse

        # 确保Done队列存在
        if "Q_DONE" not in self._queues:
            self.create_queue("Q_DONE", priority=QueuePriority.LOW)
            
        # 注册内置的 Done handler 并启动工作器
        self.register_hook("Q_DONE", handle_done)
        self.start_workers("Q_DONE", 1)  # 通常只需要一个工作器处理终止消息
        self.logger.debug("内置Done处理器已注册")

    def _setup_error_handler(self) -> None:
        """设置默认错误处理器"""
        # 确保错误处理队列存在
        if "Q_ERROR_HANDLER" not in self._queues:
            self.create_queue("Q_ERROR_HANDLER", priority=QueuePriority.HIGH)
        
        # 创建默认错误处理器并注册钩子
        from .hooks import create_default_error_handler
        error_handler = create_default_error_handler()
        self.register_hook("Q_ERROR_HANDLER", error_handler, HookType.ERROR_HANDLER)
        self.start_workers("Q_ERROR_HANDLER", 1)

    def setup_business_handlers(self, business_handler=None, response_handler=None) -> None:
        """
        设置业务处理器（用户自定义组件）

        Args:
            business_handler: 业务处理钩子函数
            response_handler: 响应处理钩子函数
        """
        if business_handler:
            # 确保业务处理队列存在
            if "Q_PROCESS_INPUT" not in self._queues:
                self.create_queue("Q_PROCESS_INPUT", priority=QueuePriority.HIGH)
            self.register_hook("Q_PROCESS_INPUT", business_handler, HookType.PRE_PROCESS)
            self.start_workers("Q_PROCESS_INPUT", 1)
            self.logger.info("业务处理器已注册")

        if response_handler:
            # 确保响应处理队列存在
            if "Q_RESPONSE_SINK" not in self._queues:
                self.create_queue("Q_RESPONSE_SINK", priority=QueuePriority.NORMAL)
            self.register_hook("Q_RESPONSE_SINK", response_handler, HookType.POST_PROCESS)
            self.start_workers("Q_RESPONSE_SINK", 1)
            self.logger.info("响应处理器已注册")

    def auto_setup(self, business_handler=None, response_handler=None) -> None:
        """
        一键自动设置整个神经系统

        Args:
            business_handler: 业务处理钩子函数（用户自定义）
            response_handler: 响应处理钩子函数（用户自定义）
        """
        self.logger.info("开始自动设置神经系统...")

        # 激活系统（自动创建所有组件，包括Done队列）
        self.activate()

        # 设置错误处理器
        self._setup_error_handler()

        # 设置业务组件
        self.setup_business_handlers(business_handler, response_handler)

        self.logger.info("神经系统自动设置完成")

    
    def inject_input(self, impulse: NeuralImpulse) -> bool:
        """
        注入神经脉冲到系统

        这是用户输入的主要入口点。

        Args:
            impulse: 神经脉冲

        Returns:
            bool: 是否成功注入
        """
        if not self._router_active:
            self.logger.error("神经系统未激活，无法注入神经脉冲")
            return False

        impulse.action_intent = 'Q_PROCESS_INPUT'
        # 添加初始处理节点记录
        impulse.add_to_history("INPUT_GATEWAY")
        return self._send_to_queue('Q_PROCESS_INPUT', impulse)

    def _send_to_queue(self, queue_name: str, impulse: NeuralImpulse) -> bool:
        """
        内部方法：发送神经脉冲到指定队列

        Args:
            queue_name: 目标队列名称
            impulse: 神经脉冲

        Returns:
            bool: 是否成功发送
        """
        queue = self.get_queue(queue_name)
        if queue is None:  # 修复：使用 is None 而不是 not queue
            self.logger.error(f"目标队列不存在: {queue_name}")
            return False

        start_time = time.time()
        
        try:
            success = queue.put(impulse, block=True, timeout=5.0)
            if success:
                with self._lock:
                    self._stats['total_impulses_processed'] += 1
                    
                # 记录处理时间
                processing_time = time.time() - start_time
                times_list = self._performance_metrics['queue_processing_times'][queue_name]
                times_list.append(processing_time)
                # 只保留最近100次处理时间
                if len(times_list) > 100:
                    times_list.pop(0)
                    
                self.logger.debug(f"神经脉冲已发送到队列 {queue_name}: {impulse.session_id[:8]}...")
            return success
        except Exception as e:
            self.logger.error(f"发送神经脉冲到队列 {queue_name} 失败: {e}")
            self._stats['total_errors'] += 1
            return False

    def stop(self) -> None:
        """停止整个神经系统"""
        self.logger.info("正在停止神经系统...")

        with self._lock:
            # 停止所有工作器
            for queue_name, workers in self._workers.items():
                self.logger.debug(f"停止队列 {queue_name} 的工作器...")
                for worker in workers:
                    worker.stop()
                    worker.join(timeout=5.0)

            self._router_active = False

        self.logger.info("🧠 神经系统已停止")

    def get_stats(self) -> Dict[str, Any]:
        """获取路由器统计信息"""
        with self._lock:
            uptime = time.time() - self._stats['created_at']
            runtime = time.time() - self._stats['activated_at'] if self._stats['activated_at'] else 0

            # 统计所有队列的信息
            queue_stats = {}
            total_queue_size = 0
            for name, queue in self._queues.items():
                stats_dict = asdict(queue.get_stats())
                stats_dict['priority'] = self._queue_priorities.get(name, QueuePriority.NORMAL).name
                queue_stats[name] = stats_dict
                total_queue_size += stats_dict['queue_size']

            # 统计所有工作器的信息
            worker_stats = {}
            total_workers = 0
            for queue_name, workers in self._workers.items():
                worker_stats[queue_name] = [worker.get_stats() for worker in workers]
                total_workers += len(workers)
                
            # 计算性能指标
            performance_stats = self._calculate_performance_stats()

            return {
                **self._stats,
                'is_active': self._router_active,
                'uptime_seconds': uptime,
                'runtime_seconds': runtime,
                'queue_count': len(self._queues),
                'hook_count': sum(len(hooks) for hooks in self._hooks.values()),
                'worker_count': total_workers,
                'total_queue_size': total_queue_size,
                'mandatory_queues_present': set(self.MANDATORY_QUEUES.keys()).issubset(set(self._queues.keys())),
                'queues': queue_stats,
                'workers': worker_stats,
                'performance': performance_stats
            }

    def _calculate_performance_stats(self) -> Dict[str, Any]:
        """计算性能统计信息"""
        stats = {
            'queue_avg_processing_times': {},
            'hook_avg_execution_times': {},
            'worker_avg_utilization': {}
        }
        
        # 计算队列平均处理时间
        for queue_name, times in self._performance_metrics['queue_processing_times'].items():
            if times:
                stats['queue_avg_processing_times'][queue_name] = sum(times) / len(times)
                
        # 计算Hook平均执行时间
        for queue_name, hook_types in self._performance_metrics['hook_execution_times'].items():
            stats['hook_avg_execution_times'][queue_name] = {}
            for hook_type, times in hook_types.items():
                if times:
                    stats['hook_avg_execution_times'][queue_name][hook_type.value] = sum(times) / len(times)
                    
        # 计算工作器平均利用率
        for queue_name, utilizations in self._performance_metrics['worker_utilization'].items():
            if utilizations:
                stats['worker_avg_utilization'][queue_name] = sum(utilizations) / len(utilizations)
                
        return stats

    def list_queues(self) -> List[str]:
        """列出所有队列名称"""
        with self._lock:
            return list(self._queues.keys())

    def list_hooks(self) -> List[str]:
        """列出所有已注册Hook的队列名称"""
        with self._lock:
            return list(self._hooks.keys())

    def get_queue_sizes(self) -> Dict[str, int]:
        """获取所有队列的当前大小"""
        sizes = {}
        for name, queue in self._queues.items():
            sizes[name] = queue.size()
        return sizes

    def __str__(self) -> str:
        """字符串表示"""
        status = "已激活" if self._router_active else "未激活"
        return f"NeuralSomaRouter(queues={len(self._queues)}, hooks={sum(len(hooks) for hooks in self._hooks.values())}, status={status})"

    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"NeuralSomaRouter(queues={list(self._queues.keys())}, "
                f"hooks={list(self._hooks.keys())}, active={self._router_active})")


# Hook适配器函数（模块级别，避免动态创建类）
def _create_hook_adapter(hook_func: Callable, hook_type: HookType, queue_name: str):
    """
    创建Hook适配器

    Args:
        hook_func: Hook函数
        hook_type: Hook类型
        queue_name: 队列名称

    Returns:
        BaseHook: Hook适配器实例
    """
    from ..hooks.base_hook import BaseHook

    class _HookAdapterImpl(BaseHook):
        def __init__(self, func, h_type, q_name):
            super().__init__(f"Adapter_{h_type.value}_{q_name}", enable_logging=False)
            self.func = func
            self.hook_type = h_type
            self.queue_name = q_name

        def before_process(self, impulse):
            if self.hook_type == HookType.PRE_PROCESS:
                return self.func(impulse, self.queue_name)
            return impulse

        def after_process(self, impulse):
            if self.hook_type == HookType.POST_PROCESS:
                return self.func(impulse, self.queue_name)
            return impulse

    return _HookAdapterImpl(hook_func, hook_type, queue_name)


def _create_custom_hook_adapter(hook_func: Callable, queue_name: str):
    """
    创建自定义Hook适配器

    Args:
        hook_func: Hook函数
        queue_name: 队列名称

    Returns:
        BaseHook: Hook适配器实例
    """
    from ..hooks.base_hook import BaseHook

    class _CustomHookAdapterImpl(BaseHook):
        def __init__(self, func, q_name):
            super().__init__(f"CustomAdapter_{q_name}", enable_logging=False)
            self.func = func
            self.queue_name = q_name

        def before_process(self, impulse):
            return self.func(impulse, self.queue_name)

        def after_process(self, impulse):
            return impulse

    return _CustomHookAdapterImpl(hook_func, queue_name)