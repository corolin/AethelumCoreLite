"""
日志分析模块

提供日志聚合、分析和智能洞察功能。
"""

import json
import time
import threading
import re
from typing import Any, Dict, List, Optional, Callable, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from enum import Enum
import statistics
import sqlite3
from pathlib import Path

from .structured_logger import LogEntry, LogLevel


class AggregationType(Enum):
    """聚合类型"""
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    RATE = "rate"
    PERCENTILE = "percentile"


class TimeWindow(Enum):
    """时间窗口"""
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR_1 = "1h"
    HOUR_6 = "6h"
    HOUR_24 = "24h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    
    def to_seconds(self) -> float:
        """转换为秒数"""
        mapping = {
            TimeWindow.MINUTE_1: 60,
            TimeWindow.MINUTE_5: 300,
            TimeWindow.MINUTE_15: 900,
            TimeWindow.HOUR_1: 3600,
            TimeWindow.HOUR_6: 21600,
            TimeWindow.HOUR_24: 86400,
            TimeWindow.DAY_1: 86400,
            TimeWindow.WEEK_1: 604800
        }
        return mapping.get(self, 3600)
    
    def to_pandas_freq(self) -> str:
        """转换为pandas频率字符串"""
        mapping = {
            TimeWindow.MINUTE_1: "1min",
            TimeWindow.MINUTE_5: "5min",
            TimeWindow.MINUTE_15: "15min",
            TimeWindow.HOUR_1: "1H",
            TimeWindow.HOUR_6: "6H",
            TimeWindow.HOUR_24: "1D",
            TimeWindow.DAY_1: "1D",
            TimeWindow.WEEK_1: "1W"
        }
        return mapping.get(self, "1H")


@dataclass
class LogPattern:
    """日志模式"""
    name: str
    pattern: str
    description: str = ""
    severity: LogLevel = LogLevel.INFO
    tags: List[str] = field(default_factory=list)
    regex: re.Pattern = field(init=False)
    
    def __post_init__(self):
        self.regex = re.compile(self.pattern, re.IGNORECASE)
    
    def match(self, message: str) -> Optional[Dict[str, str]]:
        """匹配日志消息"""
        match = self.regex.search(message)
        if match:
            return match.groupdict()
        return None


@dataclass
class AlertRule:
    """告警规则"""
    name: str
    condition: str  # 查询条件
    threshold: float
    time_window: TimeWindow
    aggregation: AggregationType
    severity: LogLevel = LogLevel.WARNING
    cooldown: float = 300  # 冷却时间（秒）
    enabled: bool = True
    last_triggered: Optional[float] = None
    trigger_count: int = 0
    
    def should_trigger(self, current_time: float, value: float) -> bool:
        """检查是否应该触发告警"""
        if not self.enabled:
            return False
        
        if self.last_triggered and current_time - self.last_triggered < self.cooldown:
            return False
        
        # 根据聚合类型判断
        if self.aggregation in [AggregationType.COUNT, AggregationType.SUM]:
            return value >= self.threshold
        elif self.aggregation == AggregationType.AVG:
            return value >= self.threshold
        elif self.aggregation in [AggregationType.MIN, AggregationType.MAX]:
            return value >= self.threshold
        elif self.aggregation == AggregationType.RATE:
            return value >= self.threshold
        
        return False
    
    def trigger(self, current_time: float):
        """触发告警"""
        self.last_triggered = current_time
        self.trigger_count += 1


