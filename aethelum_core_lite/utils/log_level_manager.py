"""
日志级别管理器

提供动态日志级别调整、条件日志控制和智能日志管理功能。
"""

import json
import time
import threading
import logging
from typing import Any, Dict, List, Optional, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import yaml
import watchdog.observers
import watchdog.events

from .structured_logger import LogLevel, StructuredLogger, get_structured_logger


class LogCondition(Enum):
    """日志条件枚举"""
    ALWAYS = "always"
    WORKING_HOURS = "working_hours"
    ERROR_MODE = "error_mode"
    DEBUG_MODE = "debug_mode"
    CUSTOM = "custom"


@dataclass
class LogLevelRule:
    """日志级别规则"""
    logger_name: str  # 支持通配符，如 "aethelum_core_lite.*"
    level: LogLevel
    condition: LogCondition = LogCondition.ALWAYS
    condition_params: Dict[str, Any] = None
    priority: int = 0  # 优先级，数值越大优先级越高
    expires_at: Optional[float] = None  # 过期时间（Unix时间戳）
    created_at: float = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.condition_params is None:
            self.condition_params = {}
    
    def is_expired(self) -> bool:
        """检查规则是否过期"""
        return self.expires_at is not None and time.time() > self.expires_at
    
    def is_applicable(self, current_context: Dict[str, Any] = None) -> bool:
        """检查规则是否适用"""
        if self.is_expired():
            return False
        
        if self.condition == LogCondition.ALWAYS:
            return True
        elif self.condition == LogCondition.WORKING_HOURS:
            return self._is_working_hours()
        elif self.condition == LogCondition.ERROR_MODE:
            return current_context and current_context.get('error_mode', False)
        elif self.condition == LogCondition.DEBUG_MODE:
            return current_context and current_context.get('debug_mode', False)
        elif self.condition == LogCondition.CUSTOM:
            custom_func = self.condition_params.get('custom_function')
            return custom_func and custom_func(current_context)
        
        return False
    
    def _is_working_hours(self) -> bool:
        """检查是否在工作时间"""
        from datetime import datetime
        
        now = datetime.now()
        work_hours = self.condition_params.get('hours', (9, 18))
        work_days = self.condition_params.get('days', range(0, 5))  # 0-6: 周一到周日
        
        if now.weekday() not in work_days:
            return False
        
        current_hour = now.hour
        return work_hours[0] <= current_hour < work_hours[1]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['level'] = self.level.name
        data['condition'] = self.condition.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LogLevelRule':
        """从字典创建规则"""
        data['level'] = LogLevel[data['level']]
        data['condition'] = LogCondition(data['condition'])
        return cls(**data)


