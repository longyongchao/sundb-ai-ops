#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : anomaly_detector.py
@Author  : LI
@Date    : 2026
@Desc    : 异常检测服务
            实现定时异常检测和自动触发诊断功能
"""

import time
import threading
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json

from server.db.repository.monitoring_repository import AlertRepository

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """告警严重程度"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    """告警类型"""
    CPU_HIGH = "NodeCpuHigh"
    MEMORY_HIGH = "NodeMemoryHigh"
    DISK_IO_HIGH = "HighDiskIO"
    SLOW_QUERY = "SlowQueryDetected"
    CONNECTION_EXHAUSTED = "ConnectionPoolExhausted"
    DEADLOCK = "DeadlockDetected"
    REPLICATION_LAG = "ReplicationLag"
    CACHE_HIT_LOW = "LowCacheHitRatio"
    LOCK_WAIT = "LockWaitDetected"
    BLOCKED_SESSION = "BlockedSessionDetected"
    IDLE_TRANSACTION = "IdleTransactionDetected"
    HIGH_ROLLBACK_RATE = "HighRollbackRate"


@dataclass
class Alert:
    """告警信息"""
    alertname: str
    severity: str
    instance: str
    description: str
    summary: str
    startsAt: str
    value: float = 0.0
    threshold: float = 0.0
    endsAt: Optional[str] = None


@dataclass
class AnomalyState:
    """异常状态"""
    is_anomaly: bool = False
    alerts: List[Alert] = field(default_factory=list)
    last_check_time: Optional[str] = None
    last_anomaly_time: Optional[str] = None
    last_diagnosis_time: Optional[str] = None
    consecutive_anomaly_count: int = 0
    metrics_snapshot: Dict[str, Any] = field(default_factory=dict)


class AnomalyDetector:
    """
    异常检测器
    
    实现基于阈值的异常检测，支持：
    1. 多指标联合检测
    2. 防抖动机制
    3. 自动触发诊断
    """
    
    DEFAULT_THRESHOLDS = {
        "cpu_usage": 0.80,
        "memory_usage": 0.85,
        "disk_io_util": 0.90,
        "slow_query_count": 10,
        "active_connections_ratio": 0.85,
        "replication_lag_seconds": 60,
        "cache_hit_ratio_min": 0.90,
        "lock_wait_count": 5,
        "blocked_session_count": 3,
        "idle_transaction_count": 5,
        "rollback_rate_max": 0.05
    }
    
    MIN_DIAGNOSIS_INTERVAL = 300
    
    ANOMALY_CONSECUTIVE_THRESHOLD = 2
    
    def __init__(
        self,
        thresholds: Optional[Dict[str, float]] = None,
        min_diagnosis_interval: int = 300,
        on_anomaly_detected: Optional[Callable] = None,
        on_diagnosis_triggered: Optional[Callable] = None
    ):
        """
        初始化异常检测器
        
        @param thresholds: 指标阈值配置
        @param min_diagnosis_interval: 最小诊断间隔（秒）
        @param on_anomaly_detected: 异常检测回调
        @param on_diagnosis_triggered: 诊断触发回调
        """
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.min_diagnosis_interval = min_diagnosis_interval
        self.on_anomaly_detected = on_anomaly_detected
        self.on_diagnosis_triggered = on_diagnosis_triggered
        
        self.state = AnomalyState()
        self.alert_history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._running = False
        self._scheduler = None
    
    def _to_float(self, value: Any, default: float = 0.0) -> float:
        """将任意数值类型转换为 float"""
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    
    def check_metrics(self, metrics: Dict[str, Any]) -> List[Alert]:
        """
        检查指标是否异常（核心：数据库指标）
        
        @param metrics: 监控指标数据
        @return: 告警列表
        """
        alerts = []
        now = datetime.now().isoformat()
        
        database = metrics.get("database", {})
        real_time = metrics.get("real_time", {})
        
        connections = database.get("connections", {})
        conn_usage_percent = self._to_float(connections.get("usage_percent", 0))
        if conn_usage_percent > self.thresholds["active_connections_ratio"] * 100:
            total = self._to_float(connections.get("total", 0))
            max_conn = self._to_float(connections.get("max_connections", 100))
            alerts.append(Alert(
                alertname=AlertType.CONNECTION_EXHAUSTED.value,
                severity="critical" if conn_usage_percent > 95 else "warning",
                instance=metrics.get("instance", "localhost"),
                description=f"数据库连接数使用率{conn_usage_percent:.1f}%（{total}/{max_conn}），超过阈值{self.thresholds['active_connections_ratio']*100:.0f}%",
                summary=f"{'CRITICAL' if conn_usage_percent > 95 else 'WARN'} {AlertType.CONNECTION_EXHAUSTED.value} {conn_usage_percent:.1f}%",
                startsAt=now,
                value=conn_usage_percent / 100.0,
                threshold=self.thresholds["active_connections_ratio"]
            ))
        
        cache = database.get("cache", {})
        cache_hit_ratio = self._to_float(cache.get("cache_hit_ratio", 100))
        if cache_hit_ratio < self.thresholds["cache_hit_ratio_min"] * 100:
            alerts.append(Alert(
                alertname=AlertType.CACHE_HIT_LOW.value,
                severity="warning",
                instance=metrics.get("instance", "localhost"),
                description=f"数据库缓存命中率{cache_hit_ratio:.1f}%，低于阈值{self.thresholds['cache_hit_ratio_min']*100:.0f}%",
                summary=f"WARN {AlertType.CACHE_HIT_LOW.value} {cache_hit_ratio:.1f}%",
                startsAt=now,
                value=cache_hit_ratio / 100.0,
                threshold=self.thresholds["cache_hit_ratio_min"]
            ))
        
        slow_queries = database.get("slow_queries", {})
        slow_query_count = self._to_float(slow_queries.get("count", 0))
        if slow_query_count > self.thresholds["slow_query_count"]:
            alerts.append(Alert(
                alertname=AlertType.SLOW_QUERY.value,
                severity="warning",
                instance=metrics.get("instance", "localhost"),
                description=f"检测到{int(slow_query_count)}条慢查询，超过阈值{self.thresholds['slow_query_count']}",
                summary=f"WARN {AlertType.SLOW_QUERY.value} Count={int(slow_query_count)}",
                startsAt=now,
                value=slow_query_count,
                threshold=self.thresholds["slow_query_count"]
            ))
        
        locks = database.get("locks", {})
        waiting_locks = self._to_float(locks.get("waiting_locks", 0))
        if waiting_locks > self.thresholds["lock_wait_count"]:
            alerts.append(Alert(
                alertname=AlertType.LOCK_WAIT.value,
                severity="warning",
                instance=metrics.get("instance", "localhost"),
                description=f"检测到{int(waiting_locks)}个锁等待，超过阈值{self.thresholds['lock_wait_count']}",
                summary=f"WARN {AlertType.LOCK_WAIT.value} Locks={int(waiting_locks)}",
                startsAt=now,
                value=waiting_locks,
                threshold=self.thresholds["lock_wait_count"]
            ))
        
        blocked_sessions = self._to_float(locks.get("blocked_sessions", 0))
        if blocked_sessions > self.thresholds["blocked_session_count"]:
            alerts.append(Alert(
                alertname=AlertType.BLOCKED_SESSION.value,
                severity="critical",
                instance=metrics.get("instance", "localhost"),
                description=f"检测到{int(blocked_sessions)}个阻塞会话，超过阈值{self.thresholds['blocked_session_count']}",
                summary=f"CRITICAL {AlertType.BLOCKED_SESSION.value} Blocked={int(blocked_sessions)}",
                startsAt=now,
                value=blocked_sessions,
                threshold=self.thresholds["blocked_session_count"]
            ))
        
        transactions = database.get("transactions", {})
        idle_in_transaction = self._to_float(transactions.get("idle_in_transaction", 0))
        if idle_in_transaction > self.thresholds["idle_transaction_count"]:
            alerts.append(Alert(
                alertname=AlertType.IDLE_TRANSACTION.value,
                severity="warning",
                instance=metrics.get("instance", "localhost"),
                description=f"检测到{int(idle_in_transaction)}个空闲事务，超过阈值{self.thresholds['idle_transaction_count']}",
                summary=f"WARN {AlertType.IDLE_TRANSACTION.value} Idle={int(idle_in_transaction)}",
                startsAt=now,
                value=idle_in_transaction,
                threshold=self.thresholds["idle_transaction_count"]
            ))
        
        performance = database.get("performance", {})
        rollback_rate = self._to_float(performance.get("rollback_rate", 0))
        if rollback_rate > self.thresholds["rollback_rate_max"] * 100:
            alerts.append(Alert(
                alertname=AlertType.HIGH_ROLLBACK_RATE.value,
                severity="warning",
                instance=metrics.get("instance", "localhost"),
                description=f"事务回滚率{rollback_rate:.2f}%，超过阈值{self.thresholds['rollback_rate_max']*100:.0f}%",
                summary=f"WARN {AlertType.HIGH_ROLLBACK_RATE.value} Rate={rollback_rate:.2f}%",
                startsAt=now,
                value=rollback_rate / 100.0,
                threshold=self.thresholds["rollback_rate_max"]
            ))
        
        cpu_usage = self._to_float(real_time.get("cpu_percent", 0)) / 100.0
        if cpu_usage > self.thresholds["cpu_usage"]:
            alerts.append(Alert(
                alertname=AlertType.CPU_HIGH.value,
                severity="critical" if cpu_usage > 0.95 else "warning",
                instance=metrics.get("instance", "localhost"),
                description=f"主机CPU使用率达到{cpu_usage*100:.1f}%，超过阈值{self.thresholds['cpu_usage']*100:.0f}%",
                summary=f"{'CRITICAL' if cpu_usage > 0.95 else 'WARN'} {AlertType.CPU_HIGH.value} CPU={cpu_usage*100:.1f}%",
                startsAt=now,
                value=cpu_usage,
                threshold=self.thresholds["cpu_usage"]
            ))
        
        memory_usage = self._to_float(real_time.get("memory_percent", 0)) / 100.0
        if memory_usage > self.thresholds["memory_usage"]:
            alerts.append(Alert(
                alertname=AlertType.MEMORY_HIGH.value,
                severity="critical" if memory_usage > 0.95 else "warning",
                instance=metrics.get("instance", "localhost"),
                description=f"主机内存使用率达到{memory_usage*100:.1f}%，超过阈值{self.thresholds['memory_usage']*100:.0f}%",
                summary=f"{'CRITICAL' if memory_usage > 0.95 else 'WARN'} {AlertType.MEMORY_HIGH.value} Memory={memory_usage*100:.1f}%",
                startsAt=now,
                value=memory_usage,
                threshold=self.thresholds["memory_usage"]
            ))
        
        disk_read = self._to_float(real_time.get("disk_read_mb", 0))
        disk_write = self._to_float(real_time.get("disk_write_mb", 0))
        disk_io_total = disk_read + disk_write
        disk_io_util = min(disk_io_total / 1000.0, 1.0)
        if disk_io_util > self.thresholds["disk_io_util"]:
            alerts.append(Alert(
                alertname=AlertType.DISK_IO_HIGH.value,
                severity="warning",
                instance=metrics.get("instance", "localhost"),
                description=f"主机磁盘I/O总量达到{disk_io_total:.1f}MB/s，超过阈值{self.thresholds['disk_io_util']*1000:.0f}MB/s",
                summary=f"WARN {AlertType.DISK_IO_HIGH.value} IO={disk_io_total:.1f}MB/s",
                startsAt=now,
                value=disk_io_util,
                threshold=self.thresholds["disk_io_util"]
            ))
        
        return alerts
    
    def detect(self, metrics: Dict[str, Any]) -> AnomalyState:
        """
        执行异常检测
        
        @param metrics: 监控指标数据
        @return: 异常状态
        """
        with self._lock:
            now = datetime.now()
            alerts = self.check_metrics(metrics)
            
            is_anomaly = len(alerts) > 0
            
            self.state.last_check_time = now.isoformat()
            self.state.metrics_snapshot = metrics
            
            if is_anomaly:
                self.state.consecutive_anomaly_count += 1
                self.state.last_anomaly_time = now.isoformat()
                
                if self.state.consecutive_anomaly_count >= self.ANOMALY_CONSECUTIVE_THRESHOLD:
                    self.state.is_anomaly = True
                    self.state.alerts = alerts
                    
                    for alert in alerts:
                        alert_dict = {
                            **alert.__dict__,
                            "detected_at": now.isoformat()
                        }
                        self.alert_history.append(alert_dict)
                        
                        try:
                            AlertRepository.save_alert(
                                alert_type=alert.alertname,
                                alert_level=alert.severity,
                                alert_message=alert.description,
                                metrics_snapshot=metrics,
                                threshold_value=alert.threshold,
                                actual_value=alert.value,
                                alert_source='auto_detector'
                            )
                            logger.info(f"告警已保存到数据库: {alert.alertname}")
                        except Exception as e:
                            logger.error(f"保存告警到数据库失败: {e}")
                    
                    if self.on_anomaly_detected:
                        try:
                            self.on_anomaly_detected(alerts, metrics)
                        except Exception as e:
                            logger.error(f"Error in anomaly callback: {e}")
            else:
                self.state.consecutive_anomaly_count = 0
                self.state.is_anomaly = False
                self.state.alerts = []
            
            return self.state
    
    def should_trigger_diagnosis(self) -> bool:
        """
        判断是否应该触发诊断
        
        @return: 是否触发诊断
        """
        if not self.state.is_anomaly:
            return False
        
        if self.state.last_diagnosis_time is None:
            return True
        
        last_time = datetime.fromisoformat(self.state.last_diagnosis_time)
        elapsed = (datetime.now() - last_time).total_seconds()
        
        return elapsed >= self.min_diagnosis_interval
    
    def trigger_diagnosis(self) -> bool:
        """
        触发诊断
        
        @return: 是否成功触发
        """
        if not self.should_trigger_diagnosis():
            return False
        
        with self._lock:
            self.state.last_diagnosis_time = datetime.now().isoformat()
        
        if self.on_diagnosis_triggered:
            try:
                self.on_diagnosis_triggered(self.state.alerts, self.state.metrics_snapshot)
                logger.info("Diagnosis triggered successfully")
                return True
            except Exception as e:
                logger.error(f"Error triggering diagnosis: {e}")
                return False
        
        return True
    
    def get_state(self) -> Dict[str, Any]:
        """
        获取当前状态
        
        @return: 状态信息
        """
        with self._lock:
            return {
                "is_anomaly": self.state.is_anomaly,
                "alerts": [a.__dict__ for a in self.state.alerts],
                "last_check_time": self.state.last_check_time,
                "last_anomaly_time": self.state.last_anomaly_time,
                "last_diagnosis_time": self.state.last_diagnosis_time,
                "consecutive_anomaly_count": self.state.consecutive_anomaly_count,
                "thresholds": self.thresholds
            }
    
    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取告警历史
        
        @param limit: 返回数量限制
        @return: 告警历史列表
        """
        with self._lock:
            return self.alert_history[-limit:]
    
    def clear_alert_history(self):
        """清空告警历史"""
        with self._lock:
            self.alert_history = []
    
    def update_thresholds(self, thresholds: Dict[str, float]):
        """
        更新阈值配置
        
        @param thresholds: 新的阈值配置
        """
        with self._lock:
            self.thresholds.update(thresholds)


_detector_instance: Optional[AnomalyDetector] = None
_detector_lock = threading.Lock()


def get_detector() -> AnomalyDetector:
    """
    获取全局异常检测器实例
    
    @return: 异常检测器实例
    """
    global _detector_instance
    
    with _detector_lock:
        if _detector_instance is None:
            _detector_instance = AnomalyDetector()
        return _detector_instance


def init_detector(
    thresholds: Optional[Dict[str, float]] = None,
    min_diagnosis_interval: int = 300,
    on_anomaly_detected: Optional[Callable] = None,
    on_diagnosis_triggered: Optional[Callable] = None
) -> AnomalyDetector:
    """
    初始化全局异常检测器
    
    @param thresholds: 指标阈值配置
    @param min_diagnosis_interval: 最小诊断间隔
    @param on_anomaly_detected: 异常检测回调
    @param on_diagnosis_triggered: 诊断触发回调
    @return: 异常检测器实例
    """
    global _detector_instance
    
    with _detector_lock:
        _detector_instance = AnomalyDetector(
            thresholds=thresholds,
            min_diagnosis_interval=min_diagnosis_interval,
            on_anomaly_detected=on_anomaly_detected,
            on_diagnosis_triggered=on_diagnosis_triggered
        )
        return _detector_instance
