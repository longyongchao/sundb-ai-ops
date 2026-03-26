#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : test_anomaly_case_repository.py
@Author  : LI
@Date    : 2026
@Desc    : 测试异常案例数据访问层
            Reference: D-Bot Paper Section 8 - Experiments
"""
import json
from typing import Dict, List, Optional
from datetime import datetime
from server.db.session import with_session
from server.db.models.diagnosis_model import TestAnomalyCase


@with_session
def create_test_case(
    session,
    case_name: str,
    anomaly_type: str,
    anomaly_description: str,
    expected_root_cause: str,
    anomaly_severity: str = "medium",
    anomaly_metadata: Dict = None,
    expected_root_cause_type: str = None,
    expected_solution: str = None,
    setup_sql: str = None,
    cleanup_sql: str = None,
    tags: List[str] = None,
    difficulty_level: str = "medium",
    case_description: str = None
) -> TestAnomalyCase:
    """
    创建测试案例
    
    @param session: 数据库会话
    @param case_name: 案例名称
    @param anomaly_type: 异常类型
    @param anomaly_description: 异常描述
    @param expected_root_cause: 预期根因
    @param anomaly_severity: 严重程度
    @param anomaly_metadata: 异常元数据
    @param expected_root_cause_type: 预期根因类型
    @param expected_solution: 预期解决方案
    @param setup_sql: 环境准备SQL
    @param cleanup_sql: 环境清理SQL
    @param tags: 标签列表
    @param difficulty_level: 难度等级
    @param case_description: 案例描述
    @return: TestAnomalyCase对象
    """
    case = TestAnomalyCase(
        case_name=case_name,
        case_description=case_description,
        anomaly_type=anomaly_type,
        anomaly_description=anomaly_description,
        anomaly_severity=anomaly_severity,
        anomaly_metadata=anomaly_metadata or {},
        expected_root_cause=expected_root_cause,
        expected_root_cause_type=expected_root_cause_type,
        expected_solution=expected_solution,
        setup_sql=setup_sql,
        cleanup_sql=cleanup_sql,
        tags=json.dumps(tags, ensure_ascii=False) if tags else None,
        difficulty_level=difficulty_level,
        create_time=datetime.now()
    )
    session.add(case)
    session.flush()
    return case


@with_session
def get_test_case_by_id(session, case_id: int) -> Optional[TestAnomalyCase]:
    """
    根据ID获取测试案例
    
    @param session: 数据库会话
    @param case_id: 案例ID
    @return: TestAnomalyCase对象
    """
    return session.query(TestAnomalyCase).filter_by(id=case_id).first()


@with_session
def list_test_cases(
    session,
    anomaly_type: str = None,
    difficulty_level: str = None,
    is_active: bool = None,
    tags: List[str] = None,
    limit: int = 20,
    offset: int = 0
) -> List[TestAnomalyCase]:
    """
    查询测试案例列表
    
    @param session: 数据库会话
    @param anomaly_type: 异常类型
    @param difficulty_level: 难度等级
    @param is_active: 是否启用
    @param tags: 标签过滤
    @param limit: 返回数量限制
    @param offset: 偏移量
    @return: TestAnomalyCase列表
    """
    query = session.query(TestAnomalyCase)
    
    if anomaly_type:
        query = query.filter_by(anomaly_type=anomaly_type)
    if difficulty_level:
        query = query.filter_by(difficulty_level=difficulty_level)
    if is_active is not None:
        query = query.filter_by(is_active=is_active)
    
    cases = query.order_by(TestAnomalyCase.create_time.desc()).offset(offset).limit(limit).all()
    
    if tags:
        filtered_cases = []
        for case in cases:
            case_tags = json.loads(case.tags) if case.tags else []
            if any(tag in case_tags for tag in tags):
                filtered_cases.append(case)
        return filtered_cases
    
    return cases


@with_session
def update_test_case(
    session,
    case_id: int,
    **kwargs
) -> Optional[TestAnomalyCase]:
    """
    更新测试案例
    
    @param session: 数据库会话
    @param case_id: 案例ID
    @param kwargs: 更新字段
    @return: 更新后的TestAnomalyCase对象
    """
    case = session.query(TestAnomalyCase).filter_by(id=case_id).first()
    if not case:
        return None
    
    for key, value in kwargs.items():
        if hasattr(case, key):
            if key == "tags" and isinstance(value, list):
                value = json.dumps(value, ensure_ascii=False)
            setattr(case, key, value)
    
    case.update_time = datetime.now()
    session.add(case)
    return case


@with_session
def update_case_statistics(
    session,
    case_id: int,
    is_success: bool,
    diagnosis_time: float
) -> Optional[TestAnomalyCase]:
    """
    更新测试案例统计数据
    
    @param session: 数据库会话
    @param case_id: 案例ID
    @param is_success: 是否诊断成功
    @param diagnosis_time: 诊断耗时
    @return: 更新后的TestAnomalyCase对象
    """
    case = session.query(TestAnomalyCase).filter_by(id=case_id).first()
    if not case:
        return None
    
    case.run_count = (case.run_count or 0) + 1
    if is_success:
        case.success_count = (case.success_count or 0) + 1
    
    total_time = (case.avg_diagnosis_time or 0) * (case.run_count - 1) + diagnosis_time
    case.avg_diagnosis_time = total_time / case.run_count
    
    case.update_time = datetime.now()
    session.add(case)
    return case


@with_session
def delete_test_case(session, case_id: int) -> bool:
    """
    删除测试案例
    
    @param session: 数据库会话
    @param case_id: 案例ID
    @return: 是否成功
    """
    case = session.query(TestAnomalyCase).filter_by(id=case_id).first()
    if case:
        session.delete(case)
        return True
    return False


@with_session
def get_test_statistics(session) -> Dict:
    """
    获取测试统计数据
    
    @param session: 数据库会话
    @return: 统计数据字典
    """
    cases = session.query(TestAnomalyCase).filter_by(is_active=True).all()
    
    total_cases = len(cases)
    total_runs = sum(c.run_count or 0 for c in cases)
    total_success = sum(c.success_count or 0 for c in cases)
    
    overall_accuracy = (total_success / total_runs * 100) if total_runs > 0 else 0
    avg_time = sum(c.avg_diagnosis_time or 0 for c in cases) / total_cases if total_cases > 0 else 0
    
    difficulty_stats = {}
    for c in cases:
        level = c.difficulty_level or "medium"
        if level not in difficulty_stats:
            difficulty_stats[level] = {"count": 0, "runs": 0, "success": 0}
        difficulty_stats[level]["count"] += 1
        difficulty_stats[level]["runs"] += c.run_count or 0
        difficulty_stats[level]["success"] += c.success_count or 0
    
    for level in difficulty_stats:
        runs = difficulty_stats[level]["runs"]
        success = difficulty_stats[level]["success"]
        difficulty_stats[level]["accuracy"] = round(success / runs * 100, 2) if runs > 0 else 0
    
    return {
        "total_cases": total_cases,
        "total_runs": total_runs,
        "total_success": total_success,
        "overall_accuracy": round(overall_accuracy, 2),
        "avg_diagnosis_time": round(avg_time, 2),
        "difficulty_statistics": difficulty_stats
    }


@with_session
def init_default_test_cases(session) -> int:
    """
    初始化默认测试案例（3+典型数据库异常）
    
    @param session: 数据库会话
    @return: 创建的案例数量
    """
    default_cases = [
        {
            "case_name": "索引缺失导致慢查询",
            "case_description": "模拟表缺少索引导致全表扫描的场景",
            "anomaly_type": "Slow Query",
            "anomaly_description": "查询响应时间异常升高，平均查询时间超过5秒，数据库CPU使用率飙升至90%以上",
            "anomaly_severity": "high",
            "expected_root_cause": "missing_index",
            "expected_root_cause_type": "index_issue",
            "expected_solution": "在查询条件列上创建索引，使用CREATE INDEX语句",
            "setup_sql": "CREATE TABLE IF NOT EXISTS test_slow_query (id SERIAL PRIMARY KEY, name VARCHAR(100), created_at TIMESTAMP); INSERT INTO test_slow_query (name, created_at) SELECT 'user_' || i, NOW() FROM generate_series(1, 100000) i;",
            "cleanup_sql": "DROP TABLE IF EXISTS test_slow_query;",
            "tags": ["index", "performance", "cpu"],
            "difficulty_level": "medium"
        },
        {
            "case_name": "CPU使用率异常升高",
            "case_description": "模拟CPU资源耗尽的场景",
            "anomaly_type": "CPU High",
            "anomaly_description": "数据库服务器CPU使用率持续维持在95%以上，系统响应缓慢，存在大量活跃会话",
            "anomaly_severity": "critical",
            "expected_root_cause": "heavy_scan",
            "expected_root_cause_type": "cpu_issue",
            "expected_solution": "优化查询执行计划，减少全表扫描，添加适当索引",
            "setup_sql": "SELECT pg_stat_reset();",
            "cleanup_sql": None,
            "tags": ["cpu", "performance", "critical"],
            "difficulty_level": "hard"
        },
        {
            "case_name": "死锁问题",
            "case_description": "模拟数据库死锁场景",
            "anomaly_type": "Deadlock",
            "anomaly_description": "检测到数据库死锁，多个事务相互等待对方释放锁资源，导致业务阻塞",
            "anomaly_severity": "high",
            "expected_root_cause": "lock_contention",
            "expected_root_cause_type": "lock_issue",
            "expected_solution": "优化事务执行顺序，减少长事务，使用适当的隔离级别",
            "setup_sql": None,
            "cleanup_sql": None,
            "tags": ["lock", "transaction", "deadlock"],
            "difficulty_level": "hard"
        },
        {
            "case_name": "内存使用过高",
            "case_description": "模拟内存泄漏或过度使用的场景",
            "anomaly_type": "Memory High",
            "anomaly_description": "数据库进程内存占用持续增长，已达到系统内存的85%，存在内存泄漏风险",
            "anomaly_severity": "high",
            "expected_root_cause": "memory_leak",
            "expected_root_cause_type": "memory_issue",
            "expected_solution": "检查连接池配置，优化缓冲区设置，排查内存泄漏",
            "setup_sql": None,
            "cleanup_sql": None,
            "tags": ["memory", "performance"],
            "difficulty_level": "medium"
        },
        {
            "case_name": "连接池耗尽",
            "case_description": "模拟数据库连接数耗尽的场景",
            "anomaly_type": "Connection Pool Exhausted",
            "anomaly_description": "数据库连接数达到最大限制，新连接请求被拒绝，应用层出现连接超时错误",
            "anomaly_severity": "high",
            "expected_root_cause": "connection_pool_issue",
            "expected_root_cause_type": "connection_issue",
            "expected_solution": "增加最大连接数配置，优化连接池设置，检查连接泄漏",
            "setup_sql": None,
            "cleanup_sql": None,
            "tags": ["connection", "pool", "configuration"],
            "difficulty_level": "easy"
        }
    ]
    
    created_count = 0
    for case_data in default_cases:
        existing = session.query(TestAnomalyCase).filter_by(case_name=case_data["case_name"]).first()
        if not existing:
            case = TestAnomalyCase(
                case_name=case_data["case_name"],
                case_description=case_data["case_description"],
                anomaly_type=case_data["anomaly_type"],
                anomaly_description=case_data["anomaly_description"],
                anomaly_severity=case_data["anomaly_severity"],
                expected_root_cause=case_data["expected_root_cause"],
                expected_root_cause_type=case_data["expected_root_cause_type"],
                expected_solution=case_data["expected_solution"],
                setup_sql=case_data.get("setup_sql"),
                cleanup_sql=case_data.get("cleanup_sql"),
                tags=json.dumps(case_data["tags"], ensure_ascii=False),
                difficulty_level=case_data["difficulty_level"],
                create_time=datetime.now()
            )
            session.add(case)
            created_count += 1
    
    return created_count