class LogAggregator:
    """日志聚合器"""
    
    def __init__(self, db_path: str = "logs_analytics.db"):
        self.db_path = Path(db_path)
        self.lock = threading.RLock()
        self.patterns: List[LogPattern] = []
        self.alert_rules: List[AlertRule] = []
        self.alert_callbacks: List[Callable[[AlertRule, Dict[str, Any]], None]] = []
        
        self._init_database()
        self._load_default_patterns()
    
    def _init_database(self):
        """初始化数据库"""
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # 创建日志条目表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS log_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    level TEXT NOT NULL,
                    logger_name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    module TEXT,
                    function TEXT,
                    line_number INTEGER,
                    thread_id INTEGER,
                    thread_name TEXT,
                    process_id INTEGER,
                    session_id TEXT,
                    correlation_id TEXT,
                    user_id TEXT,
                    request_id TEXT,
                    tags TEXT,  -- JSON array
                    metadata TEXT,  -- JSON object
                    exception TEXT,  -- JSON object
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            ''')
            
            # 创建聚合表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS aggregated_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time_window TEXT NOT NULL,
                    timestamp_start REAL NOT NULL,
                    timestamp_end REAL NOT NULL,
                    level TEXT NOT NULL,
                    logger_name TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    unique_sessions INTEGER DEFAULT 0,
                    avg_message_length REAL DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    tags TEXT,  -- JSON array
                    patterns_matched TEXT,  -- JSON array
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON log_entries(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_level ON log_entries(level)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logger_name ON log_entries(logger_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_session_id ON log_entries(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_correlation_id ON log_entries(correlation_id)')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_agg_time_window ON aggregated_logs(time_window, timestamp_start)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_agg_level ON aggregated_logs(level)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_agg_logger_name ON aggregated_logs(logger_name)')
            
            conn.commit()
            conn.close()
    
    def add_log_entry(self, entry: LogEntry):
        """添加日志条目"""
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # 转换为JSON
            tags_json = json.dumps(entry.tags) if entry.tags else None
            metadata_json = json.dumps(entry.metadata) if entry.metadata else None
            exception_json = json.dumps(entry.exception) if entry.exception else None
            
            cursor.execute('''
                INSERT INTO log_entries (
                    timestamp, level, logger_name, message, module, function,
                    line_number, thread_id, thread_name, process_id, session_id,
                    correlation_id, user_id, request_id, tags, metadata, exception
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entry.timestamp, entry.level.name, entry.logger_name, entry.message,
                entry.module, entry.function, entry.line_number, entry.thread_id,
                entry.thread_name, entry.process_id, entry.session_id,
                entry.correlation_id, entry.user_id, entry.request_id,
                tags_json, metadata_json, exception_json
            ))
            
            conn.commit()
            conn.close()
            
            # 检查模式和告警
            self._check_patterns(entry)
            self._check_alerts(entry)
    
    def add_pattern(self, pattern: LogPattern):
        """添加日志模式"""
        self.patterns.append(pattern)
    
    def add_alert_rule(self, rule: AlertRule):
        """添加告警规则"""
        self.alert_rules.append(rule)
    
    def add_alert_callback(self, callback: Callable[[AlertRule, Dict[str, Any]], None]):
        """添加告警回调"""
        self.alert_callbacks.append(callback)
    
    def _load_default_patterns(self):
        """加载默认模式"""
        default_patterns = [
            LogPattern(
                name="error_exception",
                pattern=r"(?i)error|exception|failed|failure",
                description="错误和异常",
                severity=LogLevel.ERROR,
                tags=["error"]
            ),
            LogPattern(
                name="performance_slow",
                pattern=r"(?i)slow|timeout|performance|latency",
                description="性能问题",
                severity=LogLevel.WARNING,
                tags=["performance"]
            ),
            LogPattern(
                name="database_issue",
                pattern=r"(?i)database|connection|sql|query",
                description="数据库问题",
                severity=LogLevel.WARNING,
                tags=["database"]
            ),
            LogPattern(
                name="security_issue",
                pattern=r"(?i)security|auth|login|unauthorized|forbidden",
                description="安全问题",
                severity=LogLevel.WARNING,
                tags=["security"]
            ),
            LogPattern(
                name="impulse_processing",
                pattern=r"(?i)神经脉冲|impulse|session_id",
                description="神经脉冲处理",
                severity=LogLevel.INFO,
                tags=["impulse"]
            )
        ]
        
        self.patterns.extend(default_patterns)
    
    def _check_patterns(self, entry: LogEntry):
        """检查日志模式"""
        matched_patterns = []
        
        for pattern in self.patterns:
            match_result = pattern.match(entry.message)
            if match_result:
                matched_patterns.append({
                    'pattern_name': pattern.name,
                    'severity': pattern.severity.name,
                    'tags': pattern.tags,
                    'match_groups': match_result
                })
        
        # 如果有匹配的模式，记录到数据库
        if matched_patterns:
            self._store_pattern_matches(entry.session_id or entry.timestamp, matched_patterns)
    
    def _store_pattern_matches(self, key: Union[str, float], matches: List[Dict[str, Any]]):
        """存储模式匹配结果"""
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            matches_json = json.dumps(matches)
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pattern_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_key TEXT,
                    matches TEXT,
                    matched_at REAL DEFAULT (strftime('%s', 'now'))
                )
            ''')
            
            cursor.execute('INSERT INTO pattern_matches (entry_key, matches) VALUES (?, ?)',
                        (str(key), matches_json))
            
            conn.commit()
            conn.close()
    
    def _check_alerts(self, entry: LogEntry):
        """检查告警规则"""
        current_time = time.time()
        
        for rule in self.alert_rules:
            try:
                # 简单的计数告警实现
                if rule.aggregation == AggregationType.COUNT:
                    count = self._count_logs_in_window(
                        rule.condition, 
                        current_time - rule.time_window.to_seconds(), 
                        current_time
                    )
                    
                    if rule.should_trigger(current_time, count):
                        rule.trigger(current_time)
                        self._trigger_alert(rule, {'count': count, 'entry': entry.to_dict()})
                        
            except Exception as e:
                # 告警检查失败不应该影响日志系统
                pass
    
    def _count_logs_in_window(self, condition: str, start_time: float, end_time: float) -> int:
        """计算时间窗口内的日志数量"""
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # 简化的查询，实际应该支持更复杂的条件解析
            sql = "SELECT COUNT(*) FROM log_entries WHERE timestamp BETWEEN ? AND ?"
            params = [start_time, end_time]
            
            if condition:
                # 这里应该解析condition，现在简单处理
                if "level=ERROR" in condition:
                    sql += " AND level = ?"
                    params.append("ERROR")
            
            cursor.execute(sql, params)
            count = cursor.fetchone()[0]
            conn.close()
            
            return count
    
    def _trigger_alert(self, rule: AlertRule, data: Dict[str, Any]):
        """触发告警"""
        for callback in self.alert_callbacks:
            try:
                callback(rule, data)
            except Exception:
                pass
    
    def query_logs(self, query: Dict[str, Any], limit: int = 1000) -> List[Dict[str, Any]]:
        """查询日志"""
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 构建查询SQL
            sql, params = self._build_query(query)
            sql += f" ORDER BY timestamp DESC LIMIT {limit}"
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                result = dict(row)
                # 转换JSON字段
                if result['tags']:
                    result['tags'] = json.loads(result['tags'])
                if result['metadata']:
                    result['metadata'] = json.loads(result['metadata'])
                if result['exception']:
                    result['exception'] = json.loads(result['exception'])
                results.append(result)
            
            conn.close()
            return results
    
    def _build_query(self, query: Dict[str, Any]) -> Tuple[str, List]:
        """构建查询SQL"""
        conditions = []
        params = []
        
        # 时间范围
        if 'start_time' in query:
            conditions.append("timestamp >= ?")
            params.append(query['start_time'])
        
        if 'end_time' in query:
            conditions.append("timestamp <= ?")
            params.append(query['end_time'])
        
        # 日志级别
        if 'level' in query:
            if isinstance(query['level'], list):
                placeholders = ','.join(['?' for _ in query['level']])
                conditions.append(f"level IN ({placeholders})")
                params.extend(query['level'])
            else:
                conditions.append("level = ?")
                params.append(query['level'])
        
        # 日志记录器
        if 'logger_name' in query:
            conditions.append("logger_name = ?")
            params.append(query['logger_name'])
        
        # 会话ID
        if 'session_id' in query:
            conditions.append("session_id = ?")
            params.append(query['session_id'])
        
        # 关联ID
        if 'correlation_id' in query:
            conditions.append("correlation_id = ?")
            params.append(query['correlation_id'])
        
        # 消息内容
        if 'message_contains' in query:
            conditions.append("message LIKE ?")
            params.append(f"%{query['message_contains']}%")
        
        # 标签
        if 'tag' in query:
            conditions.append("tags LIKE ?")
            params.append(f"%\"{query['tag']}\"%")
        
        # 构建最终SQL
        sql = "SELECT * FROM log_entries"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        
        return sql, params
    
    def aggregate_logs(self, dimensions: List[str], time_window: TimeWindow, 
                      start_time: Optional[float] = None, end_time: Optional[float] = None,
                      filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """聚合日志"""
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # 确定时间范围
            if end_time is None:
                end_time = time.time()
            if start_time is None:
                start_time = end_time - time_window.to_seconds()
            
            # 构建聚合查询
            group_by_clauses = []
            select_clauses = []
            
            # 时间窗口分组
            window_seconds = time_window.to_seconds()
            select_clauses.append(f"(timestamp / {window_seconds}) * {window_seconds} as window_start")
            group_by_clauses.append("(timestamp / window_seconds) * window_seconds")
            
            # 维度分组
            for dim in dimensions:
                if dim == 'level':
                    select_clauses.append("level")
                    group_by_clauses.append("level")
                elif dim == 'logger_name':
                    select_clauses.append("logger_name")
                    group_by_clauses.append("logger_name")
                elif dim == 'hour':
                    select_clauses.append("strftime('%H', datetime(timestamp, 'unixepoch')) as hour")
                    group_by_clauses.append("hour")
                elif dim == 'date':
                    select_clauses.append("strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch')) as date")
                    group_by_clauses.append("date")
            
            # 聚合函数
            select_clauses.extend([
                "COUNT(*) as count",
                "COUNT(DISTINCT session_id) as unique_sessions",
                "AVG(LENGTH(message)) as avg_message_length",
                "SUM(CASE WHEN level IN ('ERROR', 'CRITICAL') THEN 1 ELSE 0 END) as error_count"
            ])
            
            sql = f"""
                SELECT {', '.join(select_clauses)}
                FROM log_entries
                WHERE timestamp BETWEEN ? AND ?
            """
            params = [start_time, end_time]
            
            # 添加过滤条件
            if filters:
                filter_sql, filter_params = self._build_query(filters)
                sql += " AND " + filter_sql[6:]  # 移除 "SELECT * FROM log_entries"
                params.extend(filter_params)
            
            sql += f" GROUP BY {', '.join(group_by_clauses)} ORDER BY window_start DESC"
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            # 转换结果
            results = []
            column_names = [description[0] for description in cursor.description]
            
            for row in rows:
                result = dict(zip(column_names, row))
                # 转换时间戳
                if 'window_start' in result:
                    result['window_start_timestamp'] = result['window_start']
                    result['window_start'] = datetime.fromtimestamp(result['window_start']).isoformat()
                results.append(result)
            
            conn.close()
            return results
    
    def get_log_statistics(self, time_window: TimeWindow = TimeWindow.HOUR_24) -> Dict[str, Any]:
        """获取日志统计信息"""
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            end_time = time.time()
            start_time = end_time - time_window.to_seconds()
            
            stats = {}
            
            # 总体统计
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_logs,
                    COUNT(DISTINCT logger_name) as unique_loggers,
                    COUNT(DISTINCT session_id) as unique_sessions,
                    AVG(LENGTH(message)) as avg_message_length
                FROM log_entries
                WHERE timestamp BETWEEN ? AND ?
            ''', [start_time, end_time])
            
            overall_stats = dict(zip(
                ['total_logs', 'unique_loggers', 'unique_sessions', 'avg_message_length'],
                cursor.fetchone()
            ))
            stats['overall'] = overall_stats
            
            # 按级别统计
            cursor.execute('''
                SELECT level, COUNT(*) as count
                FROM log_entries
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY level
                ORDER BY count DESC
            ''', [start_time, end_time])
            
            level_stats = [{'level': row[0], 'count': row[1]} for row in cursor.fetchall()]
            stats['by_level'] = level_stats
            
            # 按日志记录器统计
            cursor.execute('''
                SELECT logger_name, COUNT(*) as count
                FROM log_entries
                WHERE timestamp BETWEEN ? AND ?
                GROUP BY logger_name
                ORDER BY count DESC
                LIMIT 10
            ''', [start_time, end_time])
            
            logger_stats = [{'logger_name': row[0], 'count': row[1]} for row in cursor.fetchall()]
            stats['by_logger'] = logger_stats
            
            # 错误趋势（按小时）
            cursor.execute('''
                SELECT 
                    strftime('%Y-%m-%d %H:00:00', datetime(timestamp, 'unixepoch')) as hour,
                    COUNT(*) as error_count
                FROM log_entries
                WHERE timestamp BETWEEN ? AND ? AND level IN ('ERROR', 'CRITICAL')
                GROUP BY hour
                ORDER BY hour ASC
            ''', [start_time, end_time])
            
            error_trend = [{'hour': row[0], 'error_count': row[1]} for row in cursor.fetchall()]
            stats['error_trend'] = error_trend
            
            # 最活跃的会话
            cursor.execute('''
                SELECT session_id, COUNT(*) as count
                FROM log_entries
                WHERE timestamp BETWEEN ? AND ? AND session_id IS NOT NULL
                GROUP BY session_id
                ORDER BY count DESC
                LIMIT 10
            ''', [start_time, end_time])
            
            session_stats = [{'session_id': row[0], 'count': row[1]} for row in cursor.fetchall()]
            stats['active_sessions'] = session_stats
            
            conn.close()
            return stats
    
    def get_patterns_summary(self, time_window: TimeWindow = TimeWindow.HOUR_24) -> Dict[str, Any]:
        """获取模式匹配摘要"""
        end_time = time.time()
        start_time = end_time - time_window.to_seconds()
        
        # 这里简化实现，实际应该从pattern_matches表查询
        summary = {
            'total_patterns': len(self.patterns),
            'active_patterns': len([p for p in self.patterns if p.severity.value >= LogLevel.WARNING.value]),
            'patterns': [
                {
                    'name': p.name,
                    'description': p.description,
                    'severity': p.severity.name,
                    'tags': p.tags
                }
                for p in self.patterns
            ]
        }
        
        return summary
    
    def cleanup_old_logs(self, retention_days: int = 30):
        """清理旧日志"""
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cutoff_time = time.time() - (retention_days * 24 * 3600)
            
            cursor.execute("DELETE FROM log_entries WHERE timestamp < ?", [cutoff_time])
            deleted_count = cursor.rowcount
            
            cursor.execute("DELETE FROM pattern_matches WHERE matched_at < ?", [cutoff_time])
            cursor.execute("DELETE FROM aggregated_logs WHERE timestamp_end < ?", [cutoff_time])
            
            conn.commit()
            conn.close()
            
            return deleted_count


