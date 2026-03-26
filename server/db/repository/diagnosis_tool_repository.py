#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : diagnosis_tool_repository.py
@Author  : LI
@Date    : 2026
@Desc    : 诊断工具数据访问层
            Reference: D-Bot Paper Section 5 - Tool Matching
"""
import json
from typing import Dict, List, Optional
from datetime import datetime
from server.db.session import with_session
from server.db.models.diagnosis_model import DiagnosisTool


@with_session
def create_diagnosis_tool(
    session,
    tool_name: str,
    tool_display_name: str = None,
    tool_description: str = None,
    tool_category: str = "diagnostic",
    input_schema: Dict = None,
    output_schema: Dict = None,
    example_usage: Dict = None,
    related_metrics: List[str] = None,
    related_experts: List[str] = None,
    execution_sql: str = None,
    execution_function: str = None,
    priority: int = 0
) -> DiagnosisTool:
    """
    创建诊断工具
    
    @param session: 数据库会话
    @param tool_name: 工具名称
    @param tool_display_name: 显示名称
    @param tool_description: 功能描述
    @param tool_category: 工具类别
    @param input_schema: 输入参数Schema
    @param output_schema: 输出结果Schema
    @param example_usage: 使用示例
    @param related_metrics: 相关指标
    @param related_experts: 关联专家
    @param execution_sql: 执行SQL
    @param execution_function: 执行函数名
    @param priority: 优先级
    @return: DiagnosisTool对象
    """
    tool = DiagnosisTool(
        tool_name=tool_name,
        tool_display_name=tool_display_name or tool_name,
        tool_description=tool_description,
        tool_category=tool_category,
        input_schema=json.dumps(input_schema, ensure_ascii=False) if input_schema else None,
        output_schema=json.dumps(output_schema, ensure_ascii=False) if output_schema else None,
        example_usage=json.dumps(example_usage, ensure_ascii=False) if example_usage else None,
        related_metrics=json.dumps(related_metrics, ensure_ascii=False) if related_metrics else None,
        related_experts=json.dumps(related_experts, ensure_ascii=False) if related_experts else None,
        execution_sql=execution_sql,
        execution_function=execution_function,
        priority=priority,
        create_time=datetime.now()
    )
    session.add(tool)
    session.flush()
    return tool


@with_session
def get_tool_by_id(session, tool_id: int) -> Optional[DiagnosisTool]:
    """
    根据ID获取诊断工具
    
    @param session: 数据库会话
    @param tool_id: 工具ID
    @return: DiagnosisTool对象
    """
    return session.query(DiagnosisTool).filter_by(id=tool_id).first()


@with_session
def get_tool_by_name(session, tool_name: str) -> Optional[DiagnosisTool]:
    """
    根据名称获取诊断工具
    
    @param session: 数据库会话
    @param tool_name: 工具名称
    @return: DiagnosisTool对象
    """
    return session.query(DiagnosisTool).filter_by(tool_name=tool_name).first()


@with_session
def list_diagnosis_tools(
    session,
    tool_category: str = None,
    is_active: bool = True,
    limit: int = 50,
    offset: int = 0
) -> List[DiagnosisTool]:
    """
    查询诊断工具列表
    
    @param session: 数据库会话
    @param tool_category: 工具类别
    @param is_active: 是否启用
    @param limit: 返回数量限制
    @param offset: 偏移量
    @return: DiagnosisTool列表
    """
    query = session.query(DiagnosisTool)
    
    if tool_category:
        query = query.filter_by(tool_category=tool_category)
    if is_active is not None:
        query = query.filter_by(is_active=is_active)
    
    tools = query.order_by(DiagnosisTool.priority.desc()).offset(offset).limit(limit).all()
    return tools


@with_session
def update_diagnosis_tool(
    session,
    tool_id: int,
    **kwargs
) -> Optional[DiagnosisTool]:
    """
    更新诊断工具
    
    @param session: 数据库会话
    @param tool_id: 工具ID
    @param kwargs: 更新字段
    @return: 更新后的DiagnosisTool对象
    """
    tool = session.query(DiagnosisTool).filter_by(id=tool_id).first()
    if not tool:
        return None
    
    json_fields = ['input_schema', 'output_schema', 'example_usage', 'related_metrics', 'related_experts']
    
    for key, value in kwargs.items():
        if hasattr(tool, key):
            if key in json_fields and isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            setattr(tool, key, value)
    
    tool.update_time = datetime.now()
    session.add(tool)
    return tool


@with_session
def delete_diagnosis_tool(session, tool_id: int) -> bool:
    """
    删除诊断工具
    
    @param session: 数据库会话
    @param tool_id: 工具ID
    @return: 是否成功
    """
    tool = session.query(DiagnosisTool).filter_by(id=tool_id).first()
    if tool:
        session.delete(tool)
        return True
    return False


@with_session
def get_tools_by_expert(session, expert_type: str) -> List[DiagnosisTool]:
    """
    获取专家关联的工具
    
    @param session: 数据库会话
    @param expert_type: 专家类型
    @return: DiagnosisTool列表
    """
    tools = session.query(DiagnosisTool).filter_by(is_active=True).all()
    
    matched_tools = []
    for tool in tools:
        related_experts = json.loads(tool.related_experts) if tool.related_experts else []
        if expert_type in related_experts:
            matched_tools.append(tool)
    
    return matched_tools


@with_session
def get_tools_by_metrics(session, metrics: List[str]) -> List[DiagnosisTool]:
    """
    根据指标获取相关工具
    
    @param session: 数据库会话
    @param metrics: 指标列表
    @return: DiagnosisTool列表
    """
    tools = session.query(DiagnosisTool).filter_by(is_active=True).all()
    
    matched_tools = []
    for tool in tools:
        related_metrics = json.loads(tool.related_metrics) if tool.related_metrics else []
        if any(m in related_metrics for m in metrics):
            matched_tools.append(tool)
    
    return matched_tools


@with_session
def init_default_tools(session) -> int:
    """
    初始化默认诊断工具
    
    @param session: 数据库会话
    @return: 创建的工具数量
    """
    default_tools = [
        {
            "tool_name": "obtain_metric_values",
            "tool_display_name": "获取系统指标",
            "tool_description": "获取数据库系统指标，包括CPU使用率、内存使用率、I/O统计等",
            "tool_category": "diagnostic",
            "input_schema": {"type": "object", "properties": {"metrics": {"type": "array", "items": {"type": "string"}}}},
            "related_metrics": ["cpu_percent", "memory_percent", "disk_io", "connections"],
            "related_experts": ["cpu_expert", "memory_expert", "io_expert"],
            "execution_function": "obtain_metric_values",
            "priority": 10
        },
        {
            "tool_name": "query_pg_stat_statements",
            "tool_display_name": "查询SQL执行统计",
            "tool_description": "查询pg_stat_statements视图，获取慢查询统计信息",
            "tool_category": "diagnostic",
            "input_schema": {"type": "object", "properties": {"top_n": {"type": "integer", "default": 5}, "threshold_ms": {"type": "integer", "default": 100}}},
            "related_metrics": ["query_time", "calls", "rows"],
            "related_experts": ["workload_expert", "database_expert"],
            "execution_function": "query_pg_stat_statements",
            "priority": 9
        },
        {
            "tool_name": "explain_query",
            "tool_display_name": "分析SQL执行计划",
            "tool_description": "分析指定查询的执行计划，识别性能瓶颈",
            "tool_category": "analysis",
            "input_schema": {"type": "object", "properties": {"query_id": {"type": "string"}}},
            "related_metrics": ["execution_plan", "cost", "rows"],
            "related_experts": ["workload_expert", "database_expert"],
            "execution_function": "explain_query",
            "priority": 8
        },
        {
            "tool_name": "check_lock_status",
            "tool_display_name": "检查锁状态",
            "tool_description": "检查数据库锁状态，识别锁竞争和死锁问题",
            "tool_category": "diagnostic",
            "input_schema": {"type": "object", "properties": {}},
            "related_metrics": ["lock_count", "blocking_locks", "lock_wait_time"],
            "related_experts": ["workload_expert"],
            "execution_function": "check_lock_status",
            "priority": 8
        },
        {
            "tool_name": "get_database_size",
            "tool_display_name": "获取数据库大小",
            "tool_description": "获取数据库和各表的存储大小信息",
            "tool_category": "diagnostic",
            "input_schema": {"type": "object", "properties": {}},
            "related_metrics": ["database_size", "table_size", "index_size"],
            "related_experts": ["io_expert", "database_expert"],
            "execution_function": "get_database_size",
            "priority": 7
        },
        {
            "tool_name": "check_active_sessions",
            "tool_display_name": "检查活跃会话",
            "tool_description": "检查当前活跃的数据库会话，识别长时间运行的查询",
            "tool_category": "diagnostic",
            "input_schema": {"type": "object", "properties": {"threshold_seconds": {"type": "integer", "default": 30}}},
            "related_metrics": ["active_sessions", "session_duration", "query_state"],
            "related_experts": ["cpu_expert", "workload_expert"],
            "execution_function": "check_active_sessions",
            "priority": 9
        },
        {
            "tool_name": "check_storage_stats",
            "tool_display_name": "检查存储统计",
            "tool_description": "检查表和索引的存储统计，识别死元组和膨胀问题",
            "tool_category": "diagnostic",
            "input_schema": {"type": "object", "properties": {}},
            "related_metrics": ["n_live_tup", "n_dead_tup", "seq_scan", "idx_scan"],
            "related_experts": ["io_expert", "database_expert"],
            "execution_function": "check_storage_stats",
            "priority": 7
        },
        {
            "tool_name": "optimize_index_selection",
            "tool_display_name": "索引优化建议",
            "tool_description": "分析表并给出索引优化建议",
            "tool_category": "action",
            "input_schema": {"type": "object", "properties": {"table": {"type": "string"}, "columns": {"type": "array", "items": {"type": "string"}}}},
            "related_metrics": ["index_usage", "seq_scan_ratio"],
            "related_experts": ["database_expert"],
            "execution_function": "optimize_index_selection",
            "priority": 6
        }
    ]
    
    created_count = 0
    for tool_data in default_tools:
        existing = session.query(DiagnosisTool).filter_by(tool_name=tool_data["tool_name"]).first()
        if not existing:
            tool = DiagnosisTool(
                tool_name=tool_data["tool_name"],
                tool_display_name=tool_data["tool_display_name"],
                tool_description=tool_data["tool_description"],
                tool_category=tool_data["tool_category"],
                input_schema=json.dumps(tool_data.get("input_schema"), ensure_ascii=False),
                related_metrics=json.dumps(tool_data.get("related_metrics", []), ensure_ascii=False),
                related_experts=json.dumps(tool_data.get("related_experts", []), ensure_ascii=False),
                execution_function=tool_data.get("execution_function"),
                priority=tool_data.get("priority", 0),
                create_time=datetime.now()
            )
            session.add(tool)
            created_count += 1
    
    return created_count