class LogLevelManager:
    """日志级别管理器"""
    
    def __init__(self):
        self.rules: List[LogLevelRule] = []
        self.logger_levels: Dict[str, LogLevel] = {}  # 缓存当前生效的级别
        self.lock = threading.RLock()
        self.file_watcher = None
        self.config_file_path = None
        self.current_context = {}
        self.change_callbacks: List[Callable[[str, LogLevel, LogLevel], None]] = []
        
    def add_rule(self, rule: LogLevelRule):
        """添加日志级别规则"""
        with self.lock:
            self.rules.append(rule)
            self._update_logger_levels()
    
    def remove_rule(self, logger_name: str, level: LogLevel = None) -> bool:
        """移除日志级别规则"""
        with self.lock:
            original_count = len(self.rules)
            
            self.rules = [rule for rule in self.rules 
                         if not (rule.logger_name == logger_name and 
                                 (level is None or rule.level == level))]
            
            if len(self.rules) < original_count:
                self._update_logger_levels()
                return True
            return False
    
    def set_temporary_level(self, logger_name: str, level: LogLevel, 
                          duration: float, condition: LogCondition = LogCondition.ALWAYS,
                          condition_params: Dict[str, Any] = None):
        """设置临时日志级别"""
        rule = LogLevelRule(
            logger_name=logger_name,
            level=level,
            condition=condition,
            condition_params=condition_params or {},
            expires_at=time.time() + duration,
            priority=100  # 临时规则具有高优先级
        )
        self.add_rule(rule)
    
    def set_error_mode(self, enabled: bool = True, duration: float = 3600):
        """设置错误模式（只记录ERROR及以上级别）"""
        self.current_context['error_mode'] = enabled
        
        if enabled:
            self.set_temporary_level(
                logger_name="*",
                level=LogLevel.ERROR,
                duration=duration,
                condition=LogCondition.ERROR_MODE
            )
    
    def set_debug_mode(self, enabled: bool = True, duration: float = 1800):
        """设置调试模式（记录所有级别）"""
        self.current_context['debug_mode'] = enabled
        
        if enabled:
            self.set_temporary_level(
                logger_name="*",
                level=LogLevel.DEBUG,
                duration=duration,
                condition=LogCondition.DEBUG_MODE
            )
    
    def get_effective_level(self, logger_name: str) -> LogLevel:
        """获取日志记录器的有效级别"""
        with self.lock:
            # 检查缓存
            if logger_name in self.logger_levels:
                return self.logger_levels[logger_name]
            
            # 查找适用的规则
            applicable_rules = []
            
            for rule in self.rules:
                if rule.is_applicable(self.current_context) and self._match_logger_name(rule.logger_name, logger_name):
                    applicable_rules.append(rule)
            
            # 按优先级排序，选择最高优先级的规则
            if applicable_rules:
                applicable_rules.sort(key=lambda r: (r.priority, r.created_at), reverse=True)
                effective_level = applicable_rules[0].level
            else:
                effective_level = LogLevel.INFO  # 默认级别
            
            # 缓存结果
            self.logger_levels[logger_name] = effective_level
            return effective_level
    
    def _match_logger_name(self, pattern: str, logger_name: str) -> bool:
        """匹配日志记录器名称（支持通配符）"""
        if pattern == "*":
            return True
        
        if "*" in pattern:
            import fnmatch
            return fnmatch.fnmatch(logger_name, pattern)
        
        return pattern == logger_name
    
    def _update_logger_levels(self):
        """更新所有日志记录器的级别"""
        # 清空缓存
        self.logger_levels.clear()
        
        # 通知所有注册的回调
        for callback in self.change_callbacks:
            try:
                callback("*", None, None)  # 通知全局变更
            except Exception as e:
                # 回调错误不应该影响日志系统
                pass
    
    def add_change_callback(self, callback: Callable[[str, LogLevel, LogLevel], None]):
        """添加级别变更回调"""
        self.change_callbacks.append(callback)
    
    def remove_change_callback(self, callback: Callable[[str, LogLevel, LogLevel], None]):
        """移除级别变更回调"""
        if callback in self.change_callbacks:
            self.change_callbacks.remove(callback)
    
    def load_rules_from_file(self, file_path: str):
        """从文件加载规则"""
        self.config_file_path = Path(file_path)
        
        if not self.config_file_path.exists():
            return
        
        try:
            with open(self.config_file_path, 'r', encoding='utf-8') as f:
                if self.config_file_path.suffix.lower() in ['.yaml', '.yml']:
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
            
            with self.lock:
                self.rules.clear()
                for rule_data in data.get('rules', []):
                    rule = LogLevelRule.from_dict(rule_data)
                    if not rule.is_expired():
                        self.rules.append(rule)
                
                self._update_logger_levels()
            
            # 启动文件监控
            self._start_file_watcher()
            
        except Exception as e:
            raise RuntimeError(f"加载日志级别规则失败: {e}")
    
    def save_rules_to_file(self, file_path: str = None):
        """保存规则到文件"""
        if file_path is None:
            file_path = self.config_file_path
        
        if file_path is None:
            raise ValueError("未指定文件路径")
        
        file_path = Path(file_path)
        
        try:
            with self.lock:
                # 过滤掉临时和过期的规则
                persistent_rules = [
                    rule for rule in self.rules 
                    if rule.expires_at is None and not rule.is_expired()
                ]
                
                data = {
                    'rules': [rule.to_dict() for rule in persistent_rules]
                }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                if file_path.suffix.lower() in ['.yaml', '.yml']:
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
                else:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            
        except Exception as e:
            raise RuntimeError(f"保存日志级别规则失败: {e}")
    
    def _start_file_watcher(self):
        """启动文件监控"""
        if self.file_watcher is not None:
            return
        
        if self.config_file_path and self.config_file_path.exists():
            self.file_watcher = ConfigFileWatcher(self)
            self.file_watcher.start()
    
    def stop_file_watcher(self):
        """停止文件监控"""
        if self.file_watcher:
            self.file_watcher.stop()
            self.file_watcher = None
    
    def get_rules(self, include_expired: bool = False) -> List[LogLevelRule]:
        """获取规则列表"""
        with self.lock:
            if include_expired:
                return self.rules.copy()
            else:
                return [rule for rule in self.rules if not rule.is_expired()]
    
    def get_logger_level_info(self, logger_name: str) -> Dict[str, Any]:
        """获取日志记录器级别信息"""
        effective_level = self.get_effective_level(logger_name)
        
        applicable_rules = []
        for rule in self.rules:
            if rule.is_applicable(self.current_context) and self._match_logger_name(rule.logger_name, logger_name):
                applicable_rules.append(rule)
        
        applicable_rules.sort(key=lambda r: (r.priority, r.created_at), reverse=True)
        
        return {
            'logger_name': logger_name,
            'effective_level': effective_level.name,
            'applicable_rules': [rule.to_dict() for rule in applicable_rules[:5]]  # 只显示前5个规则
        }
    
    def update_context(self, **context):
        """更新当前上下文"""
        self.current_context.update(context)
        self._update_logger_levels()
    
    def clear_context(self):
        """清空上下文"""
        self.current_context.clear()
        self._update_logger_levels()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            total_rules = len(self.rules)
            active_rules = len([r for r in self.rules if not r.is_expired()])
            expired_rules = total_rules - active_rules
            
            rule_type_counts = {}
            for rule in self.rules:
                rule_type = rule.condition.value
                rule_type_counts[rule_type] = rule_type_counts.get(rule_type, 0) + 1
            
            return {
                'total_rules': total_rules,
                'active_rules': active_rules,
                'expired_rules': expired_rules,
                'rule_types': rule_type_counts,
                'current_context': self.current_context.copy(),
                'cached_logger_levels': len(self.logger_levels)
            }


