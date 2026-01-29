"""
Hook链管理模块

提供Hook链的创建、管理和执行功能。
"""

import json
import logging
import time
import threading
from typing import Any, Dict, List, Optional, Callable, Union
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base_hook import BaseHook, PreHook, PostHook, ErrorHook, ConditionalHook, AsyncHook


class HookChain:
    """Hook链管理器"""
    
    def __init__(self, chain_name: str, max_workers: int = 4):
        """
        初始化Hook链
        
        Args:
            chain_name: 链名称
            max_workers: 最大并行工作线程数
        """
        self.chain_name = chain_name
        self.max_workers = max_workers
        self.logger = logging.getLogger(f"hook_chain.{chain_name}")
        
        # Hook存储
        self.pre_hooks: List[BaseHook] = []
        self.post_hooks: List[BaseHook] = []
        self.error_hooks: List[ErrorHook] = []
        self.conditional_hooks: List[ConditionalHook] = []
        self.async_hooks: List[AsyncHook] = []
        
        # 执行统计
        self.execution_stats = {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'avg_execution_time': 0.0,
            'total_execution_time': 0.0,
            'hook_stats': defaultdict(dict),
            'last_execution_time': None
        }
        
        # 线程锁
        self._lock = threading.RLock()
        
    def add_hook(self, hook: BaseHook, position: Optional[int] = None) -> 'HookChain':
        """
        添加Hook到链中
        
        Args:
            hook: 要添加的Hook
            position: 插入位置（None表示按优先级插入）
            
        Returns:
            HookChain: 返回自身以支持链式调用
        """
        with self._lock:
            if isinstance(hook, PreHook):
                self._insert_hook_by_priority(self.pre_hooks, hook, position)
            elif isinstance(hook, PostHook):
                self._insert_hook_by_priority(self.post_hooks, hook, position)
            elif isinstance(hook, ErrorHook):
                self._insert_hook_by_priority(self.error_hooks, hook, position)
            elif isinstance(hook, ConditionalHook):
                self._insert_hook_by_priority(self.conditional_hooks, hook, position)
            elif isinstance(hook, AsyncHook):
                self._insert_hook_by_priority(self.async_hooks, hook, position)
            else:
                # 基础Hook，默认添加到前置Hook
                self._insert_hook_by_priority(self.pre_hooks, hook, position)
                
            self.logger.info(f"添加Hook {hook.hook_name} 到链 {self.chain_name}")
            
        return self
    
    def _insert_hook_by_priority(self, hook_list: List[BaseHook], hook: BaseHook, position: Optional[int]):
        """按优先级插入Hook"""
        if position is not None:
            hook_list.insert(position, hook)
        else:
            # 按优先级插入（数值越小优先级越高）
            inserted = False
            for i, existing_hook in enumerate(hook_list):
                if hook.priority < existing_hook.priority:
                    hook_list.insert(i, hook)
                    inserted = True
                    break
            if not inserted:
                hook_list.append(hook)
    
    def remove_hook(self, hook_name: str) -> bool:
        """
        按名称移除Hook
        
        Args:
            hook_name: Hook名称
            
        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            removed = False
            
            for hook_list in [self.pre_hooks, self.post_hooks, self.error_hooks, 
                             self.conditional_hooks, self.async_hooks]:
                for i, hook in enumerate(hook_list):
                    if hook.hook_name == hook_name:
                        hook_list.pop(i)
                        self.logger.info(f"移除Hook {hook_name} 从链 {self.chain_name}")
                        removed = True
                        break
                if removed:
                    break
                    
            return removed
    
    def get_hook(self, hook_name: str) -> Optional[BaseHook]:
        """获取指定名称的Hook"""
        for hook_list in [self.pre_hooks, self.post_hooks, self.error_hooks, 
                         self.conditional_hooks, self.async_hooks]:
            for hook in hook_list:
                if hook.hook_name == hook_name:
                    return hook
        return None
    
    def execute_pre_hooks(self, impulse: Any, source_queue: str, parallel: bool = False) -> Any:
        """执行前置Hook"""
        if not self.pre_hooks:
            return impulse
            
        if parallel and len(self.pre_hooks) > 1:
            return self._execute_hooks_parallel(self.pre_hooks, impulse, source_queue)
        else:
            return self._execute_hooks_sequential(self.pre_hooks, impulse, source_queue)
    
    def execute_post_hooks(self, impulse: Any, source_queue: str, result: Any = None, parallel: bool = False) -> Any:
        """执行后置Hook"""
        if not self.post_hooks:
            return impulse
            
        if parallel and len(self.post_hooks) > 1:
            return self._execute_post_hooks_parallel(self.post_hooks, impulse, source_queue, result)
        else:
            return self._execute_post_hooks_sequential(self.post_hooks, impulse, source_queue, result)
    
    def execute_error_hooks(self, impulse: Any, source_queue: str, error: Exception) -> Any:
        """执行错误Hook"""
        if not self.error_hooks:
            impulse.metadata['unhandled_error'] = {
                'error': str(error),
                'error_type': type(error).__name__
            }
            return impulse
            
        for hook in self.error_hooks:
            try:
                impulse = hook.handle_error(impulse, source_queue, error)
            except Exception as hook_error:
                self.logger.error(f"错误Hook {hook.hook_name} 执行失败: {hook_error}")
                impulse.metadata[f'hook_error_{hook.hook_name}'] = str(hook_error)
                
        return impulse
    
    def execute_conditional_hooks(self, impulse: Any, source_queue: str) -> Any:
        """执行条件Hook"""
        for hook in self.conditional_hooks:
            try:
                impulse = hook.process(impulse, source_queue)
            except Exception as e:
                self.logger.error(f"条件Hook {hook.hook_name} 执行失败: {e}")
                impulse.metadata[f'hook_error_{hook.hook_name}'] = str(e)
                
        return impulse
    
    def execute_async_hooks(self, impulse: Any, source_queue: str) -> Any:
        """执行异步Hook"""
        if not self.async_hooks:
            return impulse
            
        return self._execute_hooks_parallel(self.async_hooks, impulse, source_queue)
    
    def _execute_hooks_sequential(self, hooks: List[BaseHook], impulse: Any, source_queue: str) -> Any:
        """顺序执行Hook"""
        for hook in hooks:
            if hook.enabled:
                try:
                    start_time = time.time()
                    impulse = hook.process(impulse, source_queue)
                    execution_time = time.time() - start_time
                    self._update_hook_stats(hook, execution_time, True)
                except Exception as e:
                    self.logger.error(f"Hooks {hook.hook_name} 执行失败: {e}")
                    self._update_hook_stats(hook, 0, False)
                    impulse.metadata[f'hook_error_{hook.hook_name}'] = str(e)
            else:
                self._update_hook_stats(hook, 0, False)
                
        return impulse
    
    def _execute_post_hooks_sequential(self, hooks: List[PostHook], impulse: Any, source_queue: str, result: Any) -> Any:
        """顺序执行后置Hook"""
        for hook in hooks:
            if hook.enabled:
                try:
                    start_time = time.time()
                    impulse = hook.post_process(impulse, source_queue, result)
                    execution_time = time.time() - start_time
                    self._update_hook_stats(hook, execution_time, True)
                except Exception as e:
                    self.logger.error(f"后置Hook {hook.hook_name} 执行失败: {e}")
                    self._update_hook_stats(hook, 0, False)
                    impulse.metadata[f'hook_error_{hook.hook_name}'] = str(e)
            else:
                self._update_hook_stats(hook, 0, False)
                
        return impulse
    
    def _execute_hooks_parallel(self, hooks: List[BaseHook], impulse: Any, source_queue: str) -> Any:
        """并行执行Hook"""
        if len(hooks) <= 1:
            return self._execute_hooks_sequential(hooks, impulse, source_queue)
        
        results = {}
        errors = {}
        
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(hooks))) as executor:
            # 提交所有Hook任务
            future_to_hook = {
                executor.submit(self._execute_single_hook_safe, hook, impulse, source_queue): hook
                for hook in hooks if hook.enabled
            }
            
            # 收集结果
            for future in as_completed(future_to_hook):
                hook = future_to_hook[future]
                try:
                    result_impulse = future.result()
                    results[hook.hook_name] = result_impulse
                except Exception as e:
                    self.logger.error(f"并行Hook {hook.hook_name} 执行失败: {e}")
                    errors[hook.hook_name] = str(e)
        
        # 合并结果（使用最后一个成功的结果作为基础）
        final_impulse = impulse
        for hook_name, result_impulse in results.items():
            final_impulse = result_impulse
            
        # 添加错误信息
        for hook_name, error in errors.items():
            final_impulse.metadata[f'hook_error_{hook_name}'] = error
            
        return final_impulse
    
    def _execute_post_hooks_parallel(self, hooks: List[PostHook], impulse: Any, source_queue: str, result: Any) -> Any:
        """并行执行后置Hook"""
        if len(hooks) <= 1:
            return self._execute_post_hooks_sequential(hooks, impulse, source_queue, result)
        
        results = {}
        errors = {}
        
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(hooks))) as executor:
            future_to_hook = {
                executor.submit(self._execute_single_post_hook_safe, hook, impulse, source_queue, result): hook
                for hook in hooks if hook.enabled
            }
            
            for future in as_completed(future_to_hook):
                hook = future_to_hook[future]
                try:
                    result_impulse = future.result()
                    results[hook.hook_name] = result_impulse
                except Exception as e:
                    self.logger.error(f"并行后置Hook {hook.hook_name} 执行失败: {e}")
                    errors[hook.hook_name] = str(e)
        
        final_impulse = impulse
        for hook_name, result_impulse in results.items():
            final_impulse = result_impulse
            
        for hook_name, error in errors.items():
            final_impulse.metadata[f'hook_error_{hook_name}'] = error
            
        return final_impulse
    
    def _execute_single_hook_safe(self, hook: BaseHook, impulse: Any, source_queue: str) -> Any:
        """安全执行单个Hook"""
        start_time = time.time()
        try:
            result = hook.process(impulse, source_queue)
            execution_time = time.time() - start_time
            self._update_hook_stats(hook, execution_time, True)
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            self._update_hook_stats(hook, execution_time, False)
            raise e
    
    def _execute_single_post_hook_safe(self, hook: PostHook, impulse: Any, source_queue: str, result: Any) -> Any:
        """安全执行单个后置Hook"""
        start_time = time.time()
        try:
            hook_result = hook.post_process(impulse, source_queue, result)
            execution_time = time.time() - start_time
            self._update_hook_stats(hook, execution_time, True)
            return hook_result
        except Exception as e:
            execution_time = time.time() - start_time
            self._update_hook_stats(hook, execution_time, False)
            raise e
    
    def _update_hook_stats(self, hook: BaseHook, execution_time: float, success: bool):
        """更新Hook统计信息"""
        with self._lock:
            hook_stats = self.execution_stats['hook_stats'][hook.hook_name]
            hook_stats['total_executions'] = hook_stats.get('total_executions', 0) + 1
            hook_stats['successful_executions'] = hook_stats.get('successful_executions', 0) + (1 if success else 0)
            hook_stats['total_execution_time'] = hook_stats.get('total_execution_time', 0.0) + execution_time
            hook_stats['avg_execution_time'] = hook_stats['total_execution_time'] / hook_stats['total_executions']
            hook_stats['success_rate'] = hook_stats['successful_executions'] / hook_stats['total_executions']
    
    def get_chain_stats(self) -> Dict[str, Any]:
        """获取链统计信息"""
        with self._lock:
            return {
                'chain_name': self.chain_name,
                'total_hooks': len(self.pre_hooks) + len(self.post_hooks) + len(self.error_hooks) + 
                               len(self.conditional_hooks) + len(self.async_hooks),
                'pre_hooks_count': len(self.pre_hooks),
                'post_hooks_count': len(self.post_hooks),
                'error_hooks_count': len(self.error_hooks),
                'conditional_hooks_count': len(self.conditional_hooks),
                'async_hooks_count': len(self.async_hooks),
                'execution_stats': dict(self.execution_stats),
                'enabled_hooks': [h.hook_name for hooks in [self.pre_hooks, self.post_hooks, self.error_hooks, 
                                                           self.conditional_hooks, self.async_hooks] for h in hooks if h.enabled]
            }
    
    def list_hooks(self) -> Dict[str, List[Dict[str, Any]]]:
        """列出所有Hook及其信息"""
        return {
            'pre_hooks': [self._get_hook_info(h) for h in self.pre_hooks],
            'post_hooks': [self._get_hook_info(h) for h in self.post_hooks],
            'error_hooks': [self._get_hook_info(h) for h in self.error_hooks],
            'conditional_hooks': [self._get_hook_info(h) for h in self.conditional_hooks],
            'async_hooks': [self._get_hook_info(h) for h in self.async_hooks]
        }
    
    def _get_hook_info(self, hook: BaseHook) -> Dict[str, Any]:
        """获取Hook信息"""
        return {
            'hook_name': hook.hook_name,
            'hook_type': getattr(hook, 'hook_type', 'base'),
            'priority': hook.priority,
            'enabled': hook.enabled,
            'stats': hook.get_stats() if hasattr(hook, 'get_stats') else {}
        }
    
    def enable_hook(self, hook_name: str) -> bool:
        """启用Hook"""
        hook = self.get_hook(hook_name)
        if hook:
            hook.enable()
            return True
        return False
    
    def disable_hook(self, hook_name: str) -> bool:
        """禁用Hook"""
        hook = self.get_hook(hook_name)
        if hook:
            hook.disable()
            return True
        return False
    
    def reorder_hooks(self, hook_type: str, new_order: List[str]) -> bool:
        """
        重新排序Hook
        
        Args:
            hook_type: Hook类型（pre, post, error, conditional, async）
            new_order: 新的Hook名称顺序
            
        Returns:
            bool: 是否成功重排序
        """
        hook_lists = {
            'pre': self.pre_hooks,
            'post': self.post_hooks,
            'error': self.error_hooks,
            'conditional': self.conditional_hooks,
            'async': self.async_hooks
        }
        
        if hook_type not in hook_lists:
            return False
            
        with self._lock:
            original_list = hook_lists[hook_type]
            hook_dict = {h.hook_name: h for h in original_list}
            
            # 验证新顺序
            for hook_name in new_order:
                if hook_name not in hook_dict:
                    return False
            
            # 重新排序
            new_list = [hook_dict[name] for name in new_order]
            setattr(self, f"{hook_type}_hooks", new_list)
            
        return True
    
    def save_to_dict(self) -> Dict[str, Any]:
        """将Hook链保存为字典格式"""
        return {
            'chain_name': self.chain_name,
            'max_workers': self.max_workers,
            'hooks': {
                'pre': [self._serialize_hook(h) for h in self.pre_hooks],
                'post': [self._serialize_hook(h) for h in self.post_hooks],
                'error': [self._serialize_hook(h) for h in self.error_hooks],
                'conditional': [self._serialize_hook(h) for h in self.conditional_hooks],
                'async': [self._serialize_hook(h) for h in self.async_hooks]
            }
        }
    
    def _serialize_hook(self, hook: BaseHook) -> Dict[str, Any]:
        """序列化Hook"""
        return {
            'hook_name': hook.hook_name,
            'hook_type': getattr(hook, 'hook_type', 'base'),
            'priority': hook.priority,
            'enabled': hook.enabled,
            'class_name': hook.__class__.__name__
        }


class HookChainManager:
    """Hook链管理器 - 管理多个Hook链"""
    
    def __init__(self):
        self.chains: Dict[str, HookChain] = {}
        self.global_hooks: List[BaseHook] = []
        self.logger = logging.getLogger("hook_chain_manager")
    
    def create_chain(self, chain_name: str, max_workers: int = 4) -> HookChain:
        """创建新的Hook链"""
        if chain_name in self.chains:
            self.logger.warning(f"Hook链 {chain_name} 已存在，返回现有链")
            return self.chains[chain_name]
            
        chain = HookChain(chain_name, max_workers)
        self.chains[chain_name] = chain
        self.logger.info(f"创建Hook链: {chain_name}")
        return chain
    
    def get_chain(self, chain_name: str) -> Optional[HookChain]:
        """获取Hook链"""
        return self.chains.get(chain_name)
    
    def delete_chain(self, chain_name: str) -> bool:
        """删除Hook链"""
        if chain_name in self.chains:
            del self.chains[chain_name]
            self.logger.info(f"删除Hook链: {chain_name}")
            return True
        return False
    
    def list_chains(self) -> List[str]:
        """列出所有链名称"""
        return list(self.chains.keys())
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有链的统计信息"""
        return {
            'total_chains': len(self.chains),
            'global_hooks_count': len(self.global_hooks),
            'chains': {name: chain.get_chain_stats() for name, chain in self.chains.items()}
        }
    
    def add_global_hook(self, hook: BaseHook):
        """添加全局Hook（应用到所有链）"""
        self.global_hooks.append(hook)
        
        # 添加到现有链
        for chain in self.chains.values():
            chain.add_hook(hook)
    
    def remove_global_hook(self, hook_name: str) -> bool:
        """移除全局Hook"""
        removed = False
        self.global_hooks = [h for h in self.global_hooks if h.hook_name != hook_name]
        
        # 从所有链中移除
        for chain in self.chains.values():
            if chain.remove_hook(hook_name):
                removed = True
                
        return removed


# 全局Hook链管理器实例
global_hook_manager = HookChainManager()

def get_hook_manager() -> HookChainManager:
    """获取全局Hook链管理器"""
    return global_hook_manager