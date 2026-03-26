#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : analytics.py
@Author  : LI
@Date    : 2026
@Desc    : 统一埋点封装层（门面模式 Facade Pattern）
            解决 SDK 版本兼容性并提供容错处理
            无论底层的监控服务怎么变，业务代码只管调这个"安全接口"

架构优势（论文加分点）：
1. 防御性编程：即使监控服务挂了，核心诊断逻辑依然能跑通
2. 版本隔离：切换监控服务只需改这一个文件
3. 统一格式化：可统一添加 timestamp、environment 等公共信息
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_analytics_initialized = False
_analytics_disabled = False


def init_analytics(api_key: str = None, host: str = None, disabled: bool = False):
    """
    统一初始化接口
    
    @param api_key: 监控服务 API Key
    @param host: 监控服务 Host
    @param disabled: 是否禁用监控（开发环境可设为 True）
    """
    global _analytics_initialized, _analytics_disabled
    
    _analytics_disabled = disabled
    
    if disabled:
        logger.info("[Analytics] 监控已禁用（开发模式）")
        _analytics_initialized = True
        return
    
    try:
        import posthog
        if api_key:
            posthog.api_key = api_key
        if host:
            posthog.host = host
        _analytics_initialized = True
        logger.info("[Analytics] 监控服务初始化成功")
    except ImportError:
        logger.warning("[Analytics] posthog 未安装，监控功能将静默跳过")
        _analytics_disabled = True
        _analytics_initialized = True
    except Exception as e:
        logger.error(f"[Analytics] 初始化失败: {e}")
        _analytics_disabled = True
        _analytics_initialized = True


def safe_capture(
    distinct_id: str,
    event: str,
    properties: Dict[str, Any] = None
) -> bool:
    """
    统一埋点封装层：解决 SDK 版本兼容性并提供容错处理
    
    核心修复：强制使用关键字传参，屏蔽底层参数个数限制报错
    
    @param distinct_id: 用户/会话唯一标识
    @param event: 事件名称
    @param properties: 事件属性字典
    @return: 是否成功发送
    """
    if _analytics_disabled:
        return False
    
    if not _analytics_initialized:
        init_analytics()
    
    try:
        import posthog
        
        enriched_properties = {
            **(properties or {}),
            "timestamp": datetime.now().isoformat(),
            "environment": "production"
        }
        
        posthog.capture(
            distinct_id=str(distinct_id),
            event=event,
            properties=enriched_properties
        )
        return True
        
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"[Analytics] Capture failed for event '{event}': {str(e)}")
    
    return False


def capture_diagnostic_event(
    task_id: str,
    anomaly_type: str,
    severity: str,
    root_cause: str = None,
    duration_ms: float = None,
    success: bool = True
) -> bool:
    """
    诊断事件专用埋点
    
    @param task_id: 诊断任务 ID
    @param anomaly_type: 异常类型
    @param severity: 严重程度
    @param root_cause: 根因类型
    @param duration_ms: 诊断耗时（毫秒）
    @param success: 是否成功
    @return: 是否成功发送
    """
    return safe_capture(
        distinct_id=task_id,
        event="diagnostic_triggered",
        properties={
            "anomaly_type": anomaly_type,
            "severity": severity,
            "root_cause": root_cause,
            "duration_ms": duration_ms,
            "success": success
        }
    )


def capture_error_event(
    error_type: str,
    error_message: str,
    context: Dict[str, Any] = None
) -> bool:
    """
    错误事件专用埋点
    
    @param error_type: 错误类型
    @param error_message: 错误信息
    @param context: 上下文信息
    @return: 是否成功发送
    """
    return safe_capture(
        distinct_id="system",
        event="error_occurred",
        properties={
            "error_type": error_type,
            "error_message": error_message[:500],
            "context": context
        }
    )


def capture_performance_metric(
    metric_name: str,
    metric_value: float,
    unit: str = None,
    tags: Dict[str, str] = None
) -> bool:
    """
    性能指标专用埋点
    
    @param metric_name: 指标名称
    @param metric_value: 指标值
    @param unit: 单位
    @param tags: 标签
    @return: 是否成功发送
    """
    return safe_capture(
        distinct_id="system",
        event="performance_metric",
        properties={
            "metric_name": metric_name,
            "metric_value": metric_value,
            "unit": unit,
            "tags": tags
        }
    )


def shutdown():
    """
    关闭监控服务（程序退出时调用）
    """
    try:
        import posthog
        posthog.flush()
        logger.info("[Analytics] 监控服务已关闭")
    except Exception as e:
        logger.debug(f"[Analytics] 关闭时出错: {e}")
