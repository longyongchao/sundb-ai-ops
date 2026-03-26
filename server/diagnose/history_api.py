#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : history_api.py
@Author  : LI
@Date    : 2026
@Desc    : 历史数据查询 API
            提供监控历史、告警历史、统计信息的查询接口
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import Query, Body
from pydantic import BaseModel
from server.utils import BaseResponse, ListResponse
from server.db.repository.monitoring_repository import MonitoringRepository, AlertRepository


class UpdateAlertStatusRequest(BaseModel):
    """更新告警状态请求"""
    status: str  # active/resolved/acknowledged/ignored


async def update_alert_status(
    alert_id: int,
    request: UpdateAlertStatusRequest = Body(...)
) -> BaseResponse:
    """
    更新告警状态
    
    @param alert_id: 告警ID
    @param request: 状态更新请求
    @return: 更新结果
    """
    try:
        success = AlertRepository.update_status(
            alert_id=alert_id,
            status=request.status
        )
        if success:
            return BaseResponse(
                code=200,
                msg="Status updated successfully",
                data={"alert_id": alert_id, "status": request.status}
            )
        else:
            return BaseResponse(
                code=404,
                msg=f"Alert not found: {alert_id}",
                data=None
            )
    except Exception as e:
        return BaseResponse(
            code=500,
            msg=f"Error: {str(e)}",
            data=None
        )


async def get_monitoring_history(
    start_time: Optional[str] = Query(None, description="开始时间 (ISO格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO格式)"),
    hours: Optional[int] = Query(24, description="最近N小时（默认24小时）"),
    limit: int = Query(1000, description="返回数量限制")
) -> ListResponse:
    """
    获取监控历史数据
    
    @param start_time: 开始时间 (ISO格式，如 2024-01-01T00:00:00)
    @param end_time: 结束时间 (ISO格式)
    @param hours: 最近N小时（当start_time未指定时使用）
    @param limit: 返回数量限制
    @return: 监控历史列表
    """
    try:
        if start_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        else:
            start_dt = datetime.now() - timedelta(hours=hours)
        
        if end_time:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        else:
            end_dt = datetime.now()
        
        history = MonitoringRepository.get_history(
            start_time=start_dt,
            end_time=end_dt,
            limit=limit
        )
        
        return ListResponse(
            code=200,
            msg="Success",
            data=history
        )
    except Exception as e:
        return ListResponse(
            code=500,
            msg=f"Error: {str(e)}",
            data=[]
        )


async def get_alert_history(
    start_time: Optional[str] = Query(None, description="开始时间 (ISO格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO格式)"),
    alert_type: Optional[str] = Query(None, description="告警类型"),
    alert_level: Optional[str] = Query(None, description="告警级别"),
    is_diagnosed: Optional[bool] = Query(None, description="是否已诊断"),
    days: Optional[int] = Query(7, description="最近N天（当start_time未指定时使用）"),
    limit: int = Query(100, description="返回数量限制")
) -> ListResponse:
    """
    获取告警历史数据
    
    @param start_time: 开始时间 (ISO格式)
    @param end_time: 结束时间 (ISO格式)
    @param alert_type: 告警类型过滤
    @param alert_level: 告警级别过滤
    @param is_diagnosed: 是否已诊断过滤
    @param days: 最近N天（当start_time未指定时使用）
    @param limit: 返回数量限制
    @return: 告警历史列表
    """
    try:
        if start_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        else:
            start_dt = datetime.now() - timedelta(days=days)
        
        if end_time:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        else:
            end_dt = datetime.now()
        
        alerts = AlertRepository.get_alerts(
            start_time=start_dt,
            end_time=end_dt,
            alert_type=alert_type,
            alert_level=alert_level,
            is_diagnosed=is_diagnosed,
            limit=limit
        )
        
        return ListResponse(
            code=200,
            msg="Success",
            data=alerts
        )
    except Exception as e:
        return ListResponse(
            code=500,
            msg=f"Error: {str(e)}",
            data=[]
        )


async def get_history_statistics(
    days: int = Query(7, description="统计最近N天的数据")
) -> BaseResponse:
    """
    获取历史统计信息
    
    @param days: 统计最近N天的数据
    @return: 统计信息
    """
    try:
        start_time = datetime.now() - timedelta(days=days)
        end_time = datetime.now()
        
        monitoring_stats = MonitoringRepository.get_statistics(
            start_time=start_time,
            end_time=end_time
        )
        
        alert_stats = AlertRepository.get_statistics(
            start_time=start_time,
            end_time=end_time
        )
        
        active_alerts_count = AlertRepository.get_active_alerts_count()
        
        return BaseResponse(
            code=200,
            msg="Success",
            data={
                "period": {
                    "days": days,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat()
                },
                "monitoring": monitoring_stats,
                "alerts": {
                    **alert_stats,
                    "active_count": active_alerts_count
                },
                "summary": {
                    "total_monitoring_records": monitoring_stats.get('count', 0),
                    "total_alerts": alert_stats.get('total_count', 0),
                    "diagnosis_rate": alert_stats.get('diagnosis_rate', 0),
                    "avg_cpu_usage": f"{monitoring_stats.get('avg_cpu_usage', 0)*100:.1f}%",
                    "max_cpu_usage": f"{monitoring_stats.get('max_cpu_usage', 0)*100:.1f}%",
                    "avg_memory_usage": f"{monitoring_stats.get('avg_memory_usage', 0)*100:.1f}%",
                    "max_memory_usage": f"{monitoring_stats.get('max_memory_usage', 0)*100:.1f}%"
                }
            }
        )
    except Exception as e:
        return BaseResponse(
            code=500,
            msg=f"Error: {str(e)}",
            data=None
        )


async def get_trend_data(
    metric_type: str = Query("cpu", description="指标类型: cpu/memory/disk_io/slow_query"),
    hours: int = Query(24, description="最近N小时")
) -> BaseResponse:
    """
    获取指标趋势数据（用于前端图表）
    
    @param metric_type: 指标类型
    @param hours: 最近N小时
    @return: 趋势数据
    """
    try:
        start_time = datetime.now() - timedelta(hours=hours)
        
        history = MonitoringRepository.get_history(
            start_time=start_time,
            limit=10000
        )
        
        if not history:
            return BaseResponse(
                code=200,
                msg="No data",
                data={"timestamps": [], "values": []}
            )
        
        history.reverse()
        
        timestamps = []
        values = []
        
        metric_mapping = {
            "cpu": "cpu_usage",
            "memory": "memory_usage",
            "disk_io": "disk_io_util",
            "slow_query": "slow_query_count",
            "connections": "active_connections",
            "cache_hit": "cache_hit_ratio"
        }
        
        metric_key = metric_mapping.get(metric_type, "cpu_usage")
        
        for record in history:
            timestamps.append(record.get('timestamp'))
            value = record.get(metric_key, 0)
            if metric_type in ["cpu", "memory", "disk_io", "cache_hit"]:
                values.append(round(value * 100, 2))
            else:
                values.append(value)
        
        return BaseResponse(
            code=200,
            msg="Success",
            data={
                "metric_type": metric_type,
                "timestamps": timestamps,
                "values": values,
                "unit": "%" if metric_type in ["cpu", "memory", "disk_io", "cache_hit"] else ""
            }
        )
    except Exception as e:
        return BaseResponse(
            code=500,
            msg=f"Error: {str(e)}",
            data=None
        )
