#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : init_diagnosis_tables.py
@Author  : LI
@Date    : 2026
@Desc    : 诊断相关数据库表初始化脚本
            Reference: D-Bot Paper - Database Schema
            
            创建以下表：
            1. diagnosis_records - 诊断过程记录表
            2. diagnosis_reports - 诊断报告表
            3. diagnosis_tools - 诊断工具表
            4. test_anomaly_cases - 测试异常案例表
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text, create_engine
from server.db.base import Base
from server.db.session import session_scope, FORCE_PG_URL
from server.db.models.diagnosis_model import (
    DiagnosisRecord,
    DiagnosisReport,
    DiagnosisTool,
    TestAnomalyCase
)

PG_ENGINE = create_engine(
    FORCE_PG_URL, 
    pool_pre_ping=True, 
    echo=False,
    connect_args={"client_encoding": "utf8"}
)


def create_diagnosis_tables():
    """
    创建诊断相关的数据库表
    
    @return: 是否成功
    """
    print("=" * 60)
    print("[START] 开始创建诊断相关数据库表...")
    print(f"📍 数据库连接: {FORCE_PG_URL}")
    print("=" * 60)
    
    try:
        Base.metadata.create_all(bind=PG_ENGINE)
        print("[OK] 数据库表创建成功")
        
        with session_scope() as session:
            result = session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('diagnosis_records', 'diagnosis_reports', 'diagnosis_tools', 'test_anomaly_cases')
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            print(f"[INFO] 已创建的表: {tables}")
            
            if len(tables) < 4:
                print("[WARN] 部分表未创建，尝试单独创建...")
                for table_name in ['diagnosis_records', 'diagnosis_reports', 'diagnosis_tools', 'test_anomaly_cases']:
                    if table_name not in tables:
                        print(f"  - 缺少表: {table_name}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 创建数据库表失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def init_default_data():
    """
    初始化默认数据
    
    @return: 是否成功
    """
    print("\n" + "=" * 60)
    print("[START] 开始初始化默认数据...")
    print("=" * 60)
    
    try:
        from server.db.repository.diagnosis_tool_repository import init_default_tools
        from server.db.repository.test_anomaly_case_repository import init_default_test_cases
        
        with session_scope() as session:
            tools_count = init_default_tools.__wrapped__(session)
            print(f"[OK] 初始化诊断工具: {tools_count} 个")
            
            cases_count = init_default_test_cases.__wrapped__(session)
            print(f"[OK] 初始化测试案例: {cases_count} 个")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 初始化默认数据失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_tables():
    """
    验证数据库表结构
    
    @return: 是否成功
    """
    print("\n" + "=" * 60)
    print("[SEARCH] 验证数据库表结构...")
    print("=" * 60)
    
    try:
        with session_scope() as session:
            tables_info = {
                "diagnosis_records": DiagnosisRecord,
                "diagnosis_reports": DiagnosisReport,
                "diagnosis_tools": DiagnosisTool,
                "test_anomaly_cases": TestAnomalyCase
            }
            
            for table_name, model_class in tables_info.items():
                count = session.query(model_class).count()
                print(f"  [STATS] {table_name}: {count} 条记录")
            
            tools = session.query(DiagnosisTool).limit(3).all()
            if tools:
                print("\n  [INFO] 诊断工具示例:")
                for tool in tools:
                    print(f"    - {tool.tool_name}: {tool.tool_display_name}")
            
            cases = session.query(TestAnomalyCase).limit(3).all()
            if cases:
                print("\n  [INFO] 测试案例示例:")
                for case in cases:
                    print(f"    - {case.case_name}: {case.anomaly_type}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 验证失败: {e}")
        return False


def main():
    """
    主函数 - 执行完整的数据库初始化流程
    """
    print("\n" + "🔧 D-Bot 诊断数据库初始化工具 🔧".center(60, "="))
    print()
    
    success = True
    
    if not create_diagnosis_tables():
        success = False
    
    if success and not init_default_data():
        success = False
    
    if success and not verify_tables():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("[OK] 数据库初始化完成！".center(50))
    else:
        print("[ERROR] 数据库初始化失败！".center(50))
    print("=" * 60)
    
    return success


if __name__ == "__main__":
    main()
