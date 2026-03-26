#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : diagnosis_enhancer.py
@Author  : LI
@Date    : 2026
@Desc    : 诊断报告增强模块
            实现「硬编码做规则/数据/结构，DeepSeek做智能分析/专业建议」的混合架构
            明确界定DeepSeek的调用边界，优化诊断报告质量

架构分工原则：
| 功能模块 | 实现方式 | 禁止调用DeepSeek | 必须调用DeepSeek |
|---------|---------|------------------|------------------|
| 异常类型字段映射与一致性 | 硬编码规则 | ✅ | ❌ |
| 慢查询/执行计划/数据库配置等基础数据采集 | 硬编码SQL查询 | ✅ | ❌ |
| 报告基础结构与字段规范 | 硬编码模板 | ✅ | ❌ |
| 根因深度分析、TOP SQL瓶颈定位 | LLM生成 | ❌ | ✅ |
| 针对性优化建议、落地细节、风险评估 | LLM生成 | ❌ | ✅ |
| Markdown报告内容排版与填充 | 硬编码模板+LLM结果 | 结构部分✅，内容部分❌ | 专业内容部分✅ |
"""

import json
import os
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from server.utils import normalize_data, safe_json_dumps

logger = logging.getLogger(__name__)


# ==============================================================================
# 第一部分：硬编码规则 - 根因类型与异常类型映射表
# 禁止调用DeepSeek，完全硬编码实现
# ==============================================================================

ROOT_CAUSE_TYPE_MAPPING = {
    "Slow Queries": "SlowQueries",
    "SlowQueries": "SlowQueries",
    "Long Running Queries": "SlowQueries",
    "High CPU Usage": "HighCPU",
    "HighCPU": "HighCPU",
    "CPU High": "HighCPU",
    "High Memory Usage": "HighMemory",
    "HighMemory": "HighMemory",
    "Memory High": "HighMemory",
    "High Disk IO": "HighDiskIO",
    "HighDiskIO": "HighDiskIO",
    "Disk IO High": "HighDiskIO",
    "Lock Wait/Deadlock": "LockWait",
    "LockWait": "LockWait",
    "Lock Contention": "LockWait",
    "Deadlock": "LockWait",
    "Connection Exhausted": "ConnectionExhausted",
    "ConnectionExhausted": "ConnectionExhausted",
    "Connection Pool Exhausted": "ConnectionExhausted",
    "Low Cache Hit Ratio": "LowCacheHit",
    "LowCacheHit": "LowCacheHit",
    "Cache Hit Low": "LowCacheHit",
    "Missing Indexes": "MissingIndex",
    "MissingIndex": "MissingIndex",
    "Table Bloat": "TableBloat",
    "TableBloat": "TableBloat",
    "Idle Transaction": "IdleTransaction",
    "IdleTransaction": "IdleTransaction",
    "Blocked Session": "BlockedSession",
    "BlockedSession": "BlockedSession",
    "High Rollback Rate": "HighRollback",
    "HighRollback": "HighRollback",
    "Rollback": "HighRollback",
}

ANOMALY_TYPE_DISPLAY_NAMES = {
    "SlowQueries": "慢查询问题",
    "HighCPU": "CPU使用率过高",
    "HighMemory": "内存使用率过高",
    "HighDiskIO": "磁盘I/O过高",
    "LockWait": "锁等待/死锁",
    "ConnectionExhausted": "连接池耗尽",
    "LowCacheHit": "缓存命中率过低",
    "MissingIndex": "索引缺失",
    "TableBloat": "表膨胀",
    "IdleTransaction": "空闲事务",
    "BlockedSession": "阻塞会话",
    "HighRollback": "高回滚率",
    "unknown": "未知异常",
}

ALERT_SEVERITY_MAPPING = {
    "SlowQueries": "warning",
    "HighCPU": "critical",
    "HighMemory": "critical",
    "HighDiskIO": "warning",
    "LockWait": "critical",
    "ConnectionExhausted": "critical",
    "LowCacheHit": "warning",
    "MissingIndex": "warning",
    "TableBloat": "warning",
    "IdleTransaction": "warning",
    "BlockedSession": "critical",
    "HighRollback": "warning",
    "unknown": "info",
}


def normalize_anomaly_type(root_cause_type: str) -> str:
    """
    将根因类型标准化为异常类型
    
    @param root_cause_type: 根因类型字符串
    @return: 标准化的异常类型
    """
    if not root_cause_type:
        return "unknown"
    
    root_cause_type = root_cause_type.strip()
    
    # 直接匹配
    if root_cause_type in ROOT_CAUSE_TYPE_MAPPING:
        return ROOT_CAUSE_TYPE_MAPPING[root_cause_type]
    
    # 模糊匹配
    root_cause_lower = root_cause_type.lower()
    
    for key, value in ROOT_CAUSE_TYPE_MAPPING.items():
        if key.lower() in root_cause_lower or root_cause_lower in key.lower():
            return value
    
    # ========== 新增：关键词匹配兜底 ==========
    # 慢查询相关
    if any(kw in root_cause_lower for kw in ['slow', 'query', 'sql', '查询', '慢']):
        return "SlowQueries"
    
    # CPU相关
    if any(kw in root_cause_lower for kw in ['cpu', 'processor', '处理器']):
        return "HighCPU"
    
    # 内存相关
    if any(kw in root_cause_lower for kw in ['memory', 'mem', '内存', 'oom']):
        return "HighMemory"
    
    # IO相关
    if any(kw in root_cause_lower for kw in ['io', 'disk', 'i/o', '磁盘', '读写']):
        return "HighDiskIO"
    
    # 锁相关
    if any(kw in root_cause_lower for kw in ['lock', 'deadlock', '锁', '死锁']):
        return "LockWait"
    
    # 连接相关
    if any(kw in root_cause_lower for kw in ['connection', 'connect', '连接', 'pool']):
        return "ConnectionExhausted"
    
    # 缓存相关
    if any(kw in root_cause_lower for kw in ['cache', 'hit', '缓存', '命中']):
        return "LowCacheHit"
    
    # 索引相关
    if any(kw in root_cause_lower for kw in ['index', '索引', 'seq scan']):
        return "MissingIndex"
    
    # 表膨胀相关
    if any(kw in root_cause_lower for kw in ['bloat', 'vacuum', '膨胀', 'dead tuple']):
        return "TableBloat"
    
    # 事务相关
    if any(kw in root_cause_lower for kw in ['transaction', 'idle', '事务', '空闲']):
        return "IdleTransaction"
    
    # 阻塞相关
    if any(kw in root_cause_lower for kw in ['block', 'wait', '阻塞', '等待']):
        return "BlockedSession"
    
    # 回滚相关
    if any(kw in root_cause_lower for kw in ['rollback', '回滚', 'abort']):
        return "HighRollback"
    
    return "unknown"


def get_anomaly_display_name(anomaly_type: str) -> str:
    """获取异常类型的中文显示名称"""
    return ANOMALY_TYPE_DISPLAY_NAMES.get(anomaly_type, anomaly_type)


def get_alert_severity(anomaly_type: str) -> str:
    """获取异常类型的告警严重级别"""
    return ALERT_SEVERITY_MAPPING.get(anomaly_type, "info")


# ==============================================================================
# 第二部分：硬编码SQL - 前置基础数据采集模块
# 禁止调用DeepSeek，完全使用硬编码SQL查询
# ==============================================================================

@dataclass
class DiagnosisContext:
    """诊断上下文数据结构"""
    alert_info: Dict[str, Any] = field(default_factory=dict)
    full_slow_queries: List[Dict] = field(default_factory=list)
    top1_execution_plan: Dict[str, Any] = field(default_factory=dict)
    db_config: Dict[str, Any] = field(default_factory=dict)
    server_memory_total: float = 0.0
    auxiliary_data: Dict[str, Any] = field(default_factory=dict)
    collection_errors: List[str] = field(default_factory=list)
    collection_timestamp: str = ""


class DiagnosisDataCollector:
    """
    诊断数据采集器 - 硬编码SQL实现
    
    在触发DeepSeek诊断之前，必须先通过硬编码SQL完整采集数据
    禁止让DeepSeek做数据获取工作
    """
    
    def __init__(self, db_connector=None):
        """
        初始化数据采集器
        
        @param db_connector: 数据库连接器实例
        """
        self.db = db_connector
        self._connect_status = None
    
    def _get_db_connection(self):
        """获取数据库连接"""
        if self.db is None:
            from server.diagnose.db_connector import real_db_tool
            self.db = real_db_tool
        return self.db
    
    def _get_db_executor(self):
        """获取底层数据库执行器（DatabaseConnector实例）"""
        db = self._get_db_connection()
        if hasattr(db, 'db') and hasattr(db.db, 'execute_query'):
            return db.db
        elif hasattr(db, 'execute_query'):
            return db
        else:
            raise AttributeError("无法获取有效的数据库执行器")
    
    def collect_targeted_diagnosis_data(
        self,
        alert_info: Dict[str, Any],
        original_root_causes: List[Dict] = None
    ) -> DiagnosisContext:
        """
        【整改后】基于原专家诊断结果的定向数据采集
        不再全量采集，仅采集与原根因相关的补充数据
        
        @param alert_info: 异常告警信息
        @param original_root_causes: 原多专家诊断的根因列表
        @return: DiagnosisContext 包含采集的数据
        """
        context = DiagnosisContext(
            alert_info=alert_info,
            collection_timestamp=datetime.now().isoformat()
        )
        
        target_types = set()
        if original_root_causes:
            for cause in original_root_causes:
                cause_type = cause.get("type", "").lower()
                if any(kw in cause_type for kw in ['slow', 'query', 'sql', 'cpu']):
                    target_types.add("slow_queries")
                    target_types.add("execution_plan")
                if any(kw in cause_type for kw in ['memory', 'cache', 'config']):
                    target_types.add("db_config")
                if any(kw in cause_type for kw in ['lock', 'wait', 'block', 'deadlock']):
                    target_types.add("auxiliary")
                if any(kw in cause_type for kw in ['bloat', 'vacuum', 'table']):
                    target_types.add("auxiliary")
                if any(kw in cause_type for kw in ['idle', 'transaction']):
                    target_types.add("auxiliary")
        
        if not target_types:
            target_types = {"slow_queries", "db_config", "auxiliary"}
        
        try:
            db = self._get_db_executor()
            
            if hasattr(db, 'is_connected') and callable(getattr(db, 'is_connected')):
                if not db.is_connected():
                    if hasattr(db, 'connect') and callable(getattr(db, 'connect')):
                        if not db.connect():
                            context.collection_errors.append("数据库连接失败")
                            return context
            
            if "slow_queries" in target_types:
                context.full_slow_queries = self._collect_full_slow_queries(context)
            
            if "execution_plan" in target_types and context.full_slow_queries:
                context.top1_execution_plan = self._collect_top1_execution_plan_safe(context)
            
            if "db_config" in target_types:
                context.db_config = self._collect_database_config(context)
                context.server_memory_total = self._collect_server_memory(context)
            
            if "auxiliary" in target_types:
                context.auxiliary_data = self._collect_auxiliary_data(context)
            
            logger.info(f"[OK] 定向数据采集完成，目标类型: {target_types}")
            
        except Exception as e:
            logger.error(f"采集诊断数据失败: {e}")
            context.collection_errors.append(f"数据采集异常: {str(e)}")
        
        return context
    
    def _collect_full_slow_queries(self, context: DiagnosisContext) -> List[Dict]:
        """
        采集完整慢查询数据 - 禁止截断query字段
        
        从pg_stat_statements获取TOP 10慢查询，必须保留完整SQL语句
        """
        queries = []
        
        try:
            db = self._get_db_executor()
            
            sql = """
            SELECT 
                queryid as query_id,
                query,
                calls,
                total_exec_time as total_time,
                mean_exec_time as mean_time,
                min_exec_time as min_time,
                max_exec_time as max_time,
                rows,
                shared_blks_hit,
                shared_blks_read,
                100.0 * shared_blks_hit / NULLIF(shared_blks_hit + shared_blks_read, 0) as cache_hit_ratio
            FROM pg_stat_statements
            WHERE query NOT LIKE '%pg_stat%'
            ORDER BY total_exec_time DESC
            LIMIT 10
            """
            
            results = db.execute_query(sql)
            
            if results:
                for row in results:
                    cache_hit = row.get("cache_hit_ratio")
                    if cache_hit is not None:
                        cache_hit = float(cache_hit)
                    else:
                        cache_hit = 0.0
                    
                    queries.append({
                        "query_id": row.get("query_id"),
                        "query": row.get("query", ""),
                        "calls": int(row.get("calls", 0) or 0),
                        "total_time": float(row.get("total_time", 0) or 0),
                        "mean_time": float(row.get("mean_time", 0) or 0),
                        "min_time": float(row.get("min_time", 0) or 0),
                        "max_time": float(row.get("max_time", 0) or 0),
                        "rows": int(row.get("rows", 0) or 0),
                        "cache_hit_ratio": round(cache_hit, 2)
                    })
                
                logger.info(f"[OK] 采集到 {len(queries)} 条完整慢查询数据")
            else:
                context.collection_errors.append("pg_stat_statements未启用或无慢查询数据")
                
        except Exception as e:
            error_msg = f"采集慢查询失败: {str(e)}"
            logger.error(error_msg)
            context.collection_errors.append(error_msg)
        
        return queries
    
    def _collect_top1_execution_plan(self, context: DiagnosisContext) -> Dict[str, Any]:
        """
        采集TOP 1慢查询的执行计划
        
        针对总耗时最高的慢查询，自动执行EXPLAIN ANALYZE
        注意：DDL语句不支持EXPLAIN ANALYZE，需要特殊处理
        """
        execution_plan = {
            "available": False,
            "plan": None,
            "error": None
        }
        
        if not context.full_slow_queries:
            execution_plan["error"] = "无慢查询数据，跳过执行计划采集"
            return execution_plan
        
        try:
            top_query = context.full_slow_queries[0]
            query_text = top_query.get("query", "")
            
            if not query_text or len(query_text.strip()) < 5:
                execution_plan["error"] = "SQL语句为空或过短"
                return execution_plan
            
            query_clean = query_text.strip().upper()
            
            ddl_keywords = ['CREATE', 'ALTER', 'DROP', 'TRUNCATE', 'COMMENT', 'GRANT', 'REVOKE', 'VACUUM', 'REINDEX']
            
            is_ddl = any(query_clean.startswith(keyword) for keyword in ddl_keywords)
            
            if is_ddl:
                ddl_type = next((kw for kw in ddl_keywords if query_clean.startswith(kw)), "DDL")
                execution_plan["available"] = False
                execution_plan["error"] = f"该语句为{ddl_type}类型DDL，PostgreSQL不支持对DDL执行EXPLAIN ANALYZE，已跳过"
                execution_plan["query_id"] = top_query.get("query_id")
                execution_plan["query_text"] = query_text[:500]
                execution_plan["sql_type"] = "DDL"
                logger.info(f"[INFO] TOP 1慢查询为DDL语句({ddl_type})，跳过执行计划分析")
                return execution_plan
            
            db = self._get_db_executor()
            
            explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query_text}"
            
            results = db.execute_query(explain_sql)
            
            if results:
                execution_plan["available"] = True
                execution_plan["plan"] = results[0] if results else None
                execution_plan["query_id"] = top_query.get("query_id")
                execution_plan["query_text"] = query_text[:500]
                execution_plan["sql_type"] = "DML/DQL"
                logger.info("[OK] TOP 1慢查询执行计划采集成功")
            else:
                execution_plan["error"] = "执行计划返回为空"
                
        except Exception as e:
            error_msg = f"采集执行计划失败: {str(e)}"
            logger.warning(error_msg)
            execution_plan["error"] = error_msg
            context.collection_errors.append(error_msg)
        
        return execution_plan
    
    def _collect_top1_execution_plan_safe(self, context: DiagnosisContext) -> Dict[str, Any]:
        """
        【整改后】安全采集执行计划 - 仅使用 EXPLAIN，不使用 ANALYZE
        避免在业务库实际执行慢查询
        """
        execution_plan = {
            "available": False,
            "plan": None,
            "error": None,
            "note": "使用 EXPLAIN (无 ANALYZE) 安全模式采集"
        }
        
        if not context.full_slow_queries:
            execution_plan["error"] = "无慢查询数据，跳过执行计划采集"
            return execution_plan
        
        try:
            top_query = context.full_slow_queries[0]
            query_text = top_query.get("query", "")
            
            if not query_text or len(query_text.strip()) < 5:
                execution_plan["error"] = "SQL语句为空或过短"
                return execution_plan
            
            query_clean = query_text.strip().upper()
            ddl_keywords = ['CREATE', 'ALTER', 'DROP', 'TRUNCATE', 'COMMENT', 'GRANT', 'REVOKE', 'VACUUM', 'REINDEX']
            
            if any(query_clean.startswith(keyword) for keyword in ddl_keywords):
                execution_plan["error"] = "该语句为DDL类型，跳过执行计划分析"
                execution_plan["query_id"] = top_query.get("query_id")
                return execution_plan
            
            db = self._get_db_executor()
            
            explain_sql = f"EXPLAIN (FORMAT JSON) {query_text}"
            
            results = db.execute_query(explain_sql)
            
            if results:
                execution_plan["available"] = True
                execution_plan["plan"] = results[0] if results else None
                execution_plan["query_id"] = top_query.get("query_id")
                logger.info("[OK] TOP 1慢查询执行计划(安全模式)采集成功")
            else:
                execution_plan["error"] = "执行计划返回为空"
                
        except Exception as e:
            error_msg = f"采集执行计划失败: {str(e)}"
            logger.warning(error_msg)
            execution_plan["error"] = error_msg
        
        return execution_plan
    
    def _collect_database_config(self, context: DiagnosisContext) -> Dict[str, Any]:
        """
        采集数据库核心配置参数
        """
        config = {}
        
        try:
            db = self._get_db_executor()
            
            sql = """
            SELECT 
                name,
                setting,
                unit,
                short_desc
            FROM pg_settings
            WHERE name IN (
                'shared_buffers',
                'effective_cache_size',
                'work_mem',
                'maintenance_work_mem',
                'max_connections',
                'random_page_cost',
                'effective_io_concurrency',
                'checkpoint_completion_target',
                'wal_buffers',
                'default_statistics_target'
            )
            ORDER BY name
            """
            
            results = db.execute_query(sql)
            
            for row in results:
                name = row.get("name", "")
                setting = row.get("setting", "")
                unit = row.get("unit", "")
                
                if unit == "kB":
                    value_mb = float(setting) / 1024
                    config[name] = {
                        "value": setting,
                        "unit": unit,
                        "value_mb": round(value_mb, 2),
                        "description": row.get("short_desc", "")
                    }
                elif unit == "8kB":
                    value_mb = float(setting) * 8 / 1024
                    config[name] = {
                        "value": setting,
                        "unit": unit,
                        "value_mb": round(value_mb, 2),
                        "description": row.get("short_desc", "")
                    }
                else:
                    config[name] = {
                        "value": setting,
                        "unit": unit,
                        "description": row.get("short_desc", "")
                    }
            
            conn_sql = """
            SELECT 
                (SELECT count(*) FROM pg_stat_activity) as current_connections,
                (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections
            """
            conn_result = db.execute_query(conn_sql)
            if conn_result:
                current = conn_result[0].get("current_connections", 0)
                max_conn = conn_result[0].get("max_connections", 100)
                config["connection_usage"] = {
                    "current": int(current or 0),
                    "max": int(max_conn or 100),
                    "usage_percent": round(int(current or 0) / int(max_conn or 100) * 100, 2)
                }
            
            logger.info(f"[OK] 数据库配置采集完成: {len(config)} 个参数")
            
        except Exception as e:
            error_msg = f"采集数据库配置失败: {str(e)}"
            logger.error(error_msg)
            context.collection_errors.append(error_msg)
        
        return config
    
    def _collect_server_memory(self, context: DiagnosisContext) -> float:
        """
        采集服务器物理内存总量
        """
        try:
            import psutil
            memory = psutil.virtual_memory()
            total_gb = memory.total / (1024 ** 3)
            logger.info(f"[OK] 服务器内存: {total_gb:.2f} GB")
            return round(total_gb, 2)
        except Exception as e:
            logger.warning(f"采集服务器内存失败: {e}")
            return 0.0
    
    def _collect_auxiliary_data(self, context: DiagnosisContext) -> Dict[str, Any]:
        """
        采集辅助诊断数据：表膨胀、空闲事务等
        """
        auxiliary = {
            "table_bloat": [],
            "idle_transactions": [],
            "blocked_sessions": []
        }
        
        try:
            db = self._get_db_executor()
            
            bloat_sql = """
            SELECT 
                schemaname,
                relname as table_name,
                n_live_tup as live_tuples,
                n_dead_tup as dead_tuples,
                CASE 
                    WHEN n_live_tup > 0 THEN round(100.0 * n_dead_tup / n_live_tup, 2)
                    ELSE 0 
                END as dead_ratio,
                pg_size_pretty(pg_total_relation_size(relid)) as table_size
            FROM pg_stat_user_tables
            WHERE n_dead_tup > 0
            ORDER BY n_dead_tup DESC
            LIMIT 10
            """
            
            bloat_result = db.execute_query(bloat_sql)
            if bloat_result:
                for row in bloat_result:
                    dead_ratio = float(row.get("dead_ratio", 0) or 0)
                    if dead_ratio > 5:
                        auxiliary["table_bloat"].append({
                            "schema": row.get("schemaname"),
                            "table": row.get("table_name"),
                            "live_tuples": int(row.get("live_tuples", 0) or 0),
                            "dead_tuples": int(row.get("dead_tuples", 0) or 0),
                            "dead_ratio": dead_ratio,
                            "size": row.get("table_size")
                        })
            
            idle_sql = """
            SELECT 
                pid,
                usename,
                application_name,
                client_addr,
                backend_start,
                xact_start,
                query_start,
                state,
                EXTRACT(EPOCH FROM (now() - xact_start)) as idle_seconds,
                query
            FROM pg_stat_activity
            WHERE state = 'idle in transaction'
            AND xact_start < now() - interval '30 minutes'
            ORDER BY xact_start ASC
            """
            
            idle_result = db.execute_query(idle_sql)
            if idle_result:
                for row in idle_result:
                    auxiliary["idle_transactions"].append({
                        "pid": row.get("pid"),
                        "user": row.get("usename"),
                        "application": row.get("application_name"),
                        "client_addr": str(row.get("client_addr", "")),
                        "idle_seconds": int(float(row.get("idle_seconds", 0) or 0)),
                        "query": (row.get("query") or "")[:200]
                    })
            
            blocked_sql = """
            SELECT 
                blocked.pid as blocked_pid,
                blocked.usename as blocked_user,
                blocking.pid as blocking_pid,
                blocking.usename as blocking_user,
                blocked.query as blocked_query,
                EXTRACT(EPOCH FROM (now() - blocked.query_start)) as wait_seconds
            FROM pg_stat_activity blocked
            JOIN pg_locks blocked_locks ON blocked.pid = blocked_locks.pid
            JOIN pg_locks blocking_locks ON blocked_locks.locktype = blocking_locks.locktype
                AND blocked_locks.database IS NOT DISTINCT FROM blocking_locks.database
                AND blocked_locks.relation IS NOT DISTINCT FROM blocking_locks.relation
                AND blocked_locks.page IS NOT DISTINCT FROM blocking_locks.page
                AND blocked_locks.tuple IS NOT DISTINCT FROM blocking_locks.tuple
                AND blocked_locks.pid != blocking_locks.pid
            JOIN pg_stat_activity blocking ON blocking_locks.pid = blocking.pid
            WHERE NOT blocked_locks.granted
            """
            
            blocked_result = db.execute_query(blocked_sql)
            if blocked_result:
                for row in blocked_result:
                    auxiliary["blocked_sessions"].append({
                        "blocked_pid": row.get("blocked_pid"),
                        "blocked_user": row.get("blocked_user"),
                        "blocking_pid": row.get("blocking_pid"),
                        "blocking_user": row.get("blocking_user"),
                        "wait_seconds": int(float(row.get("wait_seconds", 0) or 0)),
                        "query": (row.get("blocked_query") or "")[:200]
                    })
            
            logger.info(f"[OK] 辅助数据采集完成: 表膨胀={len(auxiliary['table_bloat'])}, 空闲事务={len(auxiliary['idle_transactions'])}, 阻塞会话={len(auxiliary['blocked_sessions'])}")
            
        except Exception as e:
            error_msg = f"采集辅助数据失败: {str(e)}"
            logger.error(error_msg)
            context.collection_errors.append(error_msg)
        
        return auxiliary


# ==============================================================================
# 第三部分：DeepSeek Prompt模板 - 必须调用DeepSeek
# 仅此处做LLM调用，生成结构化的分析结果
# ==============================================================================

DEEPSEEK_DIAGNOSIS_PROMPT_TEMPLATE = """你是一名资深PostgreSQL数据库DBA，作为**多专家诊断结果的校验者与增强者**，基于以下数据完成工作。
 
# ⛔⛔⛔ 【核心定位禁令 - 最高优先级】⛔⛔⛔
1. **禁止重新定位根因**：你的工作是校验、补充、关联、深化原专家的诊断结果，而非推翻重来
2. **禁止覆盖原结论**：如果原专家结论有数据支撑，必须保留并深化；仅当原结论与实测数据严重矛盾时，才标注质疑
3. **禁止空泛套话**：所有分析必须基于提供的「原专家结果 + 实测数据」

# ⛔⛔⛔ 【优化2：字段完整性约束 - 最高优先级】⛔⛔⛔
1. **禁止跳过字段**：integrated_optimization_solutions 中的每个对象必须包含所有字段，绝对不允许留空或输出"无"
2. **方案数量限制**：只输出 Top 3 最有效的解决方案，确保每个方案都有详细的 implementation_details
3. **字段必填**：action, sql, priority, risk_level, expected_effect, implementation_details, source_expert 全部必填
4. **描述字数限制**：每个 diagnosis_steps 描述不得超过 50 字，确保 JSON 完整闭合

=== 输入数据 ===

1. 异常告警信息：
{alert_info}

2. 【核心】原多专家诊断结果（这是你的工作基础）：
{original_expert_results_json}

3. 补充采集的实测数据：
   - TOP 10慢查询：{full_slow_queries_json}
   - TOP 1执行计划：{top1_execution_plan_json}
   - 数据库配置：{db_config_json}
   - 服务器内存：{server_memory_total} GB
   - 辅助数据：{auxiliary_data_json}

=== 你的具体任务 ===

1. **专家结论校验**：
   - 逐条校验原专家的根因是否有实测数据支撑
   - 标注哪些结论是「确认有效」，哪些是「需补充验证」，哪些是「与数据矛盾」

2. **根因关联分析**：
   - 分析不同专家根因之间的因果关系、关联关系
   - 例如：CPU专家发现的高消耗SQL，是否与SQL专家发现的索引缺失有因果关系？

3. **深度补充分析**：
   - 针对原专家结论，补充更深度的技术分析、影响范围评估
   - 基于慢查询和执行计划，给出TOP SQL的精准瓶颈分析

4. **优化方案整合**：
   - 整合、排序不同专家的优化建议
   - 补充落地细节、风险评估、执行顺序建议

=== 固定输出JSON格式 ===
{{
    "expert_validation": [
        {{
            "original_cause_index": 0,
            "original_cause_type": "原根因类型",
            "validation_result": "确认有效/需补充验证/与数据矛盾",
            "validation_evidence": "验证依据（具体数据支撑）",
            "deepened_analysis": "深化后的分析描述（可选）"
        }}
    ],
    "root_cause_relation_analysis": "根因之间的关联关系分析（如存在因果、包含等）",
    "top_sql_enhanced_analysis": {{
        "bottleneck": "TOP SQL精准瓶颈分析",
        "targeted_suggestions": ["针对该SQL的精准建议1", "建议2"]
    }},
    "integrated_optimization_solutions": [
        {{
            "action": "操作名称（必填）",
            "sql": "可执行SQL（必填）",
            "priority": "高/中/低（必填）",
            "risk_level": "低风险/中风险/高风险（必填）",
            "expected_effect": "预期效果（必填）",
            "implementation_details": "落地细节（必填，禁止留空）",
            "source_expert": "该建议来源的原专家类型（必填）"
        }}
    ],
    "quick_action_guide": ["快速操作1", "快速操作2"]
}}

【重要提醒】
- 只输出 Top 3 解决方案，确保每个字段都有实质内容
- implementation_details 必须详细说明为什么这样做、适用于什么场景
- 确保 JSON 结构完整闭合，不要截断
"""


def build_deepseek_prompt(
    context: DiagnosisContext,
    original_result: Dict[str, Any] = None
) -> str:
    """
    【整改后】构建DeepSeek Prompt - 注入原专家结果
    
    @param context: 诊断上下文数据
    @param original_result: 原Tree Search/多专家诊断结果
    @return: 格式化的Prompt字符串
    """
    alert_info_str = safe_json_dumps(context.alert_info, indent=2)
    
    original_expert_results = original_result.get("root_causes", []) if original_result else []
    original_expert_str = safe_json_dumps(original_expert_results, indent=2)
    
    multi_agent_result = original_result.get("multi_agent_result", {}) if original_result else {}
    expert_results = multi_agent_result.get("expert_results", [])
    collaborative_str = safe_json_dumps(expert_results, indent=2) if expert_results else "[]"
    
    slow_queries_str = safe_json_dumps(context.full_slow_queries, indent=2) if context.full_slow_queries else "[]"
    exec_plan_str = safe_json_dumps(context.top1_execution_plan, indent=2) if context.top1_execution_plan else "{}"
    db_config_str = safe_json_dumps(context.db_config, indent=2) if context.db_config else "{}"
    auxiliary_str = safe_json_dumps(context.auxiliary_data, indent=2) if context.auxiliary_data else "{}"
    
    prompt = DEEPSEEK_DIAGNOSIS_PROMPT_TEMPLATE.format(
        alert_info=alert_info_str,
        original_expert_results_json=original_expert_str,
        full_slow_queries_json=slow_queries_str,
        top1_execution_plan_json=exec_plan_str,
        db_config_json=db_config_str,
        server_memory_total=context.server_memory_total,
        auxiliary_data_json=auxiliary_str
    )
    
    if expert_results:
        prompt += f"""

4. 【重要】协作诊断专家结果（多专家并行诊断输出）：
{collaborative_str}
"""
    
    return prompt


def call_deepseek_for_diagnosis(
    context: DiagnosisContext, 
    original_result: Dict[str, Any] = None,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    调用DeepSeek API进行诊断分析
    
    【优化1】提高 max_tokens 到 8192，解决 JSON 截断问题
    【优化1】使用 robust_json_parse 容错解析
    【优化2】增强 Prompt 约束，确保字段完整
    
    @param context: 诊断上下文数据
    @param original_result: 原Tree Search/多专家诊断结果
    @param max_retries: 最大重试次数
    @return: DeepSeek返回的结构化诊断结果
    """
    from server.utils import get_ChatOpenAI, robust_json_parse
    from configs import TEMPERATURE, MAX_TOKENS
    
    prompt = build_deepseek_prompt(context, original_result)
    
    for attempt in range(max_retries + 1):
        try:
            llm = get_ChatOpenAI(
                model_name="deepseek-chat",
                temperature=0.3,
                max_tokens=MAX_TOKENS,
                streaming=False
            )
            
            response = llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            content = content.strip()
            
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            result = robust_json_parse(content, strict=False)
            
            if result is None:
                raise ValueError("JSON 解析失败，LLM 输出可能被截断")
            
            required_fields = ["expert_validation", "integrated_optimization_solutions"]
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"缺少必要字段: {field}")
            
            result = _ensure_solution_fields(result)
            
            logger.info(f"[OK] DeepSeek诊断分析完成，专家校验数: {len(result.get('expert_validation', []))}")
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"[WARN] DeepSeek返回结果JSON解析失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
            if attempt < max_retries:
                time.sleep(1)
                continue
        except Exception as e:
            logger.error(f"[ERROR] DeepSeek调用失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
            if attempt < max_retries:
                time.sleep(2)
                continue
    
    logger.warning("[WARN] DeepSeek调用失败，返回默认增强结果")
    return _generate_fallback_enhancement(original_result)


def _ensure_solution_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    【优化2】确保解决方案字段完整，防止模型"偷懒"跳过字段
    
    @param result: LLM 返回的结果
    @return: 补全字段后的结果
    """
    solutions = result.get("integrated_optimization_solutions", [])
    
    default_solution_template = {
        "action": "待补充",
        "sql": "-- 待生成具体SQL",
        "priority": "中",
        "risk_level": "中风险",
        "expected_effect": "待评估",
        "implementation_details": "请参考专业DBA建议",
        "source_expert": "系统"
    }
    
    ensured_solutions = []
    for sol in solutions:
        ensured = {**default_solution_template, **sol}
        if not ensured.get("implementation_details") or ensured.get("implementation_details") in ["无", "暂无", ""]:
            ensured["implementation_details"] = "请参考专业DBA建议进行实施"
        ensured_solutions.append(ensured)
    
    result["integrated_optimization_solutions"] = ensured_solutions
    return result


def _generate_fallback_enhancement(original_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    【新增】DeepSeek调用失败时的兜底 - 仅做简单格式包装，不改变原结果
    
    @param original_result: 原始诊断结果
    @return: 默认增强结果
    """
    original_causes = original_result.get("root_causes", [])
    
    validations = []
    for i, cause in enumerate(original_causes):
        validations.append({
            "original_cause_index": i,
            "original_cause_type": cause.get("type", "unknown"),
            "validation_result": "需补充验证",
            "validation_evidence": "LLM增强服务暂不可用，保留原专家结论",
            "deepened_analysis": cause.get("description", "")
        })
    
    return {
        "expert_validation": validations,
        "root_cause_relation_analysis": "LLM增强服务暂不可用，未进行关联分析",
        "top_sql_enhanced_analysis": {
            "bottleneck": "需进一步分析",
            "targeted_suggestions": ["参考原专家优化建议"]
        },
        "integrated_optimization_solutions": original_result.get("solutions", []),
        "quick_action_guide": ["参考原专家快速操作指南"]
    }


def _generate_fallback_diagnosis(context: DiagnosisContext) -> Dict[str, Any]:
    """
    DeepSeek调用失败时的兜底诊断结果
    
    @param context: 诊断上下文数据
    @return: 默认诊断结果
    """
    root_cause = "SlowQueries"
    
    if context.auxiliary_data.get("blocked_sessions"):
        root_cause = "LockWait"
    elif context.auxiliary_data.get("idle_transactions"):
        root_cause = "IdleTransaction"
    elif context.auxiliary_data.get("table_bloat"):
        root_cause = "TableBloat"
    
    solutions = []
    
    if context.full_slow_queries:
        solutions.append({
            "action": "慢查询优化",
            "sql": "-- 分析慢查询执行计划\nEXPLAIN ANALYZE <慢查询SQL>;",
            "priority": "高",
            "risk_level": "低风险",
            "expected_effect": "识别查询瓶颈，优化后预计提升30%-50%",
            "implementation_details": "在低峰期执行EXPLAIN ANALYZE，分析扫描方式和索引使用情况",
            "source_expert": "系统兜底"
        })
    
    if context.auxiliary_data.get("table_bloat"):
        solutions.append({
            "action": "表膨胀处理",
            "sql": "-- 清理死元组\nVACUUM ANALYZE <表名>;",
            "priority": "中",
            "risk_level": "低风险",
            "expected_effect": "减少表膨胀，提升查询性能",
            "implementation_details": "死元组比例>20%时建议执行，VACUUM不锁表，可在业务期间执行",
            "source_expert": "系统兜底"
        })
    
    return {
        "expert_validation": [
            {
                "original_cause_index": 0,
                "original_cause_type": root_cause,
                "validation_result": "系统兜底",
                "validation_evidence": "DeepSeek调用失败，使用基础数据分析",
                "deepened_analysis": f"检测到{len(context.full_slow_queries)}条慢查询"
            }
        ],
        "root_cause_relation_analysis": "DeepSeek调用失败，无法分析根因关联",
        "top_sql_enhanced_analysis": {
            "bottleneck": "需要进一步分析执行计划",
            "targeted_suggestions": ["分析TOP慢查询的执行计划", "检查索引覆盖情况"]
        },
        "integrated_optimization_solutions": solutions,
        "quick_action_guide": ["分析TOP慢查询执行计划", "检查索引覆盖情况", "监控数据库性能指标"]
    }


# ==============================================================================
# 第四部分：诊断报告生成与填充 - 硬编码模板 + LLM结果
# 结构部分禁止调用DeepSeek，专业内容部分使用LLM结果
# ==============================================================================

def enhance_diagnosis_result(
    original_result: Dict[str, Any],
    anomaly_info: Dict[str, Any],
    deepseek_result: Dict[str, Any],
    context: DiagnosisContext
) -> Dict[str, Any]:
    """
    【整改后】增强诊断结果 - 融合而非覆盖原专家结果
    
    @param original_result: 原始诊断结果（Tree Search/多专家输出）
    @param anomaly_info: 异常信息
    @param deepseek_result: DeepSeek增强分析结果
    @param context: 诊断上下文数据
    @return: 增强后的诊断结果
    """
    enhanced_result = original_result.copy()
    
    if "anomaly_type" not in enhanced_result:
        validations = deepseek_result.get("expert_validation", [])
        first_valid = next((v for v in validations if v.get("validation_result") == "确认有效"), None)
        if first_valid:
            final_type = normalize_anomaly_type(first_valid.get("original_cause_type", "unknown"))
        else:
            final_type = "unknown"
        
        enhanced_result["anomaly_type"] = final_type
        enhanced_result["anomaly_type_display"] = get_anomaly_display_name(final_type)
        enhanced_result["alert_type"] = final_type
        enhanced_result["alert_severity"] = get_alert_severity(final_type)
    
    original_root_causes = original_result.get("root_causes", [])
    enhanced_root_causes = []
    
    validations = deepseek_result.get("expert_validation", [])
    
    for i, cause in enumerate(original_root_causes):
        enhanced_cause = cause.copy()
        
        validation = next((v for v in validations if v.get("original_cause_index") == i), None)
        
        if validation:
            enhanced_cause["validation"] = {
                "result": validation.get("validation_result"),
                "evidence": validation.get("validation_evidence")
            }
            
            if validation.get("deepened_analysis"):
                enhanced_cause["deepened_analysis"] = validation.get("deepened_analysis")
        
        enhanced_root_causes.append(enhanced_cause)
    
    if deepseek_result.get("root_cause_relation_analysis"):
        enhanced_result["root_cause_relation_analysis"] = deepseek_result.get("root_cause_relation_analysis")
    
    original_solutions = original_result.get("solutions", [])
    integrated_solutions = deepseek_result.get("integrated_optimization_solutions", [])
    
    seen_actions = set()
    final_solutions = []
    
    for sol in integrated_solutions:
        action_key = sol.get("action", "").strip().lower()[:50]
        if action_key and action_key not in seen_actions:
            seen_actions.add(action_key)
            sol["source"] = sol.get("source_expert", "DeepSeek增强")
            final_solutions.append(sol)
    
    for sol in original_solutions:
        action_key = sol.get("action", "").strip().lower()[:50]
        if action_key and action_key not in seen_actions:
            seen_actions.add(action_key)
            final_solutions.append(sol)
    
    enhanced_result["root_causes"] = enhanced_root_causes
    enhanced_result["solutions"] = final_solutions
    
    enhanced_result["quick_action_guide"] = deepseek_result.get("quick_action_guide", [])
    enhanced_result["top_sql_enhanced_analysis"] = deepseek_result.get("top_sql_enhanced_analysis", {})
    
    enhanced_result["diagnosis_context"] = {
        "slow_queries_count": len(context.full_slow_queries),
        "execution_plan_available": context.top1_execution_plan.get("available", False),
        "table_bloat_count": len(context.auxiliary_data.get("table_bloat", [])),
        "idle_transaction_count": len(context.auxiliary_data.get("idle_transactions", [])),
        "blocked_session_count": len(context.auxiliary_data.get("blocked_sessions", [])),
        "collection_errors": context.collection_errors,
        "server_memory_gb": context.server_memory_total,
        "enhancement_mode": "专家结果校验与融合"
    }
    
    enhanced_result["full_slow_queries"] = context.full_slow_queries
    enhanced_result["database_config"] = context.db_config
    
    return enhanced_result


def generate_enhanced_markdown_report(
    enhanced_result: Dict[str, Any],
    context: DiagnosisContext
) -> str:
    """
    生成增强版Markdown诊断报告
    
    @param enhanced_result: 增强后的诊断结果
    @param context: 诊断上下文数据
    @return: Markdown格式的诊断报告
    """
    anomaly_type = enhanced_result.get("anomaly_type", "unknown")
    anomaly_display = enhanced_result.get("anomaly_type_display", "未知异常")
    confidence = enhanced_result.get("confidence", 0.85)
    
    report_lines = []
    
    report_lines.append(f"# PostgreSQL 数据库诊断报告")
    report_lines.append(f"")
    report_lines.append(f"**诊断时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"**异常类型**: {anomaly_display} ({anomaly_type})")
    report_lines.append(f"**置信度**: {confidence * 100:.1f}%")
    report_lines.append(f"")
    
    report_lines.append(f"---")
    report_lines.append(f"")
    
    report_lines.append(f"## 一、诊断概览")
    report_lines.append(f"")
    
    quick_guide = enhanced_result.get("quick_action_guide", [])
    if quick_guide:
        report_lines.append(f"### 快速操作指南")
        report_lines.append(f"")
        for i, guide in enumerate(quick_guide, 1):
            report_lines.append(f"{i}. {guide}")
        report_lines.append(f"")
    
    root_causes = enhanced_result.get("root_causes", [])
    if root_causes:
        report_lines.append(f"## 二、根因分析")
        report_lines.append(f"")
        for i, cause in enumerate(root_causes, 1):
            report_lines.append(f"### 根因 {i}: {cause.get('type', '未知')}")
            report_lines.append(f"")
            report_lines.append(f"**描述**: {cause.get('description', '')}")
            report_lines.append(f"**置信度**: {cause.get('confidence', 0) * 100:.1f}%")
            report_lines.append(f"")
            
            deep_analysis = cause.get("deep_analysis", {})
            if deep_analysis:
                top_sql_analysis = deep_analysis.get("top_sql_analysis", {})
                if top_sql_analysis:
                    report_lines.append(f"#### TOP SQL 精准分析")
                    report_lines.append(f"")
                    bottleneck = top_sql_analysis.get("bottleneck", "")
                    if bottleneck:
                        report_lines.append(f"**性能瓶颈**: {bottleneck}")
                        report_lines.append(f"")
                    
                    suggestions = top_sql_analysis.get("targeted_suggestions", [])
                    if suggestions:
                        report_lines.append(f"**针对性建议**:")
                        report_lines.append(f"")
                        for sug in suggestions:
                            report_lines.append(f"- {sug}")
                        report_lines.append(f"")
    
    slow_queries = context.full_slow_queries
    if slow_queries:
        report_lines.append(f"## 三、慢查询详情")
        report_lines.append(f"")
        report_lines.append(f"| 排名 | 调用次数 | 总耗时(ms) | 平均耗时(ms) | 缓存命中率 |")
        report_lines.append(f"|------|----------|-----------|-------------|-----------|")
        for i, query in enumerate(slow_queries[:5], 1):
            report_lines.append(f"| {i} | {query.get('calls', 0)} | {query.get('total_time', 0):.2f} | {query.get('mean_time', 0):.2f} | {query.get('cache_hit_ratio', 0):.1f}% |")
        report_lines.append(f"")
        
        report_lines.append(f"### 慢查询完整SQL语句")
        report_lines.append(f"")
        for i, query in enumerate(slow_queries[:5], 1):
            full_sql = query.get("query", "")
            report_lines.append(f"#### 慢查询 #{i} (Query ID: {query.get('query_id', 'N/A')})")
            report_lines.append(f"")
            report_lines.append(f"- **调用次数**: {query.get('calls', 0)}")
            report_lines.append(f"- **总耗时**: {query.get('total_time', 0):.2f} ms")
            report_lines.append(f"- **平均耗时**: {query.get('mean_time', 0):.2f} ms")
            report_lines.append(f"- **缓存命中率**: {query.get('cache_hit_ratio', 0):.1f}%")
            report_lines.append(f"")
            report_lines.append(f"**完整SQL语句**:")
            report_lines.append(f"")
            report_lines.append(f"```sql")
            report_lines.append(f"{full_sql}")
            report_lines.append(f"```")
            report_lines.append(f"")
    
    solutions = enhanced_result.get("solutions", [])
    if solutions:
        report_lines.append(f"## 四、详细优化方案")
        report_lines.append(f"")
        for i, sol in enumerate(solutions, 1):
            priority = sol.get("priority", "中")
            risk = sol.get("risk_level", "低风险")
            priority_icon = "🔴" if priority == "高" else "🟡" if priority == "中" else "🟢"
            
            report_lines.append(f"### 方案 {i}: {sol.get('action', '')}")
            report_lines.append(f"")
            report_lines.append(f"- **优先级**: {priority_icon} {priority}")
            report_lines.append(f"- **风险等级**: {risk}")
            report_lines.append(f"- **预期效果**: {sol.get('expected_effect', '待评估')}")
            report_lines.append(f"")
            
            explanation = sol.get("explanation", "")
            if explanation:
                report_lines.append(f"**落地细节**:")
                report_lines.append(f"")
                report_lines.append(f"{explanation}")
                report_lines.append(f"")
            
            sql = sol.get("sql", "")
            if sql and sql != "-- 请根据上述建议执行具体的优化操作":
                report_lines.append(f"**SQL语句**:")
                report_lines.append(f"")
                report_lines.append(f"```sql")
                report_lines.append(f"{sql}")
                report_lines.append(f"```")
                report_lines.append(f"")
    
    auxiliary = context.auxiliary_data
    if auxiliary.get("table_bloat") or auxiliary.get("idle_transactions") or auxiliary.get("blocked_sessions"):
        report_lines.append(f"## 五、辅助诊断数据")
        report_lines.append(f"")
        
        if auxiliary.get("table_bloat"):
            report_lines.append(f"### 表膨胀情况")
            report_lines.append(f"")
            report_lines.append(f"| 表名 | 死元组比例 | 死元组数量 | 表大小 |")
            report_lines.append(f"|------|-----------|-----------|--------|")
            for table in auxiliary["table_bloat"][:5]:
                report_lines.append(f"| {table.get('table', '')} | {table.get('dead_ratio', 0):.1f}% | {table.get('dead_tuples', 0)} | {table.get('size', '')} |")
            report_lines.append(f"")
        
        if auxiliary.get("idle_transactions"):
            report_lines.append(f"### 长时间空闲事务")
            report_lines.append(f"")
            report_lines.append(f"| PID | 用户 | 空闲时长(秒) | 查询语句 |")
            report_lines.append(f"|-----|------|-------------|---------|")
            for tx in auxiliary["idle_transactions"][:5]:
                query_preview = tx.get("query", "")[:50].replace("\n", " ")
                report_lines.append(f"| {tx.get('pid', '')} | {tx.get('user', '')} | {tx.get('idle_seconds', 0)} | `{query_preview}` |")
            report_lines.append(f"")
        
        if auxiliary.get("blocked_sessions"):
            report_lines.append(f"### 阻塞会话")
            report_lines.append(f"")
            report_lines.append(f"| 被阻塞PID | 被阻塞用户 | 阻塞源PID | 阻塞源用户 | 等待时长(秒) |")
            report_lines.append(f"|----------|-----------|----------|-----------|-------------|")
            for session in auxiliary["blocked_sessions"][:5]:
                report_lines.append(f"| {session.get('blocked_pid', '')} | {session.get('blocked_user', '')} | {session.get('blocking_pid', '')} | {session.get('blocking_user', '')} | {session.get('wait_seconds', 0)} |")
            report_lines.append(f"")
    
    report_lines.append(f"## 六、风险提示")
    report_lines.append(f"")
    report_lines.append(f"### 内存参数调整")
    report_lines.append(f"- **shared_buffers**: 推荐为物理内存的25%，需根据服务器实际配置调整")
    report_lines.append(f"- **effective_cache_size**: 推荐为物理内存的50%-75%")
    report_lines.append(f"- **风险**: 修改内存参数需要重启数据库才能生效")
    report_lines.append(f"")
    report_lines.append(f"### 表膨胀处理")
    report_lines.append(f"- **VACUUM**: 低风险，不锁表，可在业务期间执行")
    report_lines.append(f"- **VACUUM FULL**: 高风险，会锁表，仅极端膨胀场景使用")
    report_lines.append(f"- **阈值**: 死元组比例>20%时建议处理")
    report_lines.append(f"")
    report_lines.append(f"### 空闲事务终止")
    report_lines.append(f"- **判断标准**: 空闲时长>30分钟")
    report_lines.append(f"- **风险**: 强制终止会导致事务回滚")
    report_lines.append(f"- **注意**: 执行前必须核对会话信息，确认可以终止")
    report_lines.append(f"")
    
    report_lines.append(f"---")
    report_lines.append(f"")
    report_lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    report_lines.append(f"*诊断引擎: D-Bot Tree Search + DeepSeek*")
    
    return "\n".join(report_lines)


# ==============================================================================
# 第五部分：主入口函数
# ==============================================================================

def run_enhanced_diagnosis(
    anomaly_info: Dict[str, Any],
    original_result: Dict[str, Any]
) -> Tuple[Dict[str, Any], str]:
    """
    【整改后】运行增强诊断流程 - 基于原专家结果做融合
    
    @param anomaly_info: 异常信息
    @param original_result: 原始Tree Search/多专家诊断结果
    @return: (增强后的诊断结果, Markdown报告)
    """
    logger.info(f"[START] 开始专家结果增强流程...")
    
    collector = DiagnosisDataCollector()
    original_root_causes = original_result.get("root_causes", [])
    context = collector.collect_targeted_diagnosis_data(
        anomaly_info,
        original_root_causes=original_root_causes
    )
    
    logger.info(f"[INFO] 定向数据采集完成")
    
    deepseek_result = call_deepseek_for_diagnosis(context, original_result)
    
    logger.info(f"[INFO] DeepSeek增强分析完成")
    
    enhanced_result = enhance_diagnosis_result(
        original_result=original_result,
        anomaly_info=anomaly_info,
        deepseek_result=deepseek_result,
        context=context
    )
    
    markdown_report = generate_enhanced_markdown_report(enhanced_result, context)
    
    logger.info(f"[OK] 专家结果增强流程完成")
    
    return enhanced_result, markdown_report
