#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : diagnosis_report_repository.py
@Author  : LI
@Date    : 2026
@Desc    : 诊断报告数据访问层
            Reference: D-Bot Paper - Diagnosis Reports CRUD
"""
import json
from typing import Dict, List, Optional
from datetime import datetime
from server.db.session import with_session
from server.db.models.diagnosis_model import DiagnosisReport, DiagnosisRecord


@with_session
def create_diagnosis_report(
    session,
    record_id: int,
    report_content: str,
    report_title: str = None,
    report_summary: str = None,
    report_format: str = "markdown",
    root_cause_summary: str = None,
    solution_summary: str = None,
    risk_assessment: str = None
) -> DiagnosisReport:
    """
    创建诊断报告
    
    @param session: 数据库会话
    @param record_id: 关联的诊断记录ID
    @param report_content: 完整报告内容
    @param report_title: 报告标题
    @param report_summary: 报告摘要
    @param report_format: 报告格式
    @param root_cause_summary: 根因摘要
    @param solution_summary: 解决方案摘要
    @param risk_assessment: 风险评估
    @return: DiagnosisReport对象
    """
    report = DiagnosisReport(
        record_id=record_id,
        report_title=report_title or f"诊断报告 #{record_id}",
        report_content=report_content,
        report_summary=report_summary,
        report_format=report_format,
        root_cause_summary=root_cause_summary,
        solution_summary=solution_summary,
        risk_assessment=risk_assessment,
        create_time=datetime.now()
    )
    session.add(report)
    session.flush()
    return report


@with_session
def update_diagnosis_report(
    session,
    report_id: int,
    report_content: str = None,
    report_title: str = None,
    report_summary: str = None,
    root_cause_summary: str = None,
    solution_summary: str = None,
    risk_assessment: str = None,
    is_exported: bool = None,
    export_format: str = None
) -> Optional[DiagnosisReport]:
    """
    更新诊断报告
    
    @param session: 数据库会话
    @param report_id: 报告ID
    @param report_content: 报告内容
    @param report_title: 报告标题
    @param report_summary: 报告摘要
    @param root_cause_summary: 根因摘要
    @param solution_summary: 解决方案摘要
    @param risk_assessment: 风险评估
    @param is_exported: 是否已导出
    @param export_format: 导出格式
    @return: 更新后的DiagnosisReport对象
    """
    report = session.query(DiagnosisReport).filter_by(id=report_id).first()
    if not report:
        return None
    
    if report_content is not None:
        report.report_content = report_content
    if report_title is not None:
        report.report_title = report_title
    if report_summary is not None:
        report.report_summary = report_summary
    if root_cause_summary is not None:
        report.root_cause_summary = root_cause_summary
    if solution_summary is not None:
        report.solution_summary = solution_summary
    if risk_assessment is not None:
        report.risk_assessment = risk_assessment
    if is_exported is not None:
        report.is_exported = is_exported
        if is_exported:
            report.export_time = datetime.now()
    if export_format is not None:
        report.export_format = export_format
    
    report.update_time = datetime.now()
    session.add(report)
    return report


@with_session
def get_report_by_id(session, report_id: int) -> Optional[DiagnosisReport]:
    """
    根据ID获取诊断报告
    
    @param session: 数据库会话
    @param report_id: 报告ID
    @return: DiagnosisReport对象
    """
    return session.query(DiagnosisReport).filter_by(id=report_id).first()


@with_session
def get_report_by_record_id(session, record_id: int) -> Optional[Dict]:
    """
    根据诊断记录ID获取报告
    
    @param session: 数据库会话
    @param record_id: 诊断记录ID
    @return: 报告字典（返回字典而非对象，避免Session关闭后访问问题）
    """
    report = session.query(DiagnosisReport).filter_by(record_id=record_id).first()
    return report.to_dict() if report else None


@with_session
def list_diagnosis_reports(
    session,
    is_exported: bool = None,
    risk_assessment: str = None,
    limit: int = 20,
    offset: int = 0
) -> List[DiagnosisReport]:
    """
    查询诊断报告列表
    
    @param session: 数据库会话
    @param is_exported: 是否已导出
    @param risk_assessment: 风险评估
    @param limit: 返回数量限制
    @param offset: 偏移量
    @return: DiagnosisReport列表
    """
    query = session.query(DiagnosisReport)
    
    if is_exported is not None:
        query = query.filter_by(is_exported=is_exported)
    if risk_assessment:
        query = query.filter_by(risk_assessment=risk_assessment)
    
    reports = query.order_by(DiagnosisReport.create_time.desc()).offset(offset).limit(limit).all()
    return reports


@with_session
def delete_diagnosis_report_by_record_id(session, record_id: int) -> bool:
    """
    删除诊断报告（同时删除关联的诊断记录）
    
    @param session: 数据库会话
    @param record_id: 诊断记录ID（主表ID）
    @return: 是否成功
    """
    try:
        # 先删除从表的报告记录
        report = session.query(DiagnosisReport).filter_by(record_id=record_id).first()
        if report:
            session.delete(report)
            print(f"[DB] 已删除诊断报告，record_id: {record_id}")
        
        # 再删除主表的诊断记录
        record = session.query(DiagnosisRecord).filter_by(id=record_id).first()
        if record:
            session.delete(record)
            print(f"[DB] 已删除诊断记录，id: {record_id}")
        
        session.commit()
        return True
    except Exception as e:
        print(f"[DB] 删除诊断记录失败: {e}")
        session.rollback()
        return False


@with_session
def get_report_with_record(session, report_id: int) -> Dict:
    """
    获取报告及其关联的诊断记录
    
    @param session: 数据库会话
    @param report_id: 报告ID
    @return: 包含报告和记录信息的字典
    """
    report = session.query(DiagnosisReport).filter_by(id=report_id).first()
    if not report:
        return None
    
    record = session.query(DiagnosisRecord).filter_by(id=report.record_id).first()
    
    return {
        "report": report.to_dict(),
        "record": record.to_dict() if record else None
    }


@with_session
def generate_report_from_record(session, record_id: int) -> Optional[int]:
    """
    根据诊断记录自动生成报告
    
    @param session: 数据库会话
    @param record_id: 诊断记录ID
    @return: 生成的报告ID（返回ID而非对象，避免Session关闭后访问问题）
    """
    try:
        record = session.query(DiagnosisRecord).filter_by(id=record_id).first()
        if not record:
            return None
        
        existing_report = session.query(DiagnosisReport).filter_by(record_id=record_id).first()
        if existing_report:
            return existing_report.id
        
        root_causes = json.loads(record.root_causes) if record.root_causes else []
        solutions = json.loads(record.solutions) if record.solutions else []
        
        real_anomaly_type = record.anomaly_type
        if root_causes:
            cause_types = list({rc.get("type", "") for rc in root_causes if rc.get("type") and rc.get("type") != "unknown"})
            if cause_types:
                real_anomaly_type = ", ".join(cause_types)
        
        root_cause_summary = "、".join([rc.get("type", "未知") for rc in root_causes[:3]]) if root_causes else "未确定"
        solution_summary = "、".join([s.get("action", "无") for s in solutions[:3]]) if solutions else "无"
        
        report_content = _generate_markdown_report(record, root_causes, solutions, real_anomaly_type)
        
        risk_assessment = "high" if record.anomaly_severity in ["high", "critical"] else "medium" if record.anomaly_severity == "medium" else "low"
        
        report = DiagnosisReport(
            record_id=record_id,
            report_title=f"诊断报告 - {real_anomaly_type}",
            report_content=report_content,
            report_summary=f"本次诊断针对{real_anomaly_type}异常，置信度{record.confidence:.2%}，耗时{record.diagnosis_time:.2f}秒。",
            report_format="markdown",
            root_cause_summary=root_cause_summary,
            solution_summary=solution_summary,
            risk_assessment=risk_assessment,
            create_time=datetime.now()
        )
        session.add(report)
        session.flush()
        report_id = report.id
        session.commit()
        return report_id
    except Exception as e:
        print(f"[ERROR] 生成诊断报告失败: {e}")
        session.rollback()
        return None


def _generate_markdown_report(record: DiagnosisRecord, root_causes: List[Dict], solutions: List[Dict], real_anomaly_type: str = None) -> str:
    """
    生成Markdown格式的报告内容
    
    @param record: 诊断记录
    @param root_causes: 根因列表
    @param solutions: 解决方案列表
    @param real_anomaly_type: 真实异常类型（优先从root_causes提取）
    @return: Markdown格式报告
    """
    display_anomaly_type = real_anomaly_type or record.anomaly_type or "数据库性能异常"
    
    user_problem = record.anomaly_description or ""
    report_title = f"数据库性能诊断报告 - {user_problem[:20]}..." if user_problem and len(user_problem) > 20 else f"数据库性能诊断报告 - {user_problem}" if user_problem else "数据库性能诊断报告"
    
    report_lines = [
        f"# {report_title}",
        "",
        f"**异常类型**: {display_anomaly_type}",
        f"**诊断时间**: {record.create_time.strftime('%Y-%m-%d %H:%M:%S') if record.create_time else 'N/A'}",
        f"**诊断耗时**: {record.diagnosis_time:.2f}秒",
        f"**置信度**: {record.confidence:.2%}",
        f"**状态**: {record.status}",
        f"**使用模型**: DeepSeek",
        "",
        "## 异常描述",
        "",
        f"- **异常类型**: {display_anomaly_type}",
        f"- **严重程度**: {record.anomaly_severity}",
        f"- **详细描述**: {record.anomaly_description or '用户未提供详细描述'}",
        "",
        "## 诊断过程",
        "",
        f"- **推理步骤数**: {record.reasoning_steps_count}",
        f"- **搜索深度**: {record.max_search_depth}",
        f"- **剪枝节点数**: {record.pruned_nodes_count}",
        f"- **反思次数**: {record.reflection_count}",
        f"- **使用知识块数**: {record.knowledge_chunks_used}",
        "",
        "## 根因分析",
        ""
    ]
    
    filtered_causes = []
    has_business_cause = False
    
    if root_causes:
        for i, rc in enumerate(root_causes, 1):
            cause_type = rc.get('type', '未知')
            description = rc.get('description', '无描述')
            confidence = rc.get('confidence', 0)
            evidence = rc.get('evidence', '')
            
            is_system_sql = False
            if cause_type == "Slow Queries" or "慢查询" in cause_type:
                if "pg_database_size" in str(evidence) or "pg_stat" in str(evidence):
                    is_system_sql = True
            
            if is_system_sql:
                filtered_causes.append({
                    "index": i,
                    "type": "系统SQL慢查询（与业务问题无关）",
                    "description": f"检测到pg_database_size等系统SQL慢查询，非用户反馈的业务SQL",
                    "confidence": f"{confidence:.2%}",
                    "impact": rc.get('impact', '对业务影响较小')
                })
            else:
                has_business_cause = True
                filtered_causes.append({
                    "index": i,
                    "type": cause_type,
                    "description": description,
                    "confidence": f"{confidence:.2%}",
                    "impact": rc.get('impact', '未知')
                })
    
    if not has_business_cause:
        filtered_causes.insert(0, {
            "index": 0,
            "type": "暂未定位到业务根因",
            "description": f"当前数据库未捕获到与「{user_problem[:30] if user_problem else '用户描述'}」相关的业务SQL，建议验证数据库连接",
            "confidence": "N/A",
            "impact": "需要进一步排查"
        })
    
    for cause in filtered_causes:
        report_lines.extend([
            f"### 根因 {cause['index'] if cause['index'] > 0 else '#'}: {cause['type']}",
            "",
            f"- **描述**: {cause['description']}",
            f"- **置信度**: {cause['confidence']}",
            f"- **影响**: {cause['impact']}",
            ""
        ])
    
    report_lines.extend([
        "## 证据详情",
        ""
    ])
    
    if record.tree_search_trace:
        try:
            steps = json.loads(record.tree_search_trace) if isinstance(record.tree_search_trace, str) else record.tree_search_trace
            for i, step in enumerate(steps[:10], 1):
                action = step.get('action', '未知工具')
                observation = step.get('observation', '')
                if observation:
                    evidence_text = observation[:100] + "..." if len(observation) > 100 else observation
                    report_lines.extend([
                        f"### 步骤 {i}: {action}",
                        "",
                        f"```\n{evidence_text}\n```",
                        ""
                    ])
        except:
            pass
    
    report_lines.extend([
        "## 数据矛盾提醒",
        "",
        "未检测到明显数据矛盾",
        "",
        "## 修复建议",
        ""
    ])
    
    if solutions:
        for i, sol in enumerate(solutions, 1):
            report_lines.extend([
                f"### 方案 {i}: {sol.get('action', '建议操作')}",
                "",
                f"- **说明**: {sol.get('explanation', '无详细说明')}",
                f"- **SQL**: `{sol.get('sql', 'N/A')}`" if sol.get('sql') else "",
                ""
            ])
    else:
        report_lines.extend([
            "1. **验证数据库连接**: 确认连接的是业务库而非测试库，且有权限读取pg_stat_statements扩展",
            "2. **重新执行诊断**: 连接正确数据库后，触发相应异常场景再诊断",
            "3. **检查慢查询类型**: 过滤系统SQL，聚焦业务相关查询",
            ""
        ])
    
    report_lines.extend([
        "## 诊断步骤",
        ""
    ])
    
    if record.tree_search_trace:
        try:
            steps = json.loads(record.tree_search_trace) if isinstance(record.tree_search_trace, str) else record.tree_search_trace
            for i, step in enumerate(steps[:10], 1):
                action = step.get('action', '未知')
                thought = step.get('thought', '')
                report_lines.append(f"{i}. 调用 **{action}** → {thought[:50] if thought else '执行诊断'}")
        except:
            report_lines.append("诊断步骤记录不可用")
    
    report_lines.extend([
        "",
        "---",
        f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
    ])
    
    return "\n".join(report_lines)
