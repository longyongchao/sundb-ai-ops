#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库诊断工具箱 - PostgreSQL 诊断工具集

本模块实现了针对 PostgreSQL 数据库的诊断工具函数，主要功能包括：
1. 活跃会话分析 - 检测长时间运行的查询和阻塞会话
2. 慢查询挖掘 - 基于 pg_stat_statements 分析慢查询
3. 锁冲突检测 - 识别锁争用和死锁情况
4. 存储空间统计 - 分析表空间使用和膨胀情况
5. 索引建议生成 - 基于查询模式推荐优化索引

设计参考：D-Bot 论文 (VLDB 2024) Section 4.2 - 诊断工具定义
"""
import json
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import re

from server.diagnose.db_connector import DatabaseConnector, DatabaseConfig
from server.utils import get_ChatOpenAI
from configs import TEMPERATURE, MAX_TOKENS


@dataclass
class ActiveSession:
    """
    @class ActiveSession
    @brief 活跃会话信息数据类
    @param pid: 进程 ID
    @param database: 数据库名称
    @param user: 用户名
    @param application_name: 应用名称
    @param client_addr: 客户端地址
    @param client_port: 客户端端口
    @param state: 会话状态
    @param query_start: 查询开始时间
    @param state_change: 状态变更时间
    @param wait_event: 等待事件
    @param wait_event_type: 等待事件类型
    @param query: 查询语句
    @param duration: 执行时长（秒）
    """
    pid: int
    database: str
    user: str
    application_name: str
    client_addr: str
    client_port: int
    state: str
    query_start: datetime
    state_change: datetime
    wait_event: str
    wait_event_type: str
    query: str
    duration: float
    
    def to_dict(self) -> Dict:
        """
        @brief 转换为字典格式
        @return: 字典格式的会话信息
        """
        return {
            "pid": self.pid,
            "database": self.database,
            "user": self.user,
            "application_name": self.application_name,
            "client_addr": self.client_addr,
            "client_port": self.client_port,
            "state": self.state,
            "query_start": self.query_start.isoformat(),
            "state_change": self.state_change.isoformat(),
            "wait_event": self.wait_event,
            "wait_event_type": self.wait_event_type,
            "query": self.query[:200] + "..." if len(self.query) > 200 else self.query,
            "duration": round(self.duration, 2)
        }


@dataclass
class SlowQuery:
    """
    @class SlowQuery
    @brief 慢查询信息数据类
    @param query_id: 查询标识符
    @param query: 查询语句
    @param calls: 调用次数
    @param total_exec_time: 总执行时间（秒）- 【任务二修复】从毫秒转换为秒
    @param mean_exec_time: 平均执行时间（秒）- 【任务二修复】从毫秒转换为秒
    @param rows: 返回行数
    @param cpu_percent: CPU 占用百分比
    @param min_exec_time: 最小执行时间（秒）
    @param max_exec_time: 最大执行时间（秒）
    """
    query_id: int
    query: str
    calls: int
    total_exec_time: float
    mean_exec_time: float
    rows: int
    cpu_percent: float
    min_exec_time: float
    max_exec_time: float
    
    def to_dict(self) -> Dict:
        """
        @brief 转换为字典格式
        @return: 字典格式的慢查询信息
        """
        return {
            "query_id": self.query_id,
            "query": self.query[:200] + "..." if len(self.query) > 200 else self.query,
            "calls": self.calls,
            "total_exec_time": round(self.total_exec_time, 2),
            "mean_exec_time": round(self.mean_exec_time, 2),
            "rows": self.rows,
            "cpu_percent": round(self.cpu_percent, 2),
            "min_exec_time": round(self.min_exec_time, 2),
            "max_exec_time": round(self.max_exec_time, 2),
            "_unit_note": "seconds"
        }


@dataclass
class LockInfo:
    """
    @class LockInfo
    @brief 锁信息数据类
    @param lock_type: 锁类型
    @param relation: 关联表
    @param database: 数据库名称
    @param pid: 进程 ID
    @param mode: 锁模式
    @param granted: 是否已授权
    @param transaction_id: 事务 ID
    @param query: 查询语句
    @param blocking_pid: 阻塞进程 ID
    @param blocking_query: 阻塞查询语句
    """
    lock_type: str
    relation: str
    database: str
    pid: int
    mode: str
    granted: bool
    transaction_id: int
    query: str
    blocking_pid: Optional[int] = None
    blocking_query: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """
        @brief 转换为字典格式
        @return: 字典格式的锁信息
        """
        return {
            "lock_type": self.lock_type,
            "relation": self.relation,
            "database": self.database,
            "pid": self.pid,
            "mode": self.mode,
            "granted": self.granted,
            "transaction_id": self.transaction_id,
            "query": self.query[:200] + "..." if len(self.query) > 200 else self.query,
            "blocking_pid": self.blocking_pid,
            "blocking_query": self.blocking_query[:200] + "..." if self.blocking_query and len(self.blocking_query) > 200 else self.blocking_query
        }


@dataclass
class StorageStats:
    """
    @class StorageStats
    @brief 存储统计信息数据类
    @param schema: 模式名称
    @param table_name: 表名
    @param seq_scan: 顺序扫描次数
    @param idx_scan: 索引扫描次数
    @param seq_tup_read: 顺序扫描读取元组数
    @param idx_tup_fetch: 索引扫描获取元组数
    @param n_live_tup: 活元组数
    @param n_dead_tup: 死元组数
    @param table_size: 表大小
    @param bloat_estimate: 膨胀估算
    @param cache_hit_ratio: 缓存命中率
    """
    schema: str
    table_name: str
    seq_scan: int
    idx_scan: int
    seq_tup_read: int
    idx_tup_fetch: int
    n_live_tup: int
    n_dead_tup: int
    table_size: str
    bloat_estimate: str
    cache_hit_ratio: float
    
    def to_dict(self) -> Dict:
        """
        @brief 转换为字典格式
        @return: 字典格式的存储统计信息
        """
        return {
            "schema": self.schema,
            "table_name": self.table_name,
            "seq_scan": self.seq_scan,
            "idx_scan": self.idx_scan,
            "seq_tup_read": self.seq_tup_read,
            "idx_tup_fetch": self.idx_tup_fetch,
            "n_live_tup": self.n_live_tup,
            "n_dead_tup": self.n_dead_tup,
            "table_size": self.table_size,
            "bloat_estimate": self.bloat_estimate,
            "cache_hit_ratio": round(self.cache_hit_ratio, 2)
        }


class PostgresDiagnosticTools:
    """
    @class PostgresDiagnosticTools
    @brief PostgreSQL 诊断工具箱
    @details 实现数据库性能异常的诊断功能，包括：
             - 活跃会话分析
             - 慢查询挖掘
             - 锁冲突检测
             - 存储统计检查
    @reference D-Bot Paper Section 4.2 - Tool Preparation
    """
    
    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        """
        @brief 初始化诊断工具
        @param db_config: 数据库配置对象（可选）
        """
        self.db_config = db_config
        self.db = DatabaseConnector(db_config)
        self._connected = False
        self._connection_error = ""
        
        self._ensure_connection()
        
    def _ensure_connection(self) -> bool:
        """
        @brief 确保数据库连接可用
        @return: 连接成功返回 True
        """
        if not self._connected:
            self._connected = self.db.connect()
            if not self._connected:
                self._connection_error = self.db.get_error()
        return self._connected
    
    def get_connection_status(self) -> Dict:
        """
        @brief 获取数据库连接状态
        @return: 包含连接状态、错误信息和配置的字典
        """
        return {
            "connected": self._connected,
            "error": self._connection_error if not self._connected else None,
            "config": {
                "host": self.db.config.host,
                "port": self.db.config.port,
                "database": self.db.config.database
            }
        }
    
    def check_active_sessions(self, threshold_seconds: int = 60) -> Tuple[List[ActiveSession], str]:
        """
        @brief 活跃会话诊断
        @param threshold_seconds: 执行时间阈值（秒）
        @return: (会话列表, Markdown 格式表格)
        @reference D-Bot Paper Section 2.1 - Active Session Analysis
        """
        if not self._ensure_connection():
            return [], "[ERROR] 数据库连接失败"
        
        try:
            sql = f"""
            SELECT 
                pid,
                datname as database,
                usename as user,
                application_name,
                client_addr,
                client_port,
                state,
                query_start,
                state_change,
                wait_event,
                wait_event_type,
                query,
                EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - query_start)) as duration
            FROM pg_stat_activity 
            WHERE state = 'active' 
            AND query_start < (CURRENT_TIMESTAMP - INTERVAL '{threshold_seconds} seconds')
            AND pid != pg_backend_pid()
            ORDER BY duration DESC
            """
            
            results = self.db.execute_query(sql)
            sessions = []
            
            for row in results:
                session = ActiveSession(
                    pid=row.get("pid"),
                    database=row.get("database"),
                    user=row.get("user"),
                    application_name=row.get("application_name"),
                    client_addr=row.get("client_addr"),
                    client_port=row.get("client_port"),
                    state=row.get("state"),
                    query_start=row.get("query_start"),
                    state_change=row.get("state_change"),
                    wait_event=row.get("wait_event"),
                    wait_event_type=row.get("wait_event_type"),
                    query=row.get("query"),
                    duration=row.get("duration", 0)
                )
                sessions.append(session)
            
            markdown_table = self._format_active_sessions_table(sessions)
            
            return sessions, markdown_table
            
        except Exception as e:
            error_msg = f"[ERROR] 活跃会话查询失败: {e}"
            print(error_msg)
            return [], error_msg
    
    def get_slow_queries(self, top_n: int = 5, threshold_ms: int = 100) -> Tuple[List[SlowQuery], str]:
        """
        @brief 慢 SQL 挖掘
        @param top_n: 返回前 N 条慢查询
        @param threshold_ms: 慢查询阈值（毫秒）
        @return: (慢查询列表, Markdown 格式表格)
        @reference D-Bot Paper Section 2.1 - Slow Query Execution
        """
        if not self._ensure_connection():
            return [], "[ERROR] 数据库连接失败"
        
        try:
            check_sql = "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements')"
            exists = self.db.execute_scalar(check_sql)
            
            if not exists:
                try:
                    self.db.execute_update("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
                    print("[OK] 已自动启用 pg_stat_statements 扩展")
                    exists = True
                except Exception as e:
                    print(f"[WARN] pg_stat_statements 扩展自动启用失败: {e}")
                    return self._get_slow_queries_from_activity(top_n, threshold_ms)
            
            if exists:
                try:
                    sql = f"""
                    SELECT 
                        queryid as query_id,
                        query,
                        calls,
                        total_exec_time,
                        mean_exec_time,
                        rows,
                        100.0 * total_exec_time / NULLIF(SUM(total_exec_time) OVER(), 0) as cpu_percent,
                        min_exec_time,
                        max_exec_time
                    FROM pg_stat_statements 
                    WHERE mean_exec_time >= {threshold_ms / 1000.0}
                    ORDER BY mean_exec_time DESC
                    LIMIT {top_n}
                    """
                    
                    results = self.db.execute_query(sql)
                    if results:
                        slow_queries = []
                        for row in results:
                            # 【任务二修复】pg_stat_statements 返回的是毫秒，需要转换为秒
                            # 避免出现 "13万秒" 幻觉
                            total_exec_time_ms = row.get("total_exec_time", 0) or 0
                            mean_exec_time_ms = row.get("mean_exec_time", 0) or 0
                            min_exec_time_ms = row.get("min_exec_time", 0) or 0
                            max_exec_time_ms = row.get("max_exec_time", 0) or 0
                            
                            slow_query = SlowQuery(
                                query_id=row.get("query_id"),
                                query=row.get("query"),
                                calls=row.get("calls", 0),
                                total_exec_time=total_exec_time_ms / 1000.0,  # 毫秒 -> 秒
                                mean_exec_time=mean_exec_time_ms / 1000.0,    # 毫秒 -> 秒
                                rows=row.get("rows", 0),
                                cpu_percent=row.get("cpu_percent", 0),
                                min_exec_time=min_exec_time_ms / 1000.0,      # 毫秒 -> 秒
                                max_exec_time=max_exec_time_ms / 1000.0       # 毫秒 -> 秒
                            )
                            slow_queries.append(slow_query)
                        
                        if slow_queries:
                            markdown_table = self._format_slow_queries_table(slow_queries, [])
                            return slow_queries, markdown_table
                except Exception as e:
                    print(f"[WARN] pg_stat_statements 查询失败: {e}")
            
            return self._get_slow_queries_from_activity(top_n, threshold_ms)
            
        except Exception as e:
            error_msg = f"[ERROR] 慢查询查询失败: {e}"
            print(error_msg)
            return [], error_msg
    
    def _get_slow_queries_from_activity(self, top_n: int = 5, threshold_ms: int = 100) -> Tuple[List[SlowQuery], str]:
        """
        @brief 从 pg_stat_activity 获取当前执行的查询（替代方案）
        """
        try:
            sql = f"""
            SELECT 
                pid as query_id,
                query,
                state,
                wait_event_type,
                wait_event,
                EXTRACT(EPOCH FROM (now() - query_start)) as exec_time
            FROM pg_stat_activity 
            WHERE state = 'active' 
              AND query NOT LIKE '%pg_stat%'
              AND query NOT LIKE '%EXPLAIN%'
              AND EXTRACT(EPOCH FROM (now() - query_start)) > {threshold_ms / 1000.0}
            ORDER BY query_start ASC
            LIMIT {top_n}
            """
            
            results = self.db.execute_query(sql)
            slow_queries = []
            
            for row in results:
                slow_query = SlowQuery(
                    query_id=row.get("query_id"),
                    query=row.get("query", ""),
                    calls=1,
                    total_exec_time=row.get("exec_time", 0),
                    mean_exec_time=row.get("exec_time", 0),
                    rows=0,
                    cpu_percent=0,
                    min_exec_time=row.get("exec_time", 0),
                    max_exec_time=row.get("exec_time", 0)
                )
                slow_queries.append(slow_query)
            
            if slow_queries:
                markdown_table = self._format_slow_queries_table(slow_queries, [])
                return slow_queries, markdown_table
            else:
                return [], "[OK] 当前没有执行时间超过阈值的慢查询"
                
        except Exception as e:
            return [], f"[WARN] 无法获取慢查询信息: {e}"
    
    def check_locks(self) -> Tuple[List[LockInfo], str]:
        """
        @brief 锁冲突分析
        @return: (锁信息列表, Markdown 格式表格)
        @reference D-Bot Paper Section 2.1 - Lock Contention Analysis
        """
        if not self._ensure_connection():
            return [], "[ERROR] 数据库连接失败"
        
        try:
            sql = """
            SELECT 
                l.locktype as lock_type,
                COALESCE(c.relname, '') as relation,
                l.database,
                l.pid,
                l.mode,
                l.granted,
                l.virtualtransaction as transaction_id,
                a.query,
                b.pid as blocking_pid,
                b.query as blocking_query
            FROM pg_locks l
            LEFT JOIN pg_class c ON l.relation = c.oid
            JOIN pg_stat_activity a ON l.pid = a.pid
            LEFT JOIN pg_locks bl ON NOT bl.granted AND bl.pid != l.pid 
                AND bl.locktype = l.locktype 
                AND bl.database IS NOT DISTINCT FROM l.database 
                AND bl.relation IS NOT DISTINCT FROM l.relation
            LEFT JOIN pg_stat_activity b ON bl.pid = b.pid
            WHERE l.database IS NOT NULL
            ORDER BY l.granted ASC, l.locktype DESC
            """
            
            results = self.db.execute_query(sql)
            locks = []
            
            for row in results:
                lock_info = LockInfo(
                    lock_type=row.get("lock_type"),
                    relation=row.get("relation"),
                    database=row.get("database"),
                    pid=row.get("pid"),
                    mode=row.get("mode"),
                    granted=row.get("granted"),
                    transaction_id=row.get("transaction_id"),
                    query=row.get("query"),
                    blocking_pid=row.get("blocking_pid"),
                    blocking_query=row.get("blocking_query")
                )
                locks.append(lock_info)
            
            blocking_locks = [lock for lock in locks if not lock.granted and lock.blocking_pid]
            
            markdown_table = self._format_locks_table(locks, blocking_locks)
            
            return locks, markdown_table
            
        except Exception as e:
            error_msg = f"[ERROR] 锁查询失败: {e}"
            print(error_msg)
            return [], error_msg
    
    def check_storage_stats(self) -> Tuple[List[StorageStats], str]:
        """
        @brief 索引与缓存检查
        @return: (存储统计列表, Markdown 格式表格)
        @reference D-Bot Paper Section 2.1 - Storage Statistics
        """
        if not self._ensure_connection():
            return [], "[ERROR] 数据库连接失败"
        
        try:
            table_sql = """
            SELECT 
                schemaname,
                relname as table_name,
                seq_scan,
                idx_scan,
                seq_tup_read,
                idx_tup_fetch,
                n_live_tup,
                n_dead_tup,
                pg_size_pretty(pg_total_relation_size(relid)) as table_size
            FROM pg_stat_user_tables
            ORDER BY n_dead_tup DESC, seq_scan DESC
            """
            
            table_results = self.db.execute_query(table_sql)
            
            cache_sql = """
            SELECT 
                sum(heap_blks_hit) / nullif(sum(heap_blks_hit + heap_blks_read), 0) as cache_hit_ratio
            FROM pg_statio_user_tables
            """
            cache_result = self.db.execute_scalar(cache_sql)
            cache_hit_ratio = cache_result or 0
            
            bloat_sql = """
            SELECT 
                schemaname,
                relname as tablename,
                pg_size_pretty(bloat_size) as bloat_estimate
            FROM (
                SELECT 
                    schemaname,
                    relname,
                    pg_total_relation_size(schemaname||'.'||relname) as bloat_size
                FROM pg_stat_user_tables
                WHERE n_dead_tup > 0
                ORDER BY n_dead_tup DESC
                LIMIT 10
            ) bloat_stats
            """
            bloat_results = self.db.execute_query(bloat_sql)
            
            stats = []
            for row in table_results:
                bloat_info = next((b for b in bloat_results 
                                  if b.get("schemaname") == row.get("schemaname") 
                                  and b.get("tablename") == row.get("table_name")), {})
                
                stat = StorageStats(
                    schema=row.get("schemaname"),
                    table_name=row.get("table_name"),
                    seq_scan=row.get("seq_scan", 0),
                    idx_scan=row.get("idx_scan", 0),
                    seq_tup_read=row.get("seq_tup_read", 0),
                    idx_tup_fetch=row.get("idx_tup_fetch", 0),
                    n_live_tup=row.get("n_live_tup", 0),
                    n_dead_tup=row.get("n_dead_tup", 0),
                    table_size=row.get("table_size"),
                    bloat_estimate=bloat_info.get("bloat_estimate", "无膨胀"),
                    cache_hit_ratio=cache_hit_ratio
                )
                stats.append(stat)
            
            markdown_table = self._format_storage_stats_table(stats)
            
            return stats, markdown_table
            
        except Exception as e:
            error_msg = f"[ERROR] 存储统计查询失败: {e}"
            print(error_msg)
            return [], error_msg
    
    def _get_execution_plan(self, query_id: int) -> Dict:
        """
        @brief 获取查询执行计划
        @param query_id: 查询标识符
        @return: 包含执行计划的字典
        """
        try:
            if not isinstance(query_id, (int, float)):
                try:
                    query_id = int(query_id)
                except (ValueError, TypeError):
                    print(f"[ERROR] 无效的 query_id 类型: {type(query_id)}, 值: {query_id}")
                    return {"query_id": query_id, "execution_plan": [], "error": "Invalid query_id type"}
            
            sql = "SELECT query FROM pg_stat_statements WHERE queryid = %s"
            result = self.db.execute_query(sql, (int(query_id),))
            if result:
                query = result[0].get("query")
                if query:
                    query_clean = query.strip()
                    if query_clean.endswith(';'):
                        query_clean = query_clean[:-1].strip()
                    
                    if '$1' in query_clean or '$2' in query_clean or '$3' in query_clean:
                        print(f"[WARN] 查询包含参数占位符，使用 EXPLAIN (FORMAT JSON) 而非 ANALYZE")
                        db_name = self.db.config.database if hasattr(self.db, 'config') and self.db.config else 'dbgpt_metadata'
                        query_clean = query_clean.replace('$1', f"'{db_name}'")
                        query_clean = query_clean.replace('$2', '0')
                        query_clean = query_clean.replace('$3', '0')
                        for i in range(4, 20):
                            query_clean = query_clean.replace(f'${i}', '0')
                        print(f"📝 已替换参数占位符后的查询: {query_clean[:100]}...")
                    
                    try:
                        explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query_clean}"
                        plan_result = self.db.execute_query(explain_sql)
                        if plan_result:
                            return {
                                "query_id": query_id,
                                "execution_plan": plan_result[0].get("query_plan", [])
                            }
                    except Exception as analyze_error:
                        print(f"[WARN] EXPLAIN ANALYZE 失败: {analyze_error}，尝试使用简化版 EXPLAIN")
                        try:
                            explain_sql = f"EXPLAIN (FORMAT JSON) {query_clean}"
                            plan_result = self.db.execute_query(explain_sql)
                            if plan_result:
                                return {
                                    "query_id": query_id,
                                    "execution_plan": plan_result[0].get("query_plan", []),
                                    "note": "使用简化版 EXPLAIN（无 ANALYZE）"
                                }
                        except Exception as simple_error:
                            print(f"[ERROR] 简化版 EXPLAIN 也失败: {simple_error}")
                            return {
                                "query_id": query_id,
                                "execution_plan": [],
                                "error": f"无法获取执行计划: {str(simple_error)}"
                            }
        except Exception as e:
            print(f"[ERROR] 获取执行计划失败: {e}")
        return {"query_id": query_id, "execution_plan": []}
    
    def _format_active_sessions_table(self, sessions: List[ActiveSession]) -> str:
        """
        @brief 格式化活跃会话表格
        @param sessions: 活跃会话列表
        @return: Markdown 格式表格字符串
        """
        if not sessions:
            return "[SEARCH] 未发现长时间运行的活跃会话"
        
        markdown = "## [STATS] 长时间运行的活跃会话\n\n"
        markdown += "| PID | 数据库 | 用户 | 应用 | 状态 | 等待事件 | 持续时间(s) | 查询 |\n"
        markdown += "|-----|--------|------|------|------|----------|-------------|------|\n"
        
        for session in sessions[:10]:
            markdown += f"| {session.pid} | {session.database} | {session.user} | {session.application_name[:20]} | {session.state} | {session.wait_event or '无'} | {session.duration:.1f} | {session.query[:50]}... |\n"
        
        if sessions:
            avg_duration = sum(s.duration for s in sessions) / len(sessions)
            markdown += f"\n📈 **分析**: 发现 {len(sessions)} 个长时间运行的会话，平均持续时间 {avg_duration:.1f}s\n"
            
            wait_events = [s.wait_event for s in sessions if s.wait_event]
            if wait_events:
                common_waits = set(wait_events)
                markdown += f"[WARN] **等待事件**: {', '.join(common_waits)}\n"
            
            markdown += f"💡 **建议**: 检查这些查询是否可以优化或终止\n"
        
        return markdown
    
    def _format_slow_queries_table(self, slow_queries: List[SlowQuery], execution_plans: List[Dict]) -> str:
        """
        @brief 格式化慢查询表格
        @param slow_queries: 慢查询列表
        @param execution_plans: 执行计划列表
        @return: Markdown 格式表格字符串
        """
        if not slow_queries:
            return "[SEARCH] 未发现慢查询"
        
        markdown = "## 🐌 慢查询统计\n\n"
        markdown += "| Query ID | 调用次数 | 总执行时间(s) | 平均时间(ms) | CPU占比 | 行数 | 查询 |\n"
        markdown += "|----------|----------|---------------|--------------|---------|------|------|\n"
        
        for query in slow_queries:
            markdown += f"| {query.query_id} | {query.calls} | {query.total_exec_time:.2f} | {query.mean_exec_time:.2f} | {query.cpu_percent:.1f}% | {query.rows} | {query.query[:50]}... |\n"
        
        if execution_plans:
            markdown += "\n### [INFO] 执行计划分析\n\n"
            for plan in execution_plans:
                plan_data = plan.get("execution_plan", [])
                if plan_data:
                    plan_text = json.dumps(plan_data, indent=2, ensure_ascii=False)
                    markdown += f"**Query ID {plan['query_id']} 执行计划**:\n"
                    markdown += f"```json\n{plan_text[:500]}...\n```\n"
        
        if slow_queries:
            total_calls = sum(q.calls for q in slow_queries)
            total_time = sum(q.total_exec_time for q in slow_queries)
            markdown += f"\n📈 **分析**: 共发现 {len(slow_queries)} 条慢查询，总调用次数 {total_calls}，总耗时 {total_time:.2f}s\n"
            markdown += f"💡 **建议**: 重点关注平均执行时间超过 100ms 的查询\n"
        
        return markdown
    
    def _format_locks_table(self, locks: List[LockInfo], blocking_locks: List[LockInfo]) -> str:
        """
        @brief 格式化锁信息表格
        @param locks: 锁信息列表
        @param blocking_locks: 阻塞锁列表
        @return: Markdown 格式表格字符串
        """
        if not locks:
            return "[SEARCH] 未发现锁冲突"
        
        markdown = "## 🔒 锁冲突分析\n\n"
        
        if blocking_locks:
            markdown += "### [WARN] 阻塞锁 (需要关注)\n\n"
            markdown += "| 阻塞者 PID | 受害者 PID | 锁类型 | 关系 | 模式 | 阻塞查询 |\n"
            markdown += "|------------|------------|--------|------|------|----------|\n"
            
            for lock in blocking_locks[:10]:
                markdown += f"| {lock.blocking_pid} | {lock.pid} | {lock.lock_type} | {lock.relation} | {lock.mode} | {lock.query[:50]}... |\n"
        else:
            markdown += "[OK] 未发现阻塞锁\n\n"
        
        granted_count = sum(1 for lock in locks if lock.granted)
        waiting_count = sum(1 for lock in locks if not lock.granted)
        
        markdown += f"\n### [STATS] 锁统计\n"
        markdown += f"- 总锁数: {len(locks)}\n"
        markdown += f"- 已授权锁: {granted_count}\n"
        markdown += f"- 等待锁: {waiting_count}\n"
        
        if waiting_count > 0:
            markdown += f"\n[WARN] **警告**: 发现 {waiting_count} 个等待锁，可能存在锁竞争\n"
            markdown += f"💡 **建议**: 检查长时间运行的查询并考虑优化\n"
        
        return markdown
    
    def _format_storage_stats_table(self, stats: List[StorageStats]) -> str:
        """
        @brief 格式化存储统计表格
        @param stats: 存储统计列表
        @return: Markdown 格式表格字符串
        """
        if not stats:
            return "[SEARCH] 未发现表统计信息"
        
        markdown = "## 🗄️ 存储统计信息\n\n"
        markdown += "| 模式 | 表名 | 顺序扫描 | 索引扫描 | 活元组 | 死元组 | 表大小 | 缓存命中率 |\n"
        markdown += "|------|------|----------|----------|--------|--------|--------|------------|\n"
        
        for stat in stats[:20]:
            total_scans = stat.seq_scan + stat.idx_scan
            seq_ratio = (stat.seq_scan / total_scans * 100) if total_scans > 0 else 0
            idx_ratio = (stat.idx_scan / total_scans * 100) if total_scans > 0 else 0
            
            markdown += f"| {stat.schema} | {stat.table_name} | {stat.seq_scan} ({seq_ratio:.1f}%) | {stat.idx_scan} ({idx_ratio:.1f}%) | {stat.n_live_tup} | {stat.n_dead_tup} | {stat.table_size} | {stat.cache_hit_ratio:.1f}% |\n"
        
        if stats:
            high_dead_tables = [s for s in stats if s.n_dead_tup > s.n_live_tup * 0.1]
            high_seq_tables = [s for s in stats if s.seq_scan > s.idx_scan * 2]
            low_cache_tables = [s for s in stats if s.cache_hit_ratio < 80]
            
            markdown += f"\n📈 **分析**:\n"
            if high_dead_tables:
                markdown += f"- 死元组过多的表: {len(high_dead_tables)} 个\n"
            if high_seq_tables:
                markdown += f"- 顺序扫描过多的表: {len(high_seq_tables)} 个\n"
            if low_cache_tables:
                markdown += f"- 缓存命中率低的表: {len(low_cache_tables)} 个\n"
            
            markdown += f"\n💡 **建议**:\n"
            if high_dead_tables:
                markdown += f"- 对 {len(high_dead_tables)} 个高死元组表执行 VACUUM\n"
            if high_seq_tables:
                markdown += f"- 为 {len(high_seq_tables)} 个高顺序扫描表添加索引\n"
            if low_cache_tables:
                markdown += f"- 检查 {len(low_cache_tables)} 个低缓存命中表的工作内存设置\n"
        
        return markdown


postgres_tools = PostgresDiagnosticTools()


def check_active_sessions(threshold_seconds: int = 60) -> Tuple[List[Dict], str]:
    """
    @brief 检查活跃会话
    @param threshold_seconds: 执行时间阈值（秒）
    @return: (会话字典列表, Markdown 表格)
    """
    sessions, markdown = postgres_tools.check_active_sessions(threshold_seconds)
    return [session.to_dict() for session in sessions], markdown


def get_slow_queries(top_n: int = 5, threshold_ms: int = 100) -> Tuple[List[Dict], str]:
    """
    @brief 获取慢查询
    @param top_n: 返回前 N 条
    @param threshold_ms: 慢查询阈值（毫秒）
    @return: (慢查询字典列表, Markdown 表格)
    """
    slow_queries, markdown = postgres_tools.get_slow_queries(top_n, threshold_ms)
    return [query.to_dict() for query in slow_queries], markdown


def check_locks() -> Tuple[List[Dict], str]:
    """
    @brief 检查锁冲突
    @return: (锁信息字典列表, Markdown 表格)
    """
    locks, markdown = postgres_tools.check_locks()
    return [lock.to_dict() for lock in locks], markdown


def check_storage_stats() -> Tuple[List[Dict], str]:
    """
    @brief 检查存储统计
    @return: (存储统计字典列表, Markdown 表格)
    """
    stats, markdown = postgres_tools.check_storage_stats()
    return [stat.to_dict() for stat in stats], markdown


def get_database_status() -> Dict:
    """
    @brief 获取数据库状态
    @return: 数据库连接状态字典
    """
    return postgres_tools.get_connection_status()


def test_postgres_tools():
    """
    @brief 测试 PostgreSQL 诊断工具
    """
    print("🧪 测试 PostgreSQL 诊断工具...")
    
    status = get_database_status()
    print(f"🔌 连接状态: {status}")
    
    print("\n[STATS] 测试活跃会话诊断...")
    sessions, markdown = check_active_sessions(30)
    print(markdown)
    
    print("\n🐌 测试慢查询挖掘...")
    slow_queries, markdown = get_slow_queries(3, 50)
    print(markdown)
