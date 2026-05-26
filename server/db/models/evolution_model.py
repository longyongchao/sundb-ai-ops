#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Self-evolution database models.

V0.1 keeps the module as a sidecar to the existing diagnosis flow: cases and
feedback are associated with diagnosis_records but do not change diagnosis
behavior.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from server.db.base import Base


class EvolutionCase(Base):
    """Standardized diagnosis case captured for self-evolution analysis."""

    __tablename__ = "evolution_cases"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="自进化案例ID")
    record_id = Column(Integer, ForeignKey("diagnosis_records.id"), nullable=True, index=True, comment="诊断记录ID")
    diagnosis_id = Column(String(100), nullable=True, index=True, comment="诊断任务ID")
    case_fingerprint = Column(String(128), nullable=False, index=True, comment="案例指纹")
    anomaly_type = Column(String(100), nullable=True, index=True, comment="异常类型")

    input_snapshot = Column(JSON, nullable=True, comment="诊断输入快照")
    trace_snapshot = Column(JSON, nullable=True, comment="诊断推理轨迹快照")
    knowledge_snapshot = Column(JSON, nullable=True, comment="知识检索快照")
    output_snapshot = Column(JSON, nullable=True, comment="诊断输出快照")
    asset_versions = Column(JSON, nullable=True, comment="诊断资产版本快照")

    outcome_score = Column(Float, default=0.0, comment="结果评分")
    label = Column(String(32), default="uncertain_case", index=True, comment="案例标签")
    status = Column(String(32), default="captured", index=True, comment="案例状态")

    create_time = Column(DateTime, default=datetime.now, comment="创建时间")
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    feedback_items = relationship("EvolutionFeedback", back_populates="case", cascade="all, delete-orphan")

    def __repr__(self):
        return (
            f"<EvolutionCase(id={self.id}, record_id={self.record_id}, "
            f"label='{self.label}', score={self.outcome_score})>"
        )

    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "diagnosis_id": self.diagnosis_id,
            "case_fingerprint": self.case_fingerprint,
            "anomaly_type": self.anomaly_type,
            "input_snapshot": self.input_snapshot or {},
            "trace_snapshot": self.trace_snapshot or {},
            "knowledge_snapshot": self.knowledge_snapshot or {},
            "output_snapshot": self.output_snapshot or {},
            "asset_versions": self.asset_versions or {},
            "outcome_score": self.outcome_score or 0.0,
            "label": self.label,
            "status": self.status,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "update_time": self.update_time.isoformat() if self.update_time else None,
        }


class EvolutionFeedback(Base):
    """User or metric feedback associated with an evolution case."""

    __tablename__ = "evolution_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="自进化反馈ID")
    case_id = Column(Integer, ForeignKey("evolution_cases.id"), nullable=True, index=True, comment="自进化案例ID")
    record_id = Column(Integer, ForeignKey("diagnosis_records.id"), nullable=True, index=True, comment="诊断记录ID")
    message_id = Column(String(64), nullable=True, index=True, comment="聊天消息ID")

    feedback_type = Column(String(32), default="user_feedback", index=True, comment="反馈类型")
    score = Column(Float, nullable=True, comment="用户评分，兼容0-100或0-1")
    reason = Column(Text, nullable=True, comment="反馈原因")
    accepted = Column(Boolean, nullable=True, comment="是否采纳")
    metric_recovery = Column(JSON, nullable=True, comment="修复后指标恢复情况")
    recurrence = Column(Boolean, nullable=True, comment="是否复发")
    raw_feedback = Column(JSON, nullable=True, comment="原始反馈内容")

    create_time = Column(DateTime, default=datetime.now, comment="创建时间")

    case = relationship("EvolutionCase", back_populates="feedback_items")

    def __repr__(self):
        return f"<EvolutionFeedback(id={self.id}, case_id={self.case_id}, score={self.score})>"

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "record_id": self.record_id,
            "message_id": self.message_id,
            "feedback_type": self.feedback_type,
            "score": self.score,
            "reason": self.reason,
            "accepted": self.accepted,
            "metric_recovery": self.metric_recovery or {},
            "recurrence": self.recurrence,
            "raw_feedback": self.raw_feedback or {},
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }
