#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : dynamic_tool_loader.py
@Author  : LI
@Date    : 2026
@Desc    : 动态工具加载器
           Reference: D-Bot Paper Section 5.2 - Dynamic Tool Selection
           
           核心功能：
           1. 基于 BM25 检索动态筛选最相关的工具
           2. 减少冗余信息干扰，降低 LLM 幻觉概率
           3. 支持工具描述的语义匹配
"""
import re
import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from rank_bm25 import BM25Okapi
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: Dict
    keywords: List[str]
    category: str
    priority: int  # 优先级，1-10，越高越优先


class DynamicToolLoader:
    """
    @class DynamicToolLoader
    @brief 动态工具加载器 - 基于 BM25 检索动态筛选工具
    @reference D-Bot Paper Section 5.2 - Tool Matching
    
    解决的问题：
    - 静态工具列表过长，导致 LLM 注意力分散
    - 无关工具干扰，增加幻觉概率
    - 工具选择效率低下
    """
    
    DEFAULT_TOOLS = [
        ToolDefinition(
            name="obtain_metric_values",
            description="获取系统指标（CPU、内存、I/O等）",
            parameters={"metrics": ["cpu", "memory", "io"]},
            keywords=["cpu", "memory", "io", "指标", "性能", "使用率", "metrics", "performance"],
            category="monitoring",
            priority=8
        ),
        ToolDefinition(
            name="query_pg_stat_statements",
            description="查询SQL执行统计，获取慢查询列表和query_id",
            parameters={"sort_by": "total_exec_time", "limit": 10},
            keywords=["sql", "query", "慢查询", "slow", "执行时间", "pg_stat", "statements"],
            category="diagnosis",
            priority=9
        ),
        ToolDefinition(
            name="explain_query",
            description="分析SQL执行计划（需要先获取query_id）",
            parameters={"query_id": "从query_pg_stat_statements获取的数值ID"},
            keywords=["explain", "执行计划", "plan", "analyze", "优化", "索引"],
            category="diagnosis",
            priority=7
        ),
        ToolDefinition(
            name="check_lock_status",
            description="检查锁状态，发现阻塞和死锁",
            parameters={},
            keywords=["lock", "锁", "阻塞", "block", "deadlock", "死锁", "等待"],
            category="diagnosis",
            priority=8
        ),
        ToolDefinition(
            name="get_database_size",
            description="获取数据库大小和表空间信息",
            parameters={},
            keywords=["size", "大小", "存储", "storage", "table", "表", "空间"],
            category="monitoring",
            priority=5
        ),
        ToolDefinition(
            name="check_active_sessions",
            description="检查活跃会话和连接状态",
            parameters={},
            keywords=["session", "会话", "连接", "connection", "active", "活跃"],
            category="monitoring",
            priority=7
        ),
        ToolDefinition(
            name="check_storage_stats",
            description="检查存储统计，发现表膨胀和索引问题",
            parameters={},
            keywords=["storage", "存储", "膨胀", "bloat", "vacuum", "死元组", "索引"],
            category="diagnosis",
            priority=6
        ),
        ToolDefinition(
            name="Finish",
            description="完成诊断，输出结论",
            parameters={"root_cause": "根因分析", "solutions": ["解决方案"]},
            keywords=["finish", "完成", "结论", "result", "结束"],
            category="terminal",
            priority=10
        )
    ]
    
    ANOMALY_TYPE_TOOL_MAPPING = {
        "cpu_high": ["obtain_metric_values", "query_pg_stat_statements", "check_active_sessions"],
        "highcpu": ["obtain_metric_values", "query_pg_stat_statements", "check_active_sessions"],
        "memory_high": ["obtain_metric_values", "check_storage_stats", "get_database_size"],
        "highmemory": ["obtain_metric_values", "check_storage_stats", "get_database_size"],
        "slow_sql": ["query_pg_stat_statements", "explain_query", "check_storage_stats"],
        "slowqueries": ["query_pg_stat_statements", "explain_query", "check_storage_stats"],
        "lock_wait": ["check_lock_status", "check_active_sessions"],
        "lockwait": ["check_lock_status", "check_active_sessions"],
        "connection_overflow": ["check_active_sessions", "get_database_size"],
        "connectionexhausted": ["check_active_sessions", "get_database_size"],
        "io_bottleneck": ["obtain_metric_values", "check_storage_stats", "get_database_size"],
        "highdiskio": ["obtain_metric_values", "check_storage_stats", "get_database_size"],
        "tablebloat": ["check_storage_stats", "get_database_size"],
        "lowcachehit": ["obtain_metric_values", "query_pg_stat_statements"]
    }
    
    def __init__(self, tools: List[ToolDefinition] = None):
        self.tools = tools or self.DEFAULT_TOOLS
        self.bm25_index = None
        self.tokenized_corpus = []
        self._build_bm25_index()
    
    def _build_bm25_index(self):
        """构建 BM25 索引"""
        corpus = []
        for tool in self.tools:
            text = f"{tool.name} {tool.description} {' '.join(tool.keywords)}"
            corpus.append(text)
        
        self.tokenized_corpus = [doc.split() for doc in corpus]
        self.bm25_index = BM25Okapi(self.tokenized_corpus)
        
        logger.info(f"[DynamicToolLoader] BM25 索引构建完成，共 {len(self.tools)} 个工具")
    
    def select_tools(
        self,
        anomaly_info: Dict,
        reasoning_context: str = "",
        top_k: int = 5
    ) -> List[ToolDefinition]:
        """
        @brief 动态选择最相关的工具
        @param anomaly_info: 异常信息
        @param reasoning_context: 推理上下文（历史步骤）
        @param top_k: 返回的工具数量
        @return: 最相关的工具列表
        """
        selected_tools = []
        
        alert_type = anomaly_info.get("alert_type", "") or anomaly_info.get("anomaly_type", "")
        alert_type_key = alert_type.lower().replace("_", "").replace("-", "")
        
        if alert_type_key in self.ANOMALY_TYPE_TOOL_MAPPING:
            mapped_tool_names = self.ANOMALY_TYPE_TOOL_MAPPING[alert_type_key]
            for tool in self.tools:
                if tool.name in mapped_tool_names:
                    selected_tools.append(tool)
        
        query_text = f"{alert_type} {anomaly_info.get('description', '')} {reasoning_context}"
        query_tokens = query_text.lower().split()
        
        bm25_scores = self.bm25_index.get_scores(query_tokens)
        top_indices = np.argsort(bm25_scores)[-top_k:][::-1]
        
        for idx in top_indices:
            tool = self.tools[idx]
            if tool not in selected_tools:
                selected_tools.append(tool)
        
        finish_tool = next((t for t in self.tools if t.name == "Finish"), None)
        if finish_tool and finish_tool not in selected_tools:
            selected_tools.append(finish_tool)
        
        selected_tools.sort(key=lambda t: t.priority, reverse=True)
        
        return selected_tools[:top_k + 1]
    
    def format_tools_for_prompt(self, tools: List[ToolDefinition]) -> str:
        """
        @brief 格式化工具列表为 Prompt 格式
        @param tools: 工具列表
        @return: 格式化的工具描述字符串
        """
        lines = ["# 【可用工具列表】"]
        for i, tool in enumerate(tools, 1):
            params_str = json.dumps(tool.parameters, ensure_ascii=False)
            lines.append(f"{i}. {tool.name} - {tool.description}")
            lines.append(f"   参数: {params_str}")
        
        return "\n".join(lines)
    
    def get_tool_by_name(self, name: str) -> Optional[ToolDefinition]:
        """根据名称获取工具"""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
    
    def validate_tool_call(self, tool_name: str, action_input: Dict) -> Tuple[bool, str]:
        """
        @brief 验证工具调用是否合法
        @param tool_name: 工具名称
        @param action_input: 调用参数
        @return: (是否合法, 错误信息)
        """
        tool = self.get_tool_by_name(tool_name)
        if not tool:
            return False, f"未知工具: {tool_name}"
        
        if tool_name == "Finish":
            if not action_input.get("root_cause"):
                return False, "Finish 工具必须提供 root_cause 参数"
            return True, ""
        
        if tool_name == "explain_query":
            if not action_input.get("query_id"):
                return False, "explain_query 必须提供 query_id 参数（从 query_pg_stat_statements 获取）"
            if not isinstance(action_input.get("query_id"), (int, float)):
                return False, "query_id 必须是数值类型"
            return True, ""
        
        return True, ""


def get_dynamic_tools(anomaly_info: Dict, reasoning_context: str = "", top_k: int = 5) -> List[Dict]:
    """
    @brief 便捷函数：获取动态工具列表
    @param anomaly_info: 异常信息
    @param reasoning_context: 推理上下文
    @param top_k: 返回数量
    @return: 工具字典列表
    """
    loader = DynamicToolLoader()
    tools = loader.select_tools(anomaly_info, reasoning_context, top_k)
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
            "priority": t.priority
        }
        for t in tools
    ]


def format_tools_for_prompt(tools: List[ToolDefinition]) -> str:
    """便捷函数：格式化工具列表"""
    loader = DynamicToolLoader()
    return loader.format_tools_for_prompt(tools)


dynamic_tool_loader = DynamicToolLoader()


__all__ = [
    'DynamicToolLoader',
    'ToolDefinition',
    'get_dynamic_tools',
    'format_tools_for_prompt',
    'dynamic_tool_loader'
]
