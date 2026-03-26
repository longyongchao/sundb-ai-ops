#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : consistency_checker.py
@Author  : LI
@Date    : 2026
@Desc    : 一致性防火墙模块 - 解决"推理正确但结论错误"的致命缺陷
           Reference: D-Bot Paper Section 6.3 - Consistency Review
           
           核心功能：
           1. 检测推理链与结论的逻辑矛盾
           2. 强制回滚幻觉结论
           3. 记录幻觉拦截统计
"""
import re
import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyCheckResult:
    """一致性检查结果"""
    is_consistent: bool
    has_contradiction: bool
    contradiction_type: str
    original_conclusion: str
    corrected_conclusion: str
    confidence_adjustment: float
    reasoning_evidence: List[str]
    intervention_type: str


class ConsistencyFirewall:
    """
    @class ConsistencyFirewall
    @brief 一致性防火墙 - 防止"推理正确但结论错误"
    @reference D-Bot Paper Section 6.3 - Logic Consistency Review
    
    解决的核心问题：
    - 推理链发现"环境不匹配"，但结论却报告"发现10条慢查询"
    - 推理链发现"数据异常"，但结论却给出高置信度
    """
    
    ENVIRONMENT_MISMATCH_SIGNALS = [
        "wrong instance",
        "mismatch",
        "terminate analysis",
        "empty data",
        "no data",
        "环境不匹配",
        "实例错误",
        "连接错误",
        "数据为空",
        "无数据",
        "终止分析",
        "无法获取",
        "严重矛盾",
        "数据矛盾",
        "规格过小",
        "不符合特征",
        "强烈建议终止",
        "停止分析",
        "连接到了错误",
        "实例规格",
        "最大表仅",
        "与描述不符"
    ]
    
    DATA_ANOMALY_SIGNALS = [
        "abnormal",
        "unexpected",
        "contradiction",
        "inconsistent",
        "异常",
        "矛盾",
        "不一致",
        "意外",
        "不符合预期"
    ]
    
    HALLUCINATION_PATTERNS = [
        r"发现\s*\d+\s*条慢查询",
        r"总执行时间\s*[\d.]+\s*s",
        r"CPU使用率\s*[\d.]+%",
        r"发现\s*\d+\s*个阻塞",
        r"TOP\s*\d+\s*SQL"
    ]
    
    def __init__(self):
        self.intervention_count = 0
        self.intervention_log: List[Dict] = []
    
    def check_reasoning_conclusion_consistency(
        self,
        reasoning_steps: List[Dict],
        root_causes: List[Dict],
        solutions: List[Dict],
        anomaly_info: Dict = None
    ) -> ConsistencyCheckResult:
        """
        @brief 检查推理链与结论的一致性
        @param reasoning_steps: 推理步骤列表
        @param root_causes: 提取的根因列表
        @param solutions: 解决方案列表
        @param anomaly_info: 异常信息
        @return: ConsistencyCheckResult 检查结果
        """
        if not reasoning_steps:
            return ConsistencyCheckResult(
                is_consistent=True,
                has_contradiction=False,
                contradiction_type="none",
                original_conclusion="",
                corrected_conclusion="",
                confidence_adjustment=0.0,
                reasoning_evidence=[],
                intervention_type="none"
            )
        
        last_step = reasoning_steps[-1] if reasoning_steps else {}
        last_thought = self._extract_thought(last_step)
        last_observation = self._extract_observation(last_step)
        
        all_thoughts = " ".join([
            self._extract_thought(step) for step in reasoning_steps[-3:]
        ]).lower()
        all_observations = " ".join([
            self._extract_observation(step) for step in reasoning_steps[-3:]
        ]).lower()
        
        combined_text = f"{last_thought} {last_observation} {all_thoughts} {all_observations}"
        
        env_mismatch_detected = any(
            signal in combined_text for signal in self.ENVIRONMENT_MISMATCH_SIGNALS
        )
        
        data_anomaly_detected = any(
            signal in combined_text for signal in self.DATA_ANOMALY_SIGNALS
        )
        
        has_contradiction = env_mismatch_detected or data_anomaly_detected
        
        if not has_contradiction:
            return ConsistencyCheckResult(
                is_consistent=True,
                has_contradiction=False,
                contradiction_type="none",
                original_conclusion="",
                corrected_conclusion="",
                confidence_adjustment=0.0,
                reasoning_evidence=[last_thought, last_observation],
                intervention_type="none"
            )
        
        contradiction_type = "environment_mismatch" if env_mismatch_detected else "data_anomaly"
        
        root_cause_text = " ".join([
            rc.get("description", "") for rc in root_causes
        ]).lower()
        
        has_hallucination = any(
            re.search(pattern, root_cause_text, re.IGNORECASE)
            for pattern in self.HALLUCINATION_PATTERNS
        )
        
        high_confidence = any(
            rc.get("confidence", 0) > 0.7 for rc in root_causes
        )
        
        is_contradiction = has_hallucination and high_confidence
        
        if not is_contradiction:
            return ConsistencyCheckResult(
                is_consistent=True,
                has_contradiction=False,
                contradiction_type=contradiction_type,
                original_conclusion=root_cause_text,
                corrected_conclusion="",
                confidence_adjustment=0.0,
                reasoning_evidence=[last_thought, last_observation],
                intervention_type="warning_only"
            )
        
        original_conclusion = root_cause_text
        corrected_conclusion = self._generate_corrected_conclusion(
            contradiction_type,
            last_thought,
            last_observation,
            anomaly_info
        )
        
        self._log_intervention(
            contradiction_type,
            original_conclusion,
            corrected_conclusion,
            reasoning_steps
        )
        
        return ConsistencyCheckResult(
            is_consistent=False,
            has_contradiction=True,
            contradiction_type=contradiction_type,
            original_conclusion=original_conclusion,
            corrected_conclusion=corrected_conclusion,
            confidence_adjustment=1.0,
            reasoning_evidence=[last_thought, last_observation],
            intervention_type="force_override"
        )
    
    def _extract_thought(self, step: Dict) -> str:
        """提取推理步骤中的思考内容"""
        if isinstance(step, dict):
            return step.get("thought", "") or step.get("Thought", "") or ""
        return str(step)
    
    def _extract_observation(self, step: Dict) -> str:
        """提取推理步骤中的观察结果"""
        if isinstance(step, dict):
            return step.get("observation", "") or step.get("Observation", "") or ""
        return str(step)
    
    def _generate_corrected_conclusion(
        self,
        contradiction_type: str,
        last_thought: str,
        last_observation: str,
        anomaly_info: Dict = None
    ) -> str:
        """生成修正后的结论"""
        if contradiction_type == "environment_mismatch":
            return (
                "诊断中止：检测到诊断环境与问题描述存在严重逻辑矛盾。"
                "推理链显示数据库实例规格与异常描述不符（如实例过小、数据量异常），"
                "建议先验证数据库连接配置和实例信息。"
            )
        else:
            return (
                "诊断中止：检测到数据异常或逻辑矛盾。"
                "推理链显示获取的数据与预期不符，"
                "建议检查数据源和诊断环境配置。"
            )
    
    def _log_intervention(
        self,
        contradiction_type: str,
        original: str,
        corrected: str,
        reasoning_steps: List[Dict]
    ):
        """记录干预日志"""
        self.intervention_count += 1
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "intervention_id": self.intervention_count,
            "contradiction_type": contradiction_type,
            "original_conclusion": original[:200],
            "corrected_conclusion": corrected[:200],
            "reasoning_steps_count": len(reasoning_steps)
        }
        self.intervention_log.append(log_entry)
        
        logger.warning(f"[一致性防火墙] 检测到逻辑矛盾并已拦截!")
        logger.warning(f"  - 矛盾类型: {contradiction_type}")
        logger.warning(f"  - 原结论: {original[:100]}...")
        logger.warning(f"  - 修正后: {corrected[:100]}...")
    
    def apply_correction(
        self,
        result: ConsistencyCheckResult,
        root_causes: List[Dict],
        solutions: List[Dict],
        is_simulation: bool = True
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        @brief 应用修正到根因和解决方案
        @param result: 一致性检查结果
        @param root_causes: 原始根因列表
        @param solutions: 原始解决方案列表
        @param is_simulation: 是否为模拟模式（默认True，模拟模式下跳过拦截）
        @return: 修正后的 (root_causes, solutions)
        """
        if is_simulation:
            logger.info("[一致性防火墙] 模拟模式已启用，跳过环境一致性拦截")
            return root_causes, solutions
        
        if result.intervention_type != "force_override":
            return root_causes, solutions
        
        corrected_root_cause = {
            "type": "Critical Environment Mismatch",
            "description": result.corrected_conclusion,
            "description_en": result.corrected_conclusion,
            "confidence": 1.0,
            "impact": "诊断环境与问题描述不匹配，无法得出有效结论",
            "impact_en": "Diagnosis environment mismatch with problem description",
            "evidence": result.reasoning_evidence,
            "evidence_data": [],
            "is_corrected": True,
            "correction_reason": result.contradiction_type
        }
        
        corrected_solution = {
            "action": "验证诊断环境",
            "action_en": "Verify Diagnosis Environment",
            "explanation": (
                "推理链检测到环境不匹配信号，建议：\n"
                "1. 检查数据库连接配置是否正确\n"
                "2. 验证是否连接到了正确的数据库实例\n"
                "3. 确认实例规格与业务描述是否一致\n"
                "4. 检查是否存在读写分离导致的数据不一致"
            ),
            "explanation_en": "Reasoning chain detected environment mismatch signals",
            "priority": "high",
            "sql": "-- 验证数据库实例信息\nSELECT version();\nSELECT current_database();\nSELECT pg_database_size(current_database());",
            "source": "一致性防火墙自动修正",
            "is_corrected": True
        }
        
        return [corrected_root_cause], [corrected_solution]
    
    def get_intervention_stats(self) -> Dict:
        """获取干预统计"""
        return {
            "total_interventions": self.intervention_count,
            "intervention_log": self.intervention_log[-10:],
            "intervention_types": {
                "environment_mismatch": sum(
                    1 for log in self.intervention_log 
                    if log["contradiction_type"] == "environment_mismatch"
                ),
                "data_anomaly": sum(
                    1 for log in self.intervention_log 
                    if log["contradiction_type"] == "data_anomaly"
                )
            }
        }


