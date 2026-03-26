#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : testcase_api.py
@Author  : LI
@Date    : 2026
@Desc    : 诊断测试文件库 API
            提供测试用例的查询、解析、诊断功能
"""

import os
import json
import glob
from typing import List, Dict, Any, Optional
from fastapi import Body
from pydantic import BaseModel

from server.utils import BaseResponse, ListResponse


TESTCASE_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "diagnostic_test_cases")


class TestCaseInfo(BaseModel):
    """测试用例简要信息"""
    case_id: str
    case_name: str
    category: str
    difficulty: str
    alert_type: str
    severity: str
    description: str


class TestCaseDetail(BaseModel):
    """测试用例详细信息"""
    case_id: str
    case_name: str
    case_description: str
    category: str
    difficulty: str
    alert_type: str
    severity: str
    start_time: str
    end_time: str
    start_timestamp: str
    end_timestamp: str
    metrics: Dict[str, Any]
    alerts: List[Dict[str, Any]]
    labels: List[str]
    expected_root_causes: List[Dict[str, Any]]
    expected_solutions: List[Dict[str, Any]]
    diagnosis_hints: Optional[Dict[str, Any]] = None


class CategoryInfo(BaseModel):
    """场景分类信息"""
    category_id: str
    category_name: str
    description: str
    case_count: int


CATEGORY_INFO = {
    "01_cpu_high": {
        "category_name": "CPU 高负载场景",
        "description": "CPU 使用率持续过高，常见于写入密集型或计算密集型业务"
    },
    "02_slow_queries": {
        "category_name": "慢查询场景",
        "description": "查询执行时间过长，常见于缺少索引或查询优化不足"
    },
    "03_lock_contention": {
        "category_name": "锁竞争场景",
        "description": "事务锁竞争导致阻塞或死锁，常见于高并发更新场景"
    },
    "04_memory_high": {
        "category_name": "内存高使用场景",
        "description": "内存使用过高，常见于排序、哈希操作或连接数过多"
    },
    "05_io_bottleneck": {
        "category_name": "IO 瓶颈场景",
        "description": "磁盘 I/O 成为性能瓶颈，常见于检查点或 WAL 写入问题"
    },
    "06_mixed_scenarios": {
        "category_name": "混合场景",
        "description": "多种异常同时发生，需要综合分析"
    },
    "07_edge_cases": {
        "category_name": "边界场景",
        "description": "特殊或极端情况，用于验证诊断鲁棒性"
    }
}


def get_testcase_list() -> ListResponse:
    """
    获取所有测试用例列表
    
    @return: 测试用例列表
    """
    testcases = []
    
    if not os.path.exists(TESTCASE_BASE_DIR):
        return ListResponse(code=200, msg="Success", data=[])
    
    for category_dir in sorted(os.listdir(TESTCASE_BASE_DIR)):
        category_path = os.path.join(TESTCASE_BASE_DIR, category_dir)
        if not os.path.isdir(category_path):
            continue
            
        json_files = glob.glob(os.path.join(category_path, "case_*.json"))
        for json_file in sorted(json_files):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    testcases.append(TestCaseInfo(
                        case_id=data.get("case_id", ""),
                        case_name=data.get("case_name", ""),
                        category=data.get("category", ""),
                        difficulty=data.get("difficulty", ""),
                        alert_type=data.get("alert_type", ""),
                        severity=data.get("severity", ""),
                        description=data.get("case_description", "")[:100] + "..."
                    ))
            except Exception as e:
                print(f"Error loading testcase {json_file}: {e}")
                continue
    
    return ListResponse(code=200, msg="Success", data=[t.dict() for t in testcases])


def get_testcase_categories() -> BaseResponse:
    """
    获取测试用例场景分类列表
    
    @return: 场景分类列表
    """
    categories = []
    
    if not os.path.exists(TESTCASE_BASE_DIR):
        return BaseResponse(code=200, msg="Success", data=[])
    
    for category_id in sorted(os.listdir(TESTCASE_BASE_DIR)):
        category_path = os.path.join(TESTCASE_BASE_DIR, category_id)
        if not os.path.isdir(category_path):
            continue
        
        json_files = glob.glob(os.path.join(category_path, "case_*.json"))
        case_count = len(json_files)
        
        info = CATEGORY_INFO.get(category_id, {
            "category_name": category_id,
            "description": ""
        })
        
        categories.append(CategoryInfo(
            category_id=category_id,
            category_name=info["category_name"],
            description=info["description"],
            case_count=case_count
        ))
    
    return BaseResponse(code=200, msg="Success", data=[c.dict() for c in categories])


def get_testcases_by_category(category_id: str) -> ListResponse:
    """
    获取指定分类下的测试用例列表
    
    @param category_id: 分类ID
    @return: 测试用例列表
    """
    testcases = []
    category_path = os.path.join(TESTCASE_BASE_DIR, category_id)
    
    if not os.path.exists(category_path):
        return ListResponse(code=404, msg=f"Category not found: {category_id}", data=[])
    
    json_files = glob.glob(os.path.join(category_path, "case_*.json"))
    for json_file in sorted(json_files):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                testcases.append(TestCaseInfo(
                    case_id=data.get("case_id", ""),
                    case_name=data.get("case_name", ""),
                    category=data.get("category", ""),
                    difficulty=data.get("difficulty", ""),
                    alert_type=data.get("alert_type", ""),
                    severity=data.get("severity", ""),
                    description=data.get("case_description", "")
                ))
        except Exception as e:
            print(f"Error loading testcase {json_file}: {e}")
            continue
    
    return ListResponse(code=200, msg="Success", data=[t.dict() for t in testcases])


def get_testcase_detail(case_id: str) -> BaseResponse:
    """
    获取测试用例详细信息
    
    @param case_id: 用例ID
    @return: 测试用例详情
    """
    if not os.path.exists(TESTCASE_BASE_DIR):
        return BaseResponse(code=404, msg="Testcase directory not found", data=None)
    
    for category_dir in os.listdir(TESTCASE_BASE_DIR):
        category_path = os.path.join(TESTCASE_BASE_DIR, category_dir)
        if not os.path.isdir(category_path):
            continue
        
        json_file = os.path.join(category_path, f"{case_id}.json")
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return BaseResponse(code=200, msg="Success", data=data)
            except Exception as e:
                return BaseResponse(code=500, msg=f"Error loading testcase: {e}", data=None)
    
    return BaseResponse(code=404, msg=f"Testcase not found: {case_id}", data=None)


def get_testcase_file_path(case_id: str) -> Optional[str]:
    """
    获取测试用例文件路径
    
    @param case_id: 用例ID
    @return: 文件路径或None
    """
    if not os.path.exists(TESTCASE_BASE_DIR):
        return None
    
    for category_dir in os.listdir(TESTCASE_BASE_DIR):
        category_path = os.path.join(TESTCASE_BASE_DIR, category_dir)
        if not os.path.isdir(category_path):
            continue
        
        json_file = os.path.join(category_path, f"{case_id}.json")
        if os.path.exists(json_file):
            return json_file
    
    return None


def load_testcase_data(case_id: str) -> Optional[Dict[str, Any]]:
    """
    加载测试用例数据
    
    @param case_id: 用例ID
    @return: 测试用例数据或None
    """
    file_path = get_testcase_file_path(case_id)
    if not file_path:
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading testcase {case_id}: {e}")
        return None


def get_testcase_statistics() -> BaseResponse:
    """
    获取测试用例统计信息
    
    @return: 统计信息
    """
    total_count = 0
    category_counts = {}
    difficulty_counts = {"easy": 0, "medium": 0, "hard": 0}
    
    if not os.path.exists(TESTCASE_BASE_DIR):
        return BaseResponse(code=200, msg="Success", data={
            "total_count": 0,
            "category_counts": {},
            "difficulty_counts": difficulty_counts
        })
    
    for category_dir in sorted(os.listdir(TESTCASE_BASE_DIR)):
        category_path = os.path.join(TESTCASE_BASE_DIR, category_dir)
        if not os.path.isdir(category_path):
            continue
        
        json_files = glob.glob(os.path.join(category_path, "case_*.json"))
        count = len(json_files)
        category_counts[category_dir] = count
        total_count += count
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    difficulty = data.get("difficulty", "medium").lower()
                    if difficulty in difficulty_counts:
                        difficulty_counts[difficulty] += 1
            except:
                continue
    
    return BaseResponse(code=200, msg="Success", data={
        "total_count": total_count,
        "category_counts": category_counts,
        "difficulty_counts": difficulty_counts
    })