class ConfigFileWatcher:
    """配置文件监控器"""
    
    def __init__(self, level_manager: LogLevelManager):
        self.level_manager = level_manager
        self.observer = None
    
    def start(self):
        """启动监控"""
        if self.level_manager.config_file_path:
            self.observer = watchdog.observers.Observer()
            self.observer.schedule(
                ConfigFileEventHandler(self.level_manager),
                str(self.level_manager.config_file_path.parent),
                recursive=False
            )
            self.observer.start()
    
    def stop(self):
        """停止监控"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None


class ConfigFileEventHandler(watchdog.events.FileSystemEventHandler):
    """配置文件事件处理器"""
    
    def __init__(self, level_manager: LogLevelManager):
        self.level_manager = level_manager
        self.last_modified = 0
    
    def on_modified(self, event):
        """文件修改事件"""
        if event.is_directory:
            return
        
        if str(event.src_path) == str(self.level_manager.config_file_path):
            # 防抖：避免短时间内重复处理
            current_time = time.time()
            if current_time - self.last_modified < 1.0:
                return
            
            self.last_modified = current_time
            
            # 重新加载规则
            try:
                self.level_manager.load_rules_from_file(str(self.level_manager.config_file_path))
            except Exception as e:
                # 加载失败不应该影响系统运行
                pass


class DynamicStructuredLogger(StructuredLogger):
    """动态结构化日志记录器"""
    
    def __init__(self, name: str, level_manager: LogLevelManager, **config):
        self.level_manager = level_manager
        super().__init__(name, **config)
        
        # 注册级别变更回调
        self.level_manager.add_change_callback(self._on_level_changed)
        self.current_level = self.level_manager.get_effective_level(name)
    
    def _log(self, level: LogLevel, message: str, exc_info=None, **kwargs):
        """重写日志方法，使用动态级别"""
        # 获取当前有效级别
        current_level = self.level_manager.get_effective_level(self.name)
        
        if level.value < current_level.value:
            return
        
        super()._log(level, message, exc_info, **kwargs)
    
    def _on_level_changed(self, logger_name: str, old_level: Optional[LogLevel], new_level: Optional[LogLevel]):
        """级别变更回调"""
        if logger_name == "*" or logger_name == self.name:
            self.current_level = self.level_manager.get_effective_level(self.name)
    
    def close(self):
        """关闭日志记录器"""
        self.level_manager.remove_change_callback(self._on_level_changed)
        super().close()


# 全局日志级别管理器
_global_level_manager = LogLevelManager()

def get_log_level_manager() -> LogLevelManager:
    """获取全局日志级别管理器"""
    return _global_level_manager

def create_dynamic_logger(name: str, **config) -> DynamicStructuredLogger:
    """创建动态日志记录器"""
    return DynamicStructuredLogger(name, _global_level_manager, **config)

def load_log_level_config(file_path: str):
    """加载日志级别配置"""
    _global_level_manager.load_rules_from_file(file_path)

def set_temp_log_level(logger_name: str, level: LogLevel, duration: float, 
                      condition: LogCondition = LogCondition.ALWAYS,
                      condition_params: Dict[str, Any] = None):
    """设置临时日志级别"""
    _global_level_manager.set_temporary_level(
        logger_name, level, duration, condition, condition_params
    )

def set_error_log_mode(enabled: bool = True, duration: float = 3600):
    """设置错误日志模式"""
    _global_level_manager.set_error_mode(enabled, duration)

def set_debug_log_mode(enabled: bool = True, duration: float = 1800):
    """设置调试日志模式"""
    _global_level_manager.set_debug_mode(enabled, duration)

def get_effective_log_level(logger_name: str) -> LogLevel:
    """获取有效日志级别"""
    return _global_level_manager.get_effective_level(logger_name)

def update_log_context(**context):
    """更新日志上下文"""
    _global_level_manager.update_context(**context)