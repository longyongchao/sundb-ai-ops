#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : monitoring_repository.py
@Author  : LI
@Date    : 2026
@Desc    : 监控历史和告警历史数据访问层
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import desc, and_, or_, func
from sqlalchemy.orm import Session

from server.db.session import session_scope
from server.db.models.diagnosis_model import MonitoringHistory, AlertHistory, DiagnosisReport
from server.utils import normalize_data, safe_json_dumps

logger = logging.getLogger(__name__)


class MonitoringRepository:
    """监控历史数据访问层"""
    
    @staticmethod
    def save_metrics(metrics: Dict[str, Any], session: Optional[Session] = None) -> Optional[int]:
        """
        保存监控指标到数据库
        
        @param metrics: 监控指标字典
        @param session: 数据库会话
        @return: 记录ID
        """
        try:
            normalized_metrics = normalize_data(metrics)
            
            with session if session else session_scope() as sess:
                record = MonitoringHistory(
                    timestamp=datetime.now(),
                    cpu_usage=float(normalized_metrics.get('cpu_usage', 0) or 0),
                    cpu_user=float(normalized_metrics.get('cpu_user', 0) or 0),
                    cpu_system=float(normalized_metrics.get('cpu_system', 0) or 0),
                    cpu_iowait=float(normalized_metrics.get('cpu_iowait', 0) or 0),
                    cpu_idle=float(normalized_metrics.get('cpu_idle', 1) or 1),
                    memory_usage=float(normalized_metrics.get('memory_usage', 0) or 0),
                    memory_used_gb=float(normalized_metrics.get('memory_used_gb', 0) or 0),
                    memory_total_gb=float(normalized_metrics.get('memory_total_gb', 0) or 0),
                    swap_usage=float(normalized_metrics.get('swap_usage', 0) or 0),
                    disk_io_util=float(normalized_metrics.get('disk_io_util', 0) or 0),
                    disk_io_read_mb=float(normalized_metrics.get('disk_io_read_mb', 0) or 0),
                    disk_io_write_mb=float(normalized_metrics.get('disk_io_write_mb', 0) or 0),
                    disk_latency_ms=float(normalized_metrics.get('disk_latency_ms', 0) or 0),
                    load_1m=float(normalized_metrics.get('load_1m', 0) or 0),
                    load_5m=float(normalized_metrics.get('load_5m', 0) or 0),
                    load_15m=float(normalized_metrics.get('load_15m', 0) or 0),
                    active_connections=int(normalized_metrics.get('active_connections', 0) or 0),
                    max_connections=int(normalized_metrics.get('max_connections', 100) or 100),
                    idle_connections=int(normalized_metrics.get('idle_connections', 0) or 0),
                    waiting_connections=int(normalized_metrics.get('waiting_connections', 0) or 0),
                    slow_query_count=int(normalized_metrics.get('slow_query_count', 0) or 0),
                    avg_query_time=float(normalized_metrics.get('avg_query_time', 0) or 0),
                    tps=int(normalized_metrics.get('tps', 0) or 0),
                    cache_hit_ratio=float(normalized_metrics.get('cache_hit_ratio', 0) or 0),
                    temp_files=int(normalized_metrics.get('temp_files', 0) or 0),
                    checkpoint_count=int(normalized_metrics.get('checkpoint_count', 0) or 0),
                    wal_files=int(normalized_metrics.get('wal_files', 0) or 0),
                    extra_metrics=normalized_metrics.get('extra_metrics')
                )
                sess.add(record)
                sess.commit()
                return record.id
        except Exception as e:
            logger.error(f"保存监控指标失败: {e}")
            return None
    
    @staticmethod
    def batch_save_metrics(metrics_list: List[Dict[str, Any]], session: Optional[Session] = None) -> int:
        """
        批量保存监控指标
        
        @param metrics_list: 监控指标列表
        @param session: 数据库会话
        @return: 成功保存的数量
        """
        try:
            with session if session else session_scope() as sess:
                records = []
                for metrics in metrics_list:
                    record = MonitoringHistory(
                        timestamp=metrics.get('timestamp', datetime.now()),
                        cpu_usage=metrics.get('cpu_usage', 0),
                        memory_usage=metrics.get('memory_usage', 0),
                        disk_io_util=metrics.get('disk_io_util', 0),
                        load_1m=metrics.get('load_1m', 0),
                        active_connections=metrics.get('active_connections', 0),
                        slow_query_count=metrics.get('slow_query_count', 0),
                        cache_hit_ratio=metrics.get('cache_hit_ratio', 0),
                        tps=metrics.get('tps', 0)
                    )
                    records.append(record)
                
                sess.bulk_save_objects(records)
                sess.commit()
                return len(records)
        except Exception as e:
            logger.error(f"批量保存监控指标失败: {e}")
            return 0
    
    @staticmethod
    def get_history(
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
        session: Optional[Session] = None
    ) -> List[Dict]:
        """
        获取监控历史数据
        
        @param start_time: 开始时间
        @param end_time: 结束时间
        @param limit: 返回数量限制
        @param session: 数据库会话
        @return: 监控历史列表
        """
        try:
            with session if session else session_scope() as sess:
                query = sess.query(MonitoringHistory)
                
                if start_time:
                    query = query.filter(MonitoringHistory.timestamp >= start_time)
                if end_time:
                    query = query.filter(MonitoringHistory.timestamp <= end_time)
                
                query = query.order_by(desc(MonitoringHistory.timestamp)).limit(limit)
                records = query.all()
                
                return [r.to_dict() for r in records]
        except Exception as e:
            logger.error(f"获取监控历史失败: {e}")
            return []
    
    @staticmethod
    def get_statistics(
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        获取监控统计信息
        
        @param start_time: 开始时间
        @param end_time: 结束时间
        @param session: 数据库会话
        @return: 统计信息
        """
        try:
            with session if session else session_scope() as sess:
                query = sess.query(MonitoringHistory)
                
                if start_time:
                    query = query.filter(MonitoringHistory.timestamp >= start_time)
                if end_time:
                    query = query.filter(MonitoringHistory.timestamp <= end_time)
                
                result = query.with_entities(
                    func.count(MonitoringHistory.id).label('count'),
                    func.avg(MonitoringHistory.cpu_usage).label('avg_cpu'),
                    func.max(MonitoringHistory.cpu_usage).label('max_cpu'),
                    func.avg(MonitoringHistory.memory_usage).label('avg_memory'),
                    func.max(MonitoringHistory.memory_usage).label('max_memory'),
                    func.avg(MonitoringHistory.disk_io_util).label('avg_io'),
                    func.max(MonitoringHistory.disk_io_util).label('max_io'),
                    func.avg(MonitoringHistory.slow_query_count).label('avg_slow_queries'),
                    func.max(MonitoringHistory.slow_query_count).label('max_slow_queries')
                ).first()
                
                return {
                    'count': result.count or 0,
                    'avg_cpu_usage': float(result.avg_cpu or 0),
                    'max_cpu_usage': float(result.max_cpu or 0),
                    'avg_memory_usage': float(result.avg_memory or 0),
                    'max_memory_usage': float(result.max_memory or 0),
                    'avg_disk_io_util': float(result.avg_io or 0),
                    'max_disk_io_util': float(result.max_io or 0),
                    'avg_slow_query_count': float(result.avg_slow_queries or 0),
                    'max_slow_query_count': int(result.max_slow_queries or 0)
                }
        except Exception as e:
            logger.error(f"获取监控统计失败: {e}")
            return {}
    
    @staticmethod
    def cleanup_old_data(days: int = 30, session: Optional[Session] = None) -> int:
        """
        清理旧数据
        
        @param days: 保留天数
        @param session: 数据库会话
        @return: 删除的记录数
        """
        try:
            with session if session else session_scope() as sess:
                cutoff_time = datetime.now() - timedelta(days=days)
                deleted = sess.query(MonitoringHistory).filter(
                    MonitoringHistory.timestamp < cutoff_time
                ).delete()
                sess.commit()
                return deleted
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")
            return 0


class AlertRepository:
    """告警历史数据访问层"""
    
    @staticmethod
    def save_alert(
        alert_type: str,
        alert_level: str,
        alert_message: str,
        metrics_snapshot: Dict[str, Any],
        threshold_value: float = 0,
        actual_value: float = 0,
        alert_source: str = 'auto_detector',
        session: Optional[Session] = None
    ) -> Optional[int]:
        """
        保存告警记录
        
        @param alert_type: 告警类型
        @param alert_level: 告警级别
        @param alert_message: 告警信息
        @param metrics_snapshot: 指标快照
        @param threshold_value: 阈值
        @param actual_value: 实际值
        @param alert_source: 告警来源
        @param session: 数据库会话
        @return: 告警ID
        """
        try:
            normalized_metrics = normalize_data(metrics_snapshot)
            normalized_threshold = float(threshold_value) if threshold_value is not None else 0.0
            normalized_actual = float(actual_value) if actual_value is not None else 0.0
            
            with session if session else session_scope() as sess:
                alert = AlertHistory(
                    alert_type=alert_type,
                    alert_level=alert_level,
                    alert_source=alert_source,
                    alert_title=f"{alert_type} - {alert_level.upper()}",
                    alert_message=alert_message,
                    metrics_snapshot=normalized_metrics,
                    threshold_value=normalized_threshold,
                    actual_value=normalized_actual,
                    status='active'
                )
                sess.add(alert)
                sess.commit()
                return alert.id
        except Exception as e:
            logger.error(f"保存告警记录失败: {e}")
            return None
    
    @staticmethod
    def get_alerts(
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        alert_type: Optional[str] = None,
        alert_level: Optional[str] = None,
        is_diagnosed: Optional[bool] = None,
        limit: int = 100,
        session: Optional[Session] = None
    ) -> List[Dict]:
        """
        获取告警历史
        
        @param start_time: 开始时间
        @param end_time: 结束时间
        @param alert_type: 告警类型
        @param alert_level: 告警级别
        @param is_diagnosed: 是否已诊断
        @param limit: 返回数量限制
        @param session: 数据库会话
        @return: 告警列表
        """
        try:
            with session if session else session_scope() as sess:
                query = sess.query(AlertHistory)
                
                if start_time:
                    query = query.filter(AlertHistory.created_at >= start_time)
                if end_time:
                    query = query.filter(AlertHistory.created_at <= end_time)
                if alert_type:
                    query = query.filter(AlertHistory.alert_type == alert_type)
                if alert_level:
                    query = query.filter(AlertHistory.alert_level == alert_level)
                if is_diagnosed is not None:
                    query = query.filter(AlertHistory.is_diagnosed == is_diagnosed)
                
                query = query.order_by(desc(AlertHistory.created_at)).limit(limit)
                alerts = query.all()
                
                return [a.to_dict() for a in alerts]
        except Exception as e:
            logger.error(f"获取告警历史失败: {e}")
            return []
    
    @staticmethod
    def update_diagnosis_info(
        alert_id: int,
        report_id: int,
        session: Optional[Session] = None
    ) -> bool:
        """
        更新告警的诊断信息
        
        @param alert_id: 告警ID
        @param report_id: 诊断报告ID
        @param session: 数据库会话
        @return: 是否成功
        """
        try:
            with session if session else session_scope() as sess:
                alert = sess.query(AlertHistory).filter(
                    AlertHistory.id == alert_id
                ).first()
                
                if alert:
                    alert.is_diagnosed = True
                    alert.diagnosis_report_id = report_id
                    alert.diagnosis_triggered_at = datetime.now()
                    sess.commit()
                    return True
                return False
        except Exception as e:
            logger.error(f"更新告警诊断信息失败: {e}")
            return False
    
    @staticmethod
    def get_statistics(
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        获取告警统计信息
        
        @param start_time: 开始时间
        @param end_time: 结束时间
        @param session: 数据库会话
        @return: 统计信息
        """
        try:
            with session if session else session_scope() as sess:
                query = sess.query(AlertHistory)
                
                if start_time:
                    query = query.filter(AlertHistory.created_at >= start_time)
                if end_time:
                    query = query.filter(AlertHistory.created_at <= end_time)
                
                total_count = query.count()
                diagnosed_count = query.filter(AlertHistory.is_diagnosed == True).count()
                
                type_stats = sess.query(
                    AlertHistory.alert_type,
                    func.count(AlertHistory.id).label('count')
                ).filter(
                    and_(
                        AlertHistory.created_at >= start_time if start_time else True,
                        AlertHistory.created_at <= end_time if end_time else True
                    )
                ).group_by(AlertHistory.alert_type).all()
                
                level_stats = sess.query(
                    AlertHistory.alert_level,
                    func.count(AlertHistory.id).label('count')
                ).filter(
                    and_(
                        AlertHistory.created_at >= start_time if start_time else True,
                        AlertHistory.created_at <= end_time if end_time else True
                    )
                ).group_by(AlertHistory.alert_level).all()
                
                return {
                    'total_count': total_count,
                    'diagnosed_count': diagnosed_count,
                    'undiagnosed_count': total_count - diagnosed_count,
                    'diagnosis_rate': round(diagnosed_count / total_count * 100, 2) if total_count > 0 else 0,
                    'by_type': {t.alert_type: t.count for t in type_stats},
                    'by_level': {l.alert_level: l.count for l in level_stats}
                }
        except Exception as e:
            logger.error(f"获取告警统计失败: {e}")
            return {}
    
    @staticmethod
    def get_active_alerts_count(session: Optional[Session] = None) -> int:
        """
        获取活跃告警数量
        
        @param session: 数据库会话
        @return: 活跃告警数量
        """
        try:
            with session if session else session_scope() as sess:
                return sess.query(AlertHistory).filter(
                    AlertHistory.status == 'active'
                ).count()
        except Exception as e:
            logger.error(f"获取活跃告警数量失败: {e}")
            return 0
    
    @staticmethod
    def update_status(
        alert_id: int,
        status: str,
        session: Optional[Session] = None
    ) -> bool:
        """
        更新告警状态
        
        @param alert_id: 告警ID
        @param status: 新状态 (active/resolved/acknowledged/ignored)
        @param session: 数据库会话
        @return: 是否成功
        """
        try:
            with session if session else session_scope() as sess:
                alert = sess.query(AlertHistory).filter(
                    AlertHistory.id == alert_id
                ).first()
                
                if alert:
                    alert.status = status
                    if status == 'resolved':
                        alert.resolved_at = datetime.now()
                    sess.commit()
                    return True
                return False
        except Exception as e:
            logger.error(f"更新告警状态失败: {e}")
            return False
