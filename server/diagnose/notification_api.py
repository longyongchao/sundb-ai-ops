#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : notification_api.py
@Author  : LI
@Date    : 2026
@Desc    : 通知 API
            提供通知的查询、标记已读等功能
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import Body, Query
from pydantic import BaseModel

from server.utils import BaseResponse, ListResponse
from server.db.session import session_scope
from server.db.models.diagnosis_model import Notification

logger = logging.getLogger(__name__)


async def get_unread_notifications(
    limit: int = Query(20, description="返回数量限制")
) -> ListResponse:
    """
    获取未读通知列表
    
    @param limit: 返回数量限制
    @return: 未读通知列表
    """
    try:
        with session_scope() as sess:
            notifications = sess.query(Notification).filter(
                Notification.is_read == False
            ).order_by(
                Notification.created_at.desc()
            ).limit(limit).all()
            
            return ListResponse(
                code=200,
                msg="Success",
                data=[n.to_dict() for n in notifications]
            )
    except Exception as e:
        logger.error(f"获取未读通知失败: {e}")
        return ListResponse(code=500, msg=f"Error: {str(e)}", data=[])


async def get_all_notifications(
    limit: int = Query(50, description="返回数量限制"),
    notification_type: Optional[str] = Query(None, description="通知类型过滤")
) -> ListResponse:
    """
    获取所有通知列表
    
    @param limit: 返回数量限制
    @param notification_type: 通知类型过滤
    @return: 通知列表
    """
    try:
        with session_scope() as sess:
            query = sess.query(Notification)
            
            if notification_type:
                query = query.filter(Notification.notification_type == notification_type)
            
            notifications = query.order_by(
                Notification.created_at.desc()
            ).limit(limit).all()
            
            return ListResponse(
                code=200,
                msg="Success",
                data=[n.to_dict() for n in notifications]
            )
    except Exception as e:
        logger.error(f"获取通知列表失败: {e}")
        return ListResponse(code=500, msg=f"Error: {str(e)}", data=[])


async def mark_notification_read(
    notification_id: int = Body(..., embed=True)
) -> BaseResponse:
    """
    标记单条通知为已读
    
    @param notification_id: 通知ID
    @return: 操作结果
    """
    try:
        with session_scope() as sess:
            notification = sess.query(Notification).filter(
                Notification.id == notification_id
            ).first()
            
            if notification:
                notification.is_read = True
                notification.read_at = datetime.now()
                sess.commit()
                return BaseResponse(code=200, msg="标记成功", data=notification.to_dict())
            else:
                return BaseResponse(code=404, msg="通知不存在", data=None)
    except Exception as e:
        logger.error(f"标记通知已读失败: {e}")
        return BaseResponse(code=500, msg=f"Error: {str(e)}", data=None)


async def mark_all_read() -> BaseResponse:
    """
    标记所有通知为已读
    
    @return: 操作结果
    """
    try:
        with session_scope() as sess:
            sess.query(Notification).filter(
                Notification.is_read == False
            ).update({
                "is_read": True,
                "read_at": datetime.now()
            })
            sess.commit()
            return BaseResponse(code=200, msg="全部标记已读", data=None)
    except Exception as e:
        logger.error(f"标记全部已读失败: {e}")
        return BaseResponse(code=500, msg=f"Error: {str(e)}", data=None)


async def get_unread_count() -> BaseResponse:
    """
    获取未读通知数量
    
    @return: 未读数量
    """
    try:
        with session_scope() as sess:
            count = sess.query(Notification).filter(
                Notification.is_read == False
            ).count()
            
            return BaseResponse(code=200, msg="Success", data={"count": count})
    except Exception as e:
        logger.error(f"获取未读数量失败: {e}")
        return BaseResponse(code=500, msg=f"Error: {str(e)}", data={"count": 0})


def create_notification(
    notification_type: str,
    title: str = None,
    content: str = None,
    severity: str = "info",
    related_id: int = None,
    related_type: str = None,
    action_url: str = None,
    action_text: str = None,
    extra_data: dict = None
) -> Optional[int]:
    """
    创建通知（供其他模块调用）
    
    @param notification_type: 通知类型
    @param title: 通知标题
    @param content: 通知内容
    @param severity: 严重程度
    @param related_id: 关联ID
    @param related_type: 关联类型
    @param action_url: 跳转URL
    @param action_text: 操作文字
    @param extra_data: 额外数据
    @return: 通知ID
    """
    if not title:
        title = f"{notification_type}通知"
    
    try:
        with session_scope() as sess:
            notification = Notification(
                notification_type=notification_type,
                title=title,
                content=content,
                severity=severity,
                related_id=related_id,
                related_type=related_type,
                action_url=action_url,
                action_text=action_text,
                extra_data=extra_data
            )
            sess.add(notification)
            sess.commit()
            logger.info(f"创建通知成功: {title}")
            return notification.id
    except Exception as e:
        logger.error(f"创建通知失败: {e}")
        return None


def create_diagnosis_notification(
    report_id: int,
    anomaly_type: str,
    confidence: float = 0.0
) -> Optional[int]:
    """
    创建诊断完成通知（供诊断模块调用）
    
    @param report_id: 诊断报告ID
    @param anomaly_type: 异常类型
    @param confidence: 置信度
    @return: 通知ID
    """
    return create_notification(
        notification_type="diagnosis",
        title=f"诊断完成：{anomaly_type}",
        content=f"系统自动完成诊断分析，置信度：{confidence*100:.1f}%",
        severity="info" if confidence > 0.7 else "warning",
        related_id=report_id,
        related_type="diagnosis_report",
        action_url=f"/reports?id={report_id}",
        action_text="查看报告",
        extra_data={
            "anomaly_type": anomaly_type,
            "confidence": confidence
        }
    )


def create_alert_notification(
    alert_type: str,
    alert_message: str,
    severity: str = "warning"
) -> Optional[int]:
    """
    创建告警通知（供异常检测模块调用）
    
    @param alert_type: 告警类型
    @param alert_message: 告警信息
    @param severity: 严重程度
    @return: 通知ID
    """
    return create_notification(
        notification_type="alert",
        title=f"系统告警：{alert_type}",
        content=alert_message,
        severity=severity,
        action_url="/monitoring",
        action_text="查看详情",
        extra_data={
            "alert_type": alert_type
        }
    )
