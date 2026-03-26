#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : diagnosis_record_repository.py
@Author  : LI
@Date    : 2026
@Desc    : 诊断记录数据访问层
            Reference: D-Bot Paper - Diagnosis Records CRUD
"""
import json
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy import text
from server.db.session import with_session
from server.db.models.diagnosis_model import DiagnosisRecord
from server.utils import get_beijing_now_str


@with_session
def create_diagnosis_record(
    session,
    anomaly_type: str,
    anomaly_description: str,
    anomaly_severity: str = "medium",
    anomaly_metadata: Dict = None,
    user_id: int = None
) -> Optional[int]:
    """
    创建诊断记录
    
    @param session: 数据库会话
    @param anomaly_type: 异常类型
    @param anomaly_description: 异常描述
    @param anomaly_severity: 严重程度
    @param anomaly_metadata: 异常元数据
    @param user_id: 用户ID
    @return: 诊断记录ID（返回ID而非对象，避免Session关闭后访问问题）
    """
    try:
        from datetime import datetime, timedelta
        
        recent_threshold = datetime.now() - timedelta(seconds=10)
        recent_duplicate = session.query(DiagnosisRecord).filter(
            DiagnosisRecord.anomaly_type == anomaly_type,
            DiagnosisRecord.anomaly_description == anomaly_description,
            DiagnosisRecord.create_time >= recent_threshold,
            DiagnosisRecord.status.in_(["running", "completed"])
        ).first()
        
        if recent_duplicate:
            print(f"[WARN] 检测到重复诊断请求，跳过创建（ID: {recent_duplicate.id}）")
            return None
        
        record = DiagnosisRecord(
            user_id=user_id,
            anomaly_type=anomaly_type,
            anomaly_description=anomaly_description,
            anomaly_severity=anomaly_severity,
            anomaly_metadata=anomaly_metadata or {},
            status="running",
            create_time=datetime.now()
        )
        session.add(record)
        session.flush()
        record_id = record.id
        session.commit()
        return record_id
    except Exception as e:
        print(f"[ERROR] 创建诊断记录失败: {e}")
        session.rollback()
        return None


@with_session
def update_diagnosis_record(
    session,
    record_id: int,
    tree_search_trace: str = None,
    reasoning_steps_count: int = None,
    max_search_depth: int = None,
    pruned_nodes_count: int = None,
    reflection_count: int = None,
    root_causes: List[Dict] = None,
    solutions: List[Dict] = None,
    confidence: float = None,
    deepseek_tokens_input: int = None,
    deepseek_tokens_output: int = None,
    deepseek_tokens_total: int = None,
    diagnosis_time: float = None,
    status: str = None,
    error_message: str = None,
    knowledge_chunks_used: int = None,
    tools_called: List[str] = None
) -> Optional[DiagnosisRecord]:
    """
    更新诊断记录
    
    @param session: 数据库会话
    @param record_id: 记录ID
    @param tree_search_trace: 树搜索Trace
    @param reasoning_steps_count: 推理步骤数
    @param max_search_depth: 最大搜索深度
    @param pruned_nodes_count: 剪枝节点数
    @param reflection_count: 反思次数
    @param root_causes: 根因列表
    @param solutions: 解决方案列表
    @param confidence: 置信度
    @param deepseek_tokens_input: 输入Token数
    @param deepseek_tokens_output: 输出Token数
    @param deepseek_tokens_total: 总Token数
    @param diagnosis_time: 诊断耗时
    @param status: 状态
    @param error_message: 错误信息
    @param knowledge_chunks_used: 使用的知识块数
    @param tools_called: 调用的工具列表
    @return: 更新后的DiagnosisRecord对象
    """
    record = session.query(DiagnosisRecord).filter_by(id=record_id).first()
    if not record:
        return None
    
    if tree_search_trace is not None:
        record.tree_search_trace = tree_search_trace
    if reasoning_steps_count is not None:
        record.reasoning_steps_count = reasoning_steps_count
    if max_search_depth is not None:
        record.max_search_depth = max_search_depth
    if pruned_nodes_count is not None:
        record.pruned_nodes_count = pruned_nodes_count
    if reflection_count is not None:
        record.reflection_count = reflection_count
    if root_causes is not None:
        record.root_causes = json.dumps(root_causes, ensure_ascii=False)
    if solutions is not None:
        record.solutions = json.dumps(solutions, ensure_ascii=False)
    if confidence is not None:
        record.confidence = confidence
    if deepseek_tokens_input is not None:
        record.deepseek_tokens_input = deepseek_tokens_input
    if deepseek_tokens_output is not None:
        record.deepseek_tokens_output = deepseek_tokens_output
    if deepseek_tokens_total is not None:
        record.deepseek_tokens_total = deepseek_tokens_total
    if diagnosis_time is not None:
        record.diagnosis_time = diagnosis_time
    if status is not None:
        record.status = status
    if error_message is not None:
        record.error_message = error_message
    if knowledge_chunks_used is not None:
        record.knowledge_chunks_used = knowledge_chunks_used
    if tools_called is not None:
        record.tools_called = json.dumps(tools_called, ensure_ascii=False)
    
    record.update_time = datetime.now()
    session.add(record)
    return record


@with_session
def get_diagnosis_record_by_id(session, record_id: int) -> Optional[Dict]:
    """
    根据ID获取诊断记录
    
    @param session: 数据库会话
    @param record_id: 记录ID
    @return: 诊断记录字典（返回字典而非对象，避免Session关闭后访问问题）
    """
    record = session.query(DiagnosisRecord).filter_by(id=record_id).first()
    return record.to_dict() if record else None


@with_session
def list_diagnosis_records(
    session,
    user_id: int = None,
    anomaly_type: str = None,
    status: str = None,
    limit: int = 20,
    offset: int = 0
) -> List[Dict]:
    """
    查询诊断记录列表
    
    @param session: 数据库会话
    @param user_id: 用户ID
    @param anomaly_type: 异常类型
    @param status: 状态
    @param limit: 返回数量限制
    @param offset: 偏移量
    @return: 诊断记录字典列表（返回字典而非对象，避免Session关闭后访问问题）
    """
    query = session.query(DiagnosisRecord)
    
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    if anomaly_type:
        query = query.filter_by(anomaly_type=anomaly_type)
    if status:
        query = query.filter_by(status=status)
    
    records = query.order_by(DiagnosisRecord.create_time.desc()).offset(offset).limit(limit).all()
    return [record.to_dict() for record in records]


@with_session
def count_diagnosis_records(
    session,
    user_id: int = None,
    anomaly_type: str = None,
    status: str = None
) -> int:
    """
    统计诊断记录数量
    
    @param session: 数据库会话
    @param user_id: 用户ID
    @param anomaly_type: 异常类型
    @param status: 状态
    @return: 记录数量
    """
    query = session.query(DiagnosisRecord)
    
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    if anomaly_type:
        query = query.filter_by(anomaly_type=anomaly_type)
    if status:
        query = query.filter_by(status=status)
    
    return query.count()


@with_session
def delete_diagnosis_record(session, record_id: int) -> bool:
    """
    删除诊断记录
    
    @param session: 数据库会话
    @param record_id: 记录ID
    @return: 是否成功
    """
    record = session.query(DiagnosisRecord).filter_by(id=record_id).first()
    if record:
        session.delete(record)
        return True
    return False


@with_session
def get_diagnosis_statistics(session, user_id: int = None) -> Dict:
    """
    获取诊断统计数据
    
    @param session: 数据库会话
    @param user_id: 用户ID
    @return: 统计数据字典
    """
    query = session.query(DiagnosisRecord)
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    
    records = query.all()
    
    total_count = len(records)
    completed_count = sum(1 for r in records if r.status == "completed")
    failed_count = sum(1 for r in records if r.status == "failed")
    
    total_tokens = sum(r.deepseek_tokens_total or 0 for r in records)
    total_time = sum(r.diagnosis_time or 0 for r in records)
    avg_confidence = sum(r.confidence or 0 for r in records) / total_count if total_count > 0 else 0
    
    anomaly_type_counts = {}
    for r in records:
        anomaly_type_counts[r.anomaly_type] = anomaly_type_counts.get(r.anomaly_type, 0) + 1
    
    return {
        "total_count": total_count,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "success_rate": round(completed_count / total_count * 100, 2) if total_count > 0 else 0,
        "total_tokens": total_tokens,
        "total_diagnosis_time": round(total_time, 2),
        "avg_confidence": round(avg_confidence, 3),
        "anomaly_type_distribution": anomaly_type_counts
    }
