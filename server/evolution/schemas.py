#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pydantic schemas shared by self-evolution APIs and collectors."""
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EvolutionFeedbackInput(BaseModel):
    record_id: Optional[int] = Field(default=None, description="诊断记录ID")
    case_id: Optional[int] = Field(default=None, description="自进化案例ID")
    evolution_case_id: Optional[int] = Field(default=None, description="自进化案例ID，兼容前端命名")
    message_id: Optional[str] = Field(default=None, description="聊天消息ID")
    feedback_type: str = Field(default="user_feedback", description="反馈类型")
    score: Optional[float] = Field(default=None, description="评分，支持0-100或0-1")
    reason: str = Field(default="", description="反馈原因")
    accepted: Optional[bool] = Field(default=None, description="诊断建议是否被采纳")
    metric_recovery: Optional[Dict[str, Any]] = Field(default=None, description="修复后指标恢复情况")
    recurrence: Optional[bool] = Field(default=None, description="同类问题是否复发")
    raw_feedback: Dict[str, Any] = Field(default_factory=dict, description="原始反馈")