# 全局日志聚合器
_global_aggregator = LogAggregator()

def get_log_aggregator() -> LogAggregator:
    """获取全局日志聚合器"""
    return _global_aggregator

def add_log_pattern(name: str, pattern: str, description: str = "", 
                   severity: LogLevel = LogLevel.INFO, tags: List[str] = None):
    """添加日志模式"""
    log_pattern = LogPattern(
        name=name,
        pattern=pattern,
        description=description,
        severity=severity,
        tags=tags or []
    )
    _global_aggregator.add_pattern(log_pattern)

def add_log_alert(name: str, condition: str, threshold: float, 
                 time_window: TimeWindow, aggregation: AggregationType,
                 severity: LogLevel = LogLevel.WARNING):
    """添加日志告警规则"""
    alert_rule = AlertRule(
        name=name,
        condition=condition,
        threshold=threshold,
        time_window=time_window,
        aggregation=aggregation,
        severity=severity
    )
    _global_aggregator.add_alert_rule(alert_rule)

def query_logs(query: Dict[str, Any], limit: int = 1000) -> List[Dict[str, Any]]:
    """查询日志"""
    return _global_aggregator.query_logs(query, limit)

def get_log_statistics(time_window: TimeWindow = TimeWindow.HOUR_24) -> Dict[str, Any]:
    """获取日志统计"""
    return _global_aggregator.get_log_statistics(time_window)

def aggregate_logs(dimensions: List[str], time_window: TimeWindow,
                  start_time: Optional[float] = None, end_time: Optional[float] = None,
                  filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """聚合日志"""
    return _global_aggregator.aggregate_logs(
        dimensions, time_window, start_time, end_time, filters
    )