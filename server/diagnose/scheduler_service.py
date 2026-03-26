#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : scheduler_service.py
@Author  : LI
@Date    : 2026
@Desc    : 定时任务调度服务
            实现监控数据采集、异常检测、数据持久化、自动诊断触发
"""

import time
import threading
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import json

logger = logging.getLogger(__name__)

SCHEDULER_AVAILABLE = False
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
    SCHEDULER_AVAILABLE = True
except ImportError:
    logger.warning("APScheduler not installed, using simple threading scheduler")


class SimpleScheduler:
    """简单的定时任务调度器（当APScheduler不可用时使用）"""
    
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._threads: Dict[str, threading.Thread] = {}
    
    def add_job(self, func: Callable, trigger: str, id: str, **kwargs):
        """添加定时任务"""
        interval = kwargs.get('seconds', 60)
        
        def job_wrapper():
            while self._running:
                try:
                    func()
                except Exception as e:
                    logger.error(f"Job {id} error: {e}")
                
                time.sleep(interval)
        
        self._jobs[id] = {
            'func': func,
            'interval': interval,
            'wrapper': job_wrapper
        }
    
    def start(self):
        """启动调度器"""
        self._running = True
        for job_id, job in self._jobs.items():
            thread = threading.Thread(target=job['wrapper'], daemon=True, name=f"job_{job_id}")
            thread.start()
            self._threads[job_id] = thread
        logger.info(f"SimpleScheduler started with {len(self._jobs)} jobs")
    
    def shutdown(self, wait: bool = True):
        """关闭调度器"""
        self._running = False
        if wait:
            for thread in self._threads.values():
                thread.join(timeout=5)
        logger.info("SimpleScheduler shutdown")
    
    def get_jobs(self):
        """获取所有任务"""
        return list(self._jobs.keys())
    
    def remove_job(self, job_id: str):
        """移除任务"""
        if job_id in self._jobs:
            del self._jobs[job_id]


class SchedulerService:
    """
    定时任务调度服务
    
    提供四个核心定时任务：
    1. 监控数据采集（10秒/次）
    2. 异常检测判断（30秒/次）
    3. 监控数据持久化（1分钟/次）
    4. 告警数据清理（每天一次）
    """
    
    def __init__(self):
        self._scheduler = None
        self._running = False
        self._metrics_collector = None
        self._anomaly_detector = None
        self._auto_diagnosis_enabled = True
        self._latest_metrics: Dict[str, Any] = {}
        self._metrics_buffer: List[Dict[str, Any]] = []
        self._metrics_history: list = []
        self._lock = threading.Lock()
        self._last_persist_time = None
    
    def initialize(
        self,
        metrics_collector: Optional[Callable] = None,
        anomaly_detector: Optional[Any] = None,
        auto_diagnosis_enabled: bool = True
    ):
        """
        初始化调度服务
        
        @param metrics_collector: 指标采集函数
        @param anomaly_detector: 异常检测器实例
        @param auto_diagnosis_enabled: 是否启用自动诊断
        """
        self._metrics_collector = metrics_collector
        self._anomaly_detector = anomaly_detector
        self._auto_diagnosis_enabled = auto_diagnosis_enabled
        
        if SCHEDULER_AVAILABLE:
            self._scheduler = BackgroundScheduler()
            logger.info("Using APScheduler")
        else:
            self._scheduler = SimpleScheduler()
            logger.info("Using SimpleScheduler")
    
    def _collect_metrics_job(self):
        """监控数据采集任务（10秒/次）"""
        try:
            if self._metrics_collector:
                metrics = self._metrics_collector()
                if metrics:
                    with self._lock:
                        self._latest_metrics = metrics
                        self._metrics_buffer.append({
                            'timestamp': datetime.now(),
                            'metrics': metrics
                        })
                        self._metrics_history.append({
                            'timestamp': datetime.now().isoformat(),
                            'metrics': metrics
                        })
                        if len(self._metrics_history) > 1000:
                            self._metrics_history = self._metrics_history[-1000:]
                    logger.debug(f"Metrics collected: CPU={metrics.get('cpu_usage', 0):.2%}")
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
    
    def _anomaly_detection_job(self):
        """异常检测任务（30秒/次）"""
        try:
            with self._lock:
                metrics = self._latest_metrics.copy()
            
            if not metrics:
                return
            
            if self._anomaly_detector:
                state = self._anomaly_detector.detect(metrics)
                
                if state.is_anomaly:
                    logger.warning(f"Anomaly detected! Alerts: {len(state.alerts)}")
                    
                    for alert in state.alerts:
                        self._save_alert_to_db(alert, metrics)
                    
                    if self._auto_diagnosis_enabled and self._anomaly_detector.should_trigger_diagnosis():
                        self._trigger_auto_diagnosis(state.alerts, metrics)
        except Exception as e:
            logger.error(f"Error in anomaly detection: {e}")
    
    def _persist_metrics_job(self):
        """监控数据持久化任务（1分钟/次）"""
        try:
            with self._lock:
                if not self._metrics_buffer:
                    return
                
                metrics_to_save = self._metrics_buffer.copy()
                self._metrics_buffer = []
            
            saved_count = self._batch_save_metrics(metrics_to_save)
            self._last_persist_time = datetime.now()
            logger.debug(f"Persisted {saved_count} metrics records to database")
            
        except Exception as e:
            logger.error(f"Error persisting metrics: {e}")
    
    def _cleanup_old_data_job(self):
        """清理旧数据任务（每天一次）"""
        try:
            from server.db.repository.monitoring_repository import MonitoringRepository
            
            deleted = MonitoringRepository.cleanup_old_data(days=30)
            logger.info(f"Cleaned up {deleted} old monitoring records")
            
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
    
    def _save_alert_to_db(self, alert, metrics: Dict[str, Any]):
        """保存告警到数据库"""
        try:
            from server.db.repository.monitoring_repository import AlertRepository
            
            alert_id = AlertRepository.save_alert(
                alert_type=alert.alertname,
                alert_level=alert.severity,
                alert_message=alert.description,
                metrics_snapshot=metrics,
                threshold_value=alert.threshold,
                actual_value=alert.value,
                alert_source='auto_detector'
            )
            
            if alert_id:
                logger.info(f"Alert saved to database: ID={alert_id}, Type={alert.alertname}")
            
            return alert_id
            
        except Exception as e:
            logger.error(f"Error saving alert to database: {e}")
            return None
    
    def _batch_save_metrics(self, metrics_list: List[Dict]) -> int:
        """批量保存监控数据到数据库"""
        try:
            from server.db.repository.monitoring_repository import MonitoringRepository
            
            return MonitoringRepository.batch_save_metrics(metrics_list)
            
        except Exception as e:
            logger.error(f"Error batch saving metrics: {e}")
            return 0
    
    def _trigger_auto_diagnosis(self, alerts: list, metrics: Dict[str, Any]):
        """触发自动诊断"""
        try:
            logger.info("Triggering auto diagnosis...")
            
            from server.diagnose.diagnose import quick_diagnose
            from server.db.repository.monitoring_repository import AlertRepository
            from server.diagnose.notification_api import create_diagnosis_notification, create_alert_notification
            from server.diagnose.progress_manager import register_async_task, unregister_async_task, get_all_running_tasks
            import asyncio
            import os
            import threading
            
            alert_types = [a.alertname for a in alerts] if alerts else ["Unknown"]
            
            for alert in alerts:
                create_alert_notification(
                    alert_type=alert.alertname,
                    alert_message=alert.description,
                    severity=alert.severity
                )
            
            # 生成统一的任务ID（包含 auto 前缀）
            diagnosis_id = f"diag_auto_{int(time.time())}_{os.urandom(4).hex()}"
            logger.info(f"[AUTO_DIAG] 生成任务ID: {diagnosis_id}")
            
            diagnosis_input = {
                "anomaly_type": alert_types[0] if alert_types else "Unknown",
                "anomaly_description": f"自动检测到异常: {', '.join(alert_types)}",
                "metrics": metrics,
                "alerts": [a.__dict__ for a in alerts] if alerts else [],
                "auto_triggered": True,
                "diagnosis_id": diagnosis_id
            }
            
            self._anomaly_detector.trigger_diagnosis()
            
            # ========== 核心修复：确保任务100%注册到全局字典 ==========
            task = None
            registered = False
            
            try:
                # 方案1：尝试在当前线程获取事件循环
                try:
                    loop = asyncio.get_event_loop()
                    if loop and loop.is_running():
                        # 有运行中的事件循环，创建异步任务
                        task = asyncio.create_task(quick_diagnose(diagnosis_input))
                        register_async_task(diagnosis_id, task)
                        registered = True
                        logger.info(f"[TASK] 注册自动诊断任务（异步模式）: {diagnosis_id}")
                        
                        # 添加完成回调
                        def on_task_done(t):
                            unregister_async_task(diagnosis_id)
                            logger.info(f"[TASK] 自动诊断任务完成，已注销: {diagnosis_id}")
                        
                        task.add_done_callback(on_task_done)
                    else:
                        # 事件循环未运行，使用同步模式但强制注册
                        logger.info(f"[AUTO_DIAG] 事件循环未运行，使用同步模式")
                        
                        # 创建一个模拟任务对象用于跟踪
                        class SyncTaskWrapper:
                            """同步任务的包装器，用于跟踪任务状态"""
                            def __init__(self, diagnosis_id):
                                self.diagnosis_id = diagnosis_id
                                self._cancelled = False
                                self._done = False
                                self._result = None
                            
                            def cancel(self):
                                """取消任务"""
                                self._cancelled = True
                            
                            def done(self):
                                """标记任务完成"""
                                self._done = True
                            
                            def cancelled(self):
                                return self._cancelled
                            
                            def set_result(self, result):
                                self._result = result
                        
                        # 创建任务包装器并注册
                        sync_task = SyncTaskWrapper(diagnosis_id)
                        register_async_task(diagnosis_id, sync_task)
                        logger.info(f"[TASK] 注册自动诊断任务（同步模式）: {diagnosis_id}")
                        
                        try:
                            result = loop.run_until_complete(quick_diagnose(diagnosis_input))
                            sync_task.set_result(result)
                        except Exception as e:
                            logger.error(f"[AUTO_DIAG] 同步执行错误: {e}")
                        finally:
                            unregister_async_task(diagnosis_id)
                            logger.info(f"[TASK] 同步任务完成，已注销: {diagnosis_id}")
                except RuntimeError as e:
                    # 方案2： 没有事件循环，尝试创建新的事件循环
                    logger.info(f"[AUTO_DIAG] 无事件循环，创建新循环执行: {e}")
                    
                    # 创建新的事件循环来运行任务
                    async def run_diagnosis_with_tracking():
                        """在新事件循环中运行诊断并跟踪"""
                        try:
                            # 在新循环中，需要重新注册任务
                            current_task = asyncio.current_task()
                            if current_task:
                                register_async_task(diagnosis_id, current_task)
                                logger.info(f"[TASK] 注册自动诊断任务（新循环模式）: {diagnosis_id}")
                            
                            result = await quick_diagnose(diagnosis_input)
                            return result
                        except asyncio.CancelledError:
                            logger.info(f"[TASK] 自动诊断任务被取消: {diagnosis_id}")
                            unregister_async_task(diagnosis_id)
                            raise
                        except Exception as e:
                            logger.error(f"[AUTO_DIAG] 诊断执行错误: {e}")
                            unregister_async_task(diagnosis_id)
                            raise
                        finally:
                            # 确保任务被注销
                            if get_all_running_tasks().get(diagnosis_id):
                                unregister_async_task(diagnosis_id)
                                logger.info(f"[TASK] 自动诊断任务已注销: {diagnosis_id}")
                    
                    # 在新线程中运行异步任务
                    def run_in_thread():
                        """在新线程中运行诊断任务"""
                        try:
                            asyncio.run(run_diagnosis_with_tracking())
                        except Exception as e:
                            logger.error(f"[AUTO_DIAG] 线程执行错误: {e}")
                    
                    # 启动新线程执行
                    thread = threading.Thread(target=run_in_thread, daemon=True)
                    thread.start()
                    logger.info(f"[AUTO_DIAG] 已在新线程中启动诊断任务: {diagnosis_id}")
                    registered = True
                    
            except Exception as e:
                logger.error(f"[AUTO_DIAG] 任务创建失败: {e}")
            
            if task:
                logger.info(f"[AUTO_DIAG] 异步任务已创建: {diagnosis_id}")
            elif registered:
                logger.info(f"[AUTO_DIAG] 任务已在新线程中启动")
            else:
                logger.warning(f"[AUTO_DIAG] 任务未能注册到全局字典，可能无法被取消")
            
            logger.info("Auto diagnosis triggered successfully")
            
        except Exception as e:
            logger.error(f"Error triggering auto diagnosis: {e}")
    
    def start(self):
        """启动调度服务"""
        if self._running:
            return
        
        self._scheduler.add_job(
            self._collect_metrics_job,
            trigger='interval',
            seconds=10,
            id='metrics_collector'
        )
        
        self._scheduler.add_job(
            self._anomaly_detection_job,
            trigger='interval',
            seconds=30,
            id='anomaly_detector'
        )
        
        self._scheduler.add_job(
            self._persist_metrics_job,
            trigger='interval',
            seconds=60,
            id='metrics_persister'
        )
        
        self._scheduler.add_job(
            self._cleanup_old_data_job,
            trigger='interval',
            seconds=86400,
            id='data_cleanup'
        )
        
        self._scheduler.start()
        self._running = True
        logger.info("Scheduler service started with 4 jobs (auto-start enabled)")
    
    def stop(self):
        """停止调度服务"""
        if not self._running:
            return
        
        if self._metrics_buffer:
            self._persist_metrics_job()
        
        self._scheduler.shutdown(wait=True)
        self._running = False
        logger.info("Scheduler service stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """获取调度服务状态"""
        return {
            "running": self._running,
            "auto_diagnosis_enabled": self._auto_diagnosis_enabled,
            "jobs": self._scheduler.get_jobs() if self._scheduler else [],
            "latest_metrics": self._latest_metrics,
            "metrics_buffer_size": len(self._metrics_buffer),
            "metrics_history_count": len(self._metrics_history),
            "last_persist_time": self._last_persist_time.isoformat() if self._last_persist_time else None
        }
    
    def get_latest_metrics(self) -> Dict[str, Any]:
        """获取最新指标数据"""
        with self._lock:
            return self._latest_metrics.copy()
    
    def get_metrics_history(self, limit: int = 100) -> list:
        """获取指标历史数据"""
        with self._lock:
            return self._metrics_history[-limit:]
    
    def set_auto_diagnosis(self, enabled: bool):
        """设置自动诊断开关"""
        self._auto_diagnosis_enabled = enabled
        logger.info(f"Auto diagnosis {'enabled' if enabled else 'disabled'}")
    
    def pause_monitoring(self):
        """暂停监控（暂停所有定时任务 + 取消正在运行的诊断任务）"""
        if not self._running:
            logger.warning("Scheduler not running, cannot pause")
            return False
        
        try:
            # 第一步：取消所有正在运行的诊断任务
            from server.diagnose.progress_manager import cancel_all_async_tasks, get_all_running_tasks
            
            running_tasks = get_all_running_tasks()
            task_count = len(running_tasks)
            
            if task_count > 0:
                cancel_results = cancel_all_async_tasks()
                success_count = len([r for r in cancel_results.values() if r])
                logger.info(f"[MONITORING] 取消了 {success_count}/{task_count} 个正在运行的诊断任务")
                print(f"[MONITORING] 任务ID列表: {list(running_tasks.keys())}")
            else:
                logger.info("[MONITORING] 没有正在运行的诊断任务")
            
            # 第二步：暂停调度器定时任务
            if SCHEDULER_AVAILABLE and hasattr(self._scheduler, 'pause'):
                for job in self._scheduler.get_jobs():
                    self._scheduler.pause_job(job.id)
                logger.info(f"All monitoring jobs paused (APScheduler), cancelled {task_count} diagnosis tasks")
            else:
                # ✅ 核心修复：直接修改 SimpleScheduler 实例内部的 _running 变量
                if hasattr(self._scheduler, '_running'):
                    self._scheduler._running = False
                    logger.info("[MONITORING] SimpleScheduler._running 已设置为 False")
                self._running = False
                logger.info(f"SimpleScheduler paused, cancelled {task_count} diagnosis tasks")
            
            return True
        except Exception as e:
            logger.error(f"Error pausing monitoring: {e}")
            return False
    
    def resume_monitoring(self):
        """恢复监控（恢复所有定时任务）"""
        try:
            if SCHEDULER_AVAILABLE and hasattr(self._scheduler, 'resume'):
                for job in self._scheduler.get_jobs():
                    self._scheduler.resume_job(job.id)
                self._running = True
                logger.info("All monitoring jobs resumed (APScheduler)")
            else:
                # ✅ 核心修复：恢复 SimpleScheduler 的运行状态，并重新启动线程
                if hasattr(self._scheduler, '_running') and not self._scheduler._running:
                    self._scheduler._running = True
                    # SimpleScheduler 停止后线程会退出，需要重新启动线程
                    # 但不要重新添加任务，因为任务已经在 _jobs 字典中
                    for job_id, job in self._scheduler._jobs.items():
                        if job_id not in self._scheduler._threads or not self._scheduler._threads[job_id].is_alive():
                            thread = threading.Thread(target=job['wrapper'], daemon=True, name=f"job_{job_id}")
                            thread.start()
                            self._scheduler._threads[job_id] = thread
                    logger.info("[MONITORING] SimpleScheduler._running 已设置为 True，并重新启动线程")
                self._running = True
                logger.info("SimpleScheduler resumed")
            
            return True
        except Exception as e:
            logger.error(f"Error resuming monitoring: {e}")
            return False
    
    def is_monitoring_active(self) -> bool:
        """检查监控是否活跃"""
        return self._running


_scheduler_instance: Optional[SchedulerService] = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> SchedulerService:
    """获取全局调度服务实例"""
    global _scheduler_instance
    
    with _scheduler_lock:
        if _scheduler_instance is None:
            _scheduler_instance = SchedulerService()
        return _scheduler_instance


def init_scheduler(
    metrics_collector: Optional[Callable] = None,
    anomaly_detector: Optional[Any] = None,
    auto_diagnosis_enabled: bool = True,
    auto_start: bool = True
) -> SchedulerService:
    """
    初始化全局调度服务
    
    @param metrics_collector: 指标采集函数
    @param anomaly_detector: 异常检测器实例
    @param auto_diagnosis_enabled: 是否启用自动诊断
    @param auto_start: 是否自动启动
    @return: 调度服务实例
    """
    global _scheduler_instance
    
    with _scheduler_lock:
        _scheduler_instance = SchedulerService()
        _scheduler_instance.initialize(
            metrics_collector=metrics_collector,
            anomaly_detector=anomaly_detector,
            auto_diagnosis_enabled=auto_diagnosis_enabled
        )
        
        if auto_start:
            _scheduler_instance.start()
            logger.info("Scheduler service auto-started")
        
        return _scheduler_instance