def check_and_correct_diagnosis(
    reasoning_steps: List[Dict],
    root_causes: List[Dict],
    solutions: List[Dict],
    anomaly_info: Dict = None,
    is_simulation: bool = True
) -> Tuple[List[Dict], List[Dict], Dict]:
    """
    @brief 便捷函数：检查并修正诊断结果
    @param reasoning_steps: 推理步骤
    @param root_causes: 根因列表
    @param solutions: 解决方案列表
    @param anomaly_info: 异常信息
    @param is_simulation: 是否为模拟模式（默认True，跳过拦截）
    @return: (修正后的root_causes, 修正后的solutions, 检查结果)
    """
    firewall = ConsistencyFirewall()
    
    result = firewall.check_reasoning_conclusion_consistency(
        reasoning_steps,
        root_causes,
        solutions,
        anomaly_info
    )
    
    if result.intervention_type == "force_override":
        corrected_causes, corrected_solutions = firewall.apply_correction(
            result, root_causes, solutions, is_simulation=is_simulation
        )
        return corrected_causes, corrected_solutions, result.to_dict() if hasattr(result, 'to_dict') else {
            "is_consistent": result.is_consistent,
            "has_contradiction": result.has_contradiction,
            "contradiction_type": result.contradiction_type,
            "intervention_type": result.intervention_type
        }
    
    return root_causes, solutions, {
        "is_consistent": result.is_consistent,
        "has_contradiction": result.has_contradiction,
        "contradiction_type": result.contradiction_type,
        "intervention_type": result.intervention_type
    }


consistency_firewall = ConsistencyFirewall()


__all__ = [
    'ConsistencyFirewall',
    'ConsistencyCheckResult',
    'check_and_correct_diagnosis',
    'consistency_firewall'
]
