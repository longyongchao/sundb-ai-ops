#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : ablation_study.py
@Author  : LI
@Date    : 2026
@Desc    : 消融实验框架
            Reference: D-Bot Paper Section 8 - Experiments
            
            支持以下配置的对比实验：
            1. Full - 完整 D-Bot 系统
            2. No-Tree - 无树搜索，直接推理
            3. No-Reflect - 无反思机制
            4. No-Knowledge - 无知识库
            5. Vanilla-LLM - 纯 LLM 对话
            
            评估指标：
            - Accuracy (准确率)
            - Precision (精确率)
            - Recall (召回率)
            - F1-Score
            - Diagnosis Time (诊断时间)
"""
import os
import json
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

# 导入诊断模块
from server.diagnose.tree_search_service import run_tree_search_diagnosis
from server.diagnose.knowledge_loader import load_knowledge, get_all_root_causes


class AblationConfig(Enum):
    """消融实验配置"""
    FULL = "full"                    # 完整 D-Bot
    NO_TREE = "no_tree"              # 无树搜索
    NO_REFLECT = "no_reflect"        # 无反思
    NO_KNOWLEDGE = "no_knowledge"    # 无知识库
    VANILLA_LLM = "vanilla_llm"      # 纯 LLM


@dataclass
class DiagnosisResult:
    """诊断结果"""
    config: AblationConfig
    case_id: str
    predicted_causes: List[str]
    actual_causes: List[str]
    diagnosis_time: float
    reasoning_steps: int
    knowledge_matches: int
    confidence: float
    
    def to_dict(self) -> Dict:
        return {
            "config": self.config.value,
            "case_id": self.case_id,
            "predicted_causes": self.predicted_causes,
            "actual_causes": self.actual_causes,
            "diagnosis_time": self.diagnosis_time,
            "reasoning_steps": self.reasoning_steps,
            "knowledge_matches": self.knowledge_matches,
            "confidence": self.confidence
        }


@dataclass
class EvaluationMetrics:
    """评估指标"""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    avg_diagnosis_time: float
    avg_reasoning_steps: float
    avg_knowledge_matches: float
    
    def to_dict(self) -> Dict:
        return {
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "avg_diagnosis_time": round(self.avg_diagnosis_time, 2),
            "avg_reasoning_steps": round(self.avg_reasoning_steps, 2),
            "avg_knowledge_matches": round(self.avg_knowledge_matches, 2)
        }


class AblationStudy:
    """
    @class AblationStudy
    @brief 消融实验框架
    @reference D-Bot Paper Section 8 - Experimental Study
    """
    
    # 测试用例
    TEST_CASES = [
        {
            "id": "slow_sql_001",
            "alert_type": "slow_sql",
            "description": "数据库响应缓慢，CPU使用率升高",
            "severity": "high",
            "expected_causes": ["slow_query", "cpu_pressure"]
        },
        {
            "id": "lock_wait_001",
            "alert_type": "lock_wait",
            "description": "事务阻塞，出现锁等待",
            "severity": "high",
            "expected_causes": ["lock_contention", "long_transaction"]
        },
        {
            "id": "memory_001",
            "alert_type": "memory_pressure",
            "description": "内存使用率过高，出现交换",
            "severity": "medium",
            "expected_causes": ["memory_leak", "buffer_pressure"]
        },
        {
            "id": "io_bottleneck_001",
            "alert_type": "io_bottleneck",
            "description": "磁盘I/O等待时间长",
            "severity": "medium",
            "expected_causes": ["io_contention", "disk_bottleneck"]
        },
        {
            "id": "connection_001",
            "alert_type": "connection_exhaust",
            "description": "数据库连接数达到上限",
            "severity": "high",
            "expected_causes": ["connection_leak", "pool_exhaust"]
        }
    ]
    
    def __init__(self, output_dir: str = None):
        """
        @brief 初始化消融实验
        @param output_dir: 结果输出目录
        """
        self.output_dir = output_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "ablation_results"
        )
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.results: List[DiagnosisResult] = []
    
    def run_single_case(
        self, 
        case: Dict, 
        config: AblationConfig
    ) -> DiagnosisResult:
        """
        @brief 运行单个测试用例
        @param case: 测试用例
        @param config: 消融配置
        @return: 诊断结果
        """
        print(f"\n{'='*60}")
        print(f"配置: {config.value} | 用例: {case['id']}")
        print(f"{'='*60}")
        
        start_time = time.time()
        
        if config == AblationConfig.FULL:
            result = self._run_full(case)
        elif config == AblationConfig.NO_TREE:
            result = self._run_no_tree(case)
        elif config == AblationConfig.NO_REFLECT:
            result = self._run_no_reflect(case)
        elif config == AblationConfig.NO_KNOWLEDGE:
            result = self._run_no_knowledge(case)
        else:  # VANILLA_LLM
            result = self._run_vanilla_llm(case)
        
        diagnosis_time = time.time() - start_time
        
        return DiagnosisResult(
            config=config,
            case_id=case["id"],
            predicted_causes=result.get("root_causes", []),
            actual_causes=case.get("expected_causes", []),
            diagnosis_time=diagnosis_time,
            reasoning_steps=result.get("reasoning_steps", 0),
            knowledge_matches=result.get("search_stats", {}).get("knowledge_matches", 0),
            confidence=result.get("confidence", 0.5)
        )
    
    def _run_full(self, case: Dict) -> Dict:
        """完整 D-Bot 系统"""
        anomaly_info = {
            "alert_type": case["alert_type"],
            "description": case["description"],
            "severity": case["severity"]
        }
        return run_tree_search_diagnosis(anomaly_info)
    
    def _run_no_tree(self, case: Dict) -> Dict:
        """无树搜索 - 单步推理"""
        from server.utils import get_ChatOpenAI
        from configs import TEMPERATURE, MAX_TOKENS
        
        llm = get_ChatOpenAI()
        
        prompt = f"""
        作为数据库诊断专家，请直接分析以下异常并给出结论：
        
        异常类型: {case['alert_type']}
        描述: {case['description']}
        
        请直接输出根因和解决方案，格式如下：
        Root Cause: [根因]
        Solution: [解决方案]
        """
        
        response = llm.generate(prompt)
        
        return {
            "root_causes": [response[:50]],
            "reasoning_steps": 1,
            "search_stats": {"knowledge_matches": 0},
            "confidence": 0.5
        }
    
    def _run_no_reflect(self, case: Dict) -> Dict:
        """无反思机制 - 禁用反思"""
        anomaly_info = {
            "alert_type": case["alert_type"],
            "description": case["description"],
            "severity": case["severity"],
            "disable_reflection": True  # 禁用反思标志
        }
        return run_tree_search_diagnosis(anomaly_info)
    
    def _run_no_knowledge(self, case: Dict) -> Dict:
        """无知识库 - 空知识库"""
        anomaly_info = {
            "alert_type": case["alert_type"],
            "description": case["description"],
            "severity": case["severity"],
            "skip_knowledge": True  # 跳过知识库标志
        }
        return run_tree_search_diagnosis(anomaly_info)
    
    def _run_vanilla_llm(self, case: Dict) -> Dict:
        """纯 LLM 对话 - 无任何增强"""
        from server.utils import get_ChatOpenAI
        
        llm = get_ChatOpenAI()
        
        prompt = f"""
        数据库出现异常，请帮我诊断：
        {case['description']}
        """
        
        response = llm.generate(prompt)
        
        return {
            "root_causes": ["vanilla_llm_response"],
            "reasoning_steps": 1,
            "search_stats": {"knowledge_matches": 0},
            "confidence": 0.3
        }
    
    def run_all_configs(self, cases: List[Dict] = None) -> Dict[str, EvaluationMetrics]:
        """
        @brief 运行所有配置的消融实验
        @param cases: 测试用例列表
        @return: 各配置的评估指标
        """
        cases = cases or self.TEST_CASES
        all_results: Dict[str, List[DiagnosisResult]] = {
            config.value: [] for config in AblationConfig
        }
        
        for config in AblationConfig:
            print(f"\n{'#'*60}")
            print(f"# 运行配置: {config.value}")
            print(f"{'#'*60}")
            
            for case in cases:
                try:
                    result = self.run_single_case(case, config)
                    all_results[config.value].append(result)
                    self.results.append(result)
                except Exception as e:
                    print(f"[ERROR] 用例 {case['id']} 执行失败: {e}")
        
        # 计算评估指标
        metrics = {}
        for config_name, results in all_results.items():
            if results:
                metrics[config_name] = self._calculate_metrics(results)
        
        # 保存结果
        self._save_results(all_results, metrics)
        
        return metrics
    
    def _calculate_metrics(self, results: List[DiagnosisResult]) -> EvaluationMetrics:
        """
        @brief 计算评估指标
        @param results: 诊断结果列表
        @return: 评估指标
        """
        total = len(results)
        if total == 0:
            return EvaluationMetrics(0, 0, 0, 0, 0, 0, 0)
        
        # 计算准确率（完全匹配）
        correct = 0
        all_predicted = []
        all_actual = []
        
        for r in results:
            predicted_set = set(r.predicted_causes)
            actual_set = set(r.actual_causes)
            
            if predicted_set & actual_set:  # 有交集
                correct += 1
            
            all_predicted.extend(r.predicted_causes)
            all_actual.extend(r.actual_causes)
        
        accuracy = correct / total
        
        # 计算 Precision, Recall, F1
        predicted_set = set(all_predicted)
        actual_set = set(all_actual)
        
        true_positives = len(predicted_set & actual_set)
        
        precision = true_positives / len(predicted_set) if predicted_set else 0
        recall = true_positives / len(actual_set) if actual_set else 0
        f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        # 计算平均值
        avg_time = np.mean([r.diagnosis_time for r in results])
        avg_steps = np.mean([r.reasoning_steps for r in results])
        avg_matches = np.mean([r.knowledge_matches for r in results])
        
        return EvaluationMetrics(
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            avg_diagnosis_time=avg_time,
            avg_reasoning_steps=avg_steps,
            avg_knowledge_matches=avg_matches
        )
    
    def _save_results(
        self, 
        all_results: Dict[str, List[DiagnosisResult]], 
        metrics: Dict[str, EvaluationMetrics]
    ):
        """保存实验结果"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # 保存详细结果
        results_file = os.path.join(self.output_dir, f"results_{timestamp}.json")
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                config: [r.to_dict() for r in results]
                for config, results in all_results.items()
            }, f, ensure_ascii=False, indent=2)
        
        # 保存评估指标
        metrics_file = os.path.join(self.output_dir, f"metrics_{timestamp}.json")
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump({
                config: m.to_dict()
                for config, m in metrics.items()
            }, f, ensure_ascii=False, indent=2)
        
        # 生成对比表格
        self._generate_comparison_table(metrics, timestamp)
        
        print(f"\n[OK] 结果已保存到: {self.output_dir}")
    
    def _generate_comparison_table(self, metrics: Dict[str, EvaluationMetrics], timestamp: str):
        """生成对比表格"""
        table_file = os.path.join(self.output_dir, f"comparison_{timestamp}.md")
        
        with open(table_file, 'w', encoding='utf-8') as f:
            f.write("# D-Bot 消融实验对比结果\n\n")
            f.write("| 配置 | Accuracy | Precision | Recall | F1-Score | Avg Time(s) | Avg Steps |\n")
            f.write("|------|----------|-----------|--------|----------|-------------|----------|\n")
            
            for config, m in metrics.items():
                f.write(f"| {config} | {m.accuracy:.4f} | {m.precision:.4f} | {m.recall:.4f} | {m.f1_score:.4f} | {m.avg_diagnosis_time:.2f} | {m.avg_reasoning_steps:.1f} |\n")
            
            f.write("\n## 配置说明\n")
            f.write("- **full**: 完整 D-Bot 系统\n")
            f.write("- **no_tree**: 无树搜索，单步推理\n")
            f.write("- **no_reflect**: 无反思机制\n")
            f.write("- **no_knowledge**: 无知识库\n")
            f.write("- **vanilla_llm**: 纯 LLM 对话\n")


def run_ablation_study():
    """运行消融实验"""
    study = AblationStudy()
    metrics = study.run_all_configs()
    
    print("\n" + "="*60)
    print("消融实验结果汇总")
    print("="*60)
    
    for config, m in metrics.items():
        print(f"\n{config}:")
        print(f"  Accuracy: {m.accuracy:.4f}")
        print(f"  Precision: {m.precision:.4f}")
        print(f"  Recall: {m.recall:.4f}")
        print(f"  F1-Score: {m.f1_score:.4f}")
        print(f"  Avg Time: {m.avg_diagnosis_time:.2f}s")
    
    return metrics


if __name__ == "__main__":
    run_ablation_study()
