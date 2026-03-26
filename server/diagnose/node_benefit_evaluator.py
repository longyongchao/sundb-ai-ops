#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : node_benefit_evaluator.py
@Author  : LI
@Date    : 2026
@Desc    : 节点收益评估器
            Reference: D-Bot Paper Section 6.2 - Node Scoring
            
            实现完整的奖励函数 R，包含：
            1. Instant Benefit（即时收益）：当前动作的直接价值
            2. Long-term Benefit（长期收益）：对未来诊断的价值
            3. Selection Frequency（选择频率）：UCT探索因子
"""
import json
import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BenefitScore:
    """收益评分结果"""
    instant_benefit: float
    long_term_benefit: float
    selection_frequency: float  # 新增：选择频率
    combined_score: float
    breakdown: Dict
    
    def to_dict(self) -> Dict:
        return {
            "instant_benefit": round(self.instant_benefit, 4),
            "long_term_benefit": round(self.long_term_benefit, 4),
            "selection_frequency": round(self.selection_frequency, 4),  # 新增
            "combined_score": round(self.combined_score, 4),
            "breakdown": self.breakdown
        }


class NodeBenefitEvaluator:
    """
    @class NodeBenefitEvaluator
    @brief 节点收益评估器
    @reference D-Bot Paper Section 6.2 - Reward Function
    
    奖励函数 R(s, a) = α * Instant(s, a) + (1-α) * LongTerm(s, a)
    
    其中：
    - Instant(s, a)：即时收益，评估当前动作的信息价值
    - LongTerm(s, a)：长期收益，评估对未来诊断的潜在价值
    - α：权重系数，默认 0.6
    """
    
    ROOT_CAUSE_KEYWORDS = {
        "high_weight": ["slow_query", "lock_contention", "memory_leak", "io_bottleneck", "cpu_pressure"],
        "medium_weight": ["index", "timeout", "connection", "transaction", "deadlock"],
        "low_weight": ["query", "table", "column", "index"]
    }
    
    VALUABLE_PATTERNS = [
        r"发现.*问题",
        r"检测到.*异常",
        r"存在.*瓶颈",
        r"建议.*优化",
        r"根因.*确定",
        r"CPU.*使用率.*\d+%",
        r"内存.*使用.*\d+%",
        r"等待.*\d+.*ms",
        r"慢查询.*\d+.*条"
    ]
    
    CONCLUSION_PATTERNS = [
        r"根因.*是",
        r"问题.*在于",
        r"原因是",
        r"导致.*问题"
    ]
    
    KNOWLEDGE_PATTERNS = [
        r"建议.*创建索引",
        r"建议.*优化",
        r"建议.*调整参数",
        r"可以.*解决",
        r"应该.*检查"
    ]
    
    ACTION_PROGRESS = {
        "obtain_metric_values": 0.3,
        "query_pg_stat_statements": 0.4,
        "explain_query": 0.5,
        "check_lock_status": 0.4,
        "check_active_sessions": 0.35,
        "check_storage_stats": 0.3,
        "get_database_size": 0.2,
        "optimize_index_selection": 0.6,
        "Finish": 0.9
    }
    
    def __init__(self, alpha: float = 0.6, uct_c: float = 1.0):
        """
        @brief 初始化评估器
        @param alpha: 即时收益权重，默认 0.6
        @param uct_c: UCT 探索因子常数，默认 1.0（论文 UCT 公式的 c)
        """
        self.alpha = alpha
        self.uct_c = uct_c  # 新增：UCT 探索常数
        self._previous_metrics: Dict = {}
        
        self._compiled_valuable_patterns = [re.compile(pattern) for pattern in self.VALUABLE_PATTERNS]
        self._compiled_conclusion_patterns = [re.compile(pattern) for pattern in self.CONCLUSION_PATTERNS]
        self._compiled_knowledge_patterns = [re.compile(pattern) for pattern in self.KNOWLEDGE_PATTERNS]
        
        self._compiled_high_weight = [re.compile(r'\b' + re.escape(kw) + r'\b') for kw in self.ROOT_CAUSE_KEYWORDS["high_weight"]]
        self._compiled_medium_weight = [re.compile(r'\b' + re.escape(kw) + r'\b') for kw in self.ROOT_CAUSE_KEYWORDS["medium_weight"]]
        self._compiled_low_weight = [re.compile(r'\b' + re.escape(kw) + r'\b') for kw in self.ROOT_CAUSE_KEYWORDS["low_weight"]]
    
    def evaluate(self, observation: str, action: str, context: Dict = None) -> BenefitScore:
        """
        @brief 评估节点收益
        @param observation: 观察结果
        @param action: 执行的动作
        @param context: 上下文信息（包含历史路径、当前深度等）
        @return: BenefitScore 收益评分结果
        """
        if not isinstance(observation, str):
            observation = str(observation) if observation is not None else ""
        if not isinstance(action, str):
            action = str(action) if action is not None else ""
        if context is not None and not isinstance(context, dict):
            context = {}
        
        context = context or {}
        
        instant, instant_breakdown = self._calculate_instant_benefit(
            observation, action, context
        )
        
        long_term, long_term_breakdown = self._calculate_long_term_benefit(
            observation, action, context
        )
        
        # 新增：计算选择频率惩罚（UCT 探索因子）
        selection_freq, freq_breakdown = self._calculate_selection_frequency(action, context)
        
        # 修正：最终 combined_score 应用 UCT 思想
        # 论文：整体收益 = 基础收益 + 探索因子
        base_score = self.alpha * instant + (1 - self.alpha) * long_term
        
        # UCT 探索奖励
        total_visits = context.get("total_visits", 1)
        node_visits = context.get("node_visits", 1)
        uct_exploration_bonus = self.uct_c * np.sqrt(np.log(total_visits + 1)) / (node_visits + 1)
        
        # 选择频率惩罚：如果该动作被频繁选择，降低分数
        combined = base_score + uct_exploration_bonus - selection_freq * 0.2
        
        return BenefitScore(
            instant_benefit=instant,
            long_term_benefit=long_term,
            selection_frequency=selection_freq,  # 新增
            combined_score=combined,
            breakdown={
                "instant": instant_breakdown,
                "long_term": long_term_breakdown,
                "selection_frequency": freq_breakdown,  # 新增
                "uct_exploration_bonus": uct_exploration_bonus,  # 新增
                "alpha": self.alpha,
                "uct_c": self.uct_c
            }
        )
    
    def _calculate_instant_benefit(
        self, 
        observation: str, 
        action: str,
        context: Dict
    ) -> Tuple[float, Dict]:
        """
        @brief 计算即时收益
        @reference D-Bot Paper Section 6.2 - Instant Benefit
        
        即时收益评估维度：
        1. 信息增益：是否获取了有价值的新信息
        2. 根因发现：是否发现了明确的根因证据
        3. 诊断进度：是否推进了诊断进程
        4. 数据质量：返回数据的完整性和有效性
        """
        breakdown = {
            "info_gain": 0.0,
            "root_cause_evidence": 0.0,
            "diagnosis_progress": 0.0,
            "data_quality": 0.0
        }
        
        info_gain = self._evaluate_information_gain(observation)
        breakdown["info_gain"] = info_gain
        
        root_cause_score = self._evaluate_root_cause_evidence(observation)
        breakdown["root_cause_evidence"] = root_cause_score
        
        progress = self._evaluate_diagnosis_progress(action, observation, context)
        breakdown["diagnosis_progress"] = progress
        
        quality = self._evaluate_data_quality(observation)
        breakdown["data_quality"] = quality
        
        instant = (
            info_gain * 0.25 +
            root_cause_score * 0.35 +
            progress * 0.25 +
            quality * 0.15
        )
        
        return instant, breakdown
    
    def _calculate_long_term_benefit(
        self,
        observation: str,
        action: str,
        context: Dict
    ) -> Tuple[float, Dict]:
        """
        @brief 计算长期收益（更贴近论文 Section 6.2）
        @reference D-Bot Paper Section 6.2 - Long-term Benefit
        
        论文明确的三个评估维度：
        1. Closeness to task completion（是否接近找到根因）
        2. Performance（即时收益的表现）
        3. Efficiency（和祖先节点的重叠率，避免无效重复）
        """
        breakdown = {
            "closeness_to_completion": 0.0,  # 论文维度 1
            "performance": 0.0,                # 论文维度 2
            "efficiency": 0.0,                 # 论文维度 3
            "valid_votes": 0                   # 论文：有效投票数
        }
        
        # 1. Closeness to task completion（是否接近完成）
        closeness = 0.0
        if any(kw in observation for kw in ["根因", "确定", "结论", "Finish"]):
            closeness = 0.8
        elif any(kw in observation for kw in ["发现", "检测到", "异常"]):
            closeness = 0.5
        breakdown["closeness_to_completion"] = closeness
        
        # 2. Performance（基于即时收益的表现）
        # 论文：基于 instant benefit 的表现
        performance = 0.0
        if "success" in observation and "错误" not in observation:
            performance = 0.6
        if any(kw in observation for kw in ["慢查询", "CPU", "锁", "IO"]):
            performance += 0.2
        breakdown["performance"] = min(performance, 1.0)
        
        # 3. Efficiency（效率：和祖先节点的重叠率）
        # 论文：overlap rate with the analysis results of the ancestor nodes
        efficiency = 0.5
        history = context.get("history_path", [])
        if history:
            # 简单实现：检查当前 action 是否和最近 3 步重复
            recent_actions = [step.get("action") for step in history[-3:]]
            if action not in recent_actions:
                efficiency = 0.8
            else:
                efficiency = 0.2
        breakdown["efficiency"] = efficiency
        
        # 论文：有效投票数（模拟多轮投票）
        valid_votes = sum([
            1 if closeness > 0.5 else 0,
            1 if performance > 0.5 else 0,
            1 if efficiency > 0.5 else 0
        ])
        breakdown["valid_votes"] = valid_votes
        
        long_term = (
            closeness * 0.4 +
            performance * 0.35 +
            efficiency * 0.25
        )
        
        return long_term, breakdown
    
    def _evaluate_information_gain(self, observation: str) -> float:
        """评估信息增益"""
        if not observation:
            return 0.0
        
        score = 0.0
        
        for pattern in self._compiled_valuable_patterns:
            if pattern.search(observation):
                score += 0.15
        
        try:
            if observation.startswith("{"):
                data = json.loads(observation)
                if isinstance(data, dict):
                    score += min(len(data) * 0.05, 0.3)
                    
                    numeric_count = sum(1 for v in data.values() if isinstance(v, (int, float)))
                    score += min(numeric_count * 0.03, 0.2)
        except json.JSONDecodeError:
            logger.debug(f"观察结果不是有效JSON: {observation[:50]}...")
        except Exception as e:
            logger.warning(f"解析观察结果时出错: {e}")
        
        word_count = len(observation.split())
        score += min(word_count * 0.005, 0.2)
        
        return min(score, 1.0)
    
    def _evaluate_root_cause_evidence(self, observation: str) -> float:
        """评估根因发现证据 - 使用单词边界匹配避免重复加分"""
        if not observation:
            return 0.0
        
        score = 0.0
        obs_lower = observation.lower()
        matched_keywords = set()
        
        for pattern in self._compiled_high_weight:
            match = pattern.search(obs_lower)
            if match:
                kw = match.group()
                if kw not in matched_keywords:
                    score += 0.3
                    matched_keywords.add(kw)
        
        for pattern in self._compiled_medium_weight:
            match = pattern.search(obs_lower)
            if match:
                kw = match.group()
                if kw not in matched_keywords:
                    score += 0.15
                    matched_keywords.add(kw)
        
        if re.search(r"\d+%|\d+ms|\d+s|\d+条", observation):
            score += 0.2
        
        for pattern in self._compiled_conclusion_patterns:
            if pattern.search(observation):
                score += 0.25
                break
        
        return min(score, 1.0)
    
    def _evaluate_diagnosis_progress(
        self, 
        action: str, 
        observation: str,
        context: Dict
    ) -> float:
        """评估诊断进度"""
        score = 0.0
        
        score = self.ACTION_PROGRESS.get(action, 0.2)
        
        if observation and "错误" not in observation and "失败" not in observation:
            score += 0.1
        
        depth = context.get("depth", 0)
        if depth > 0:
            score += min(depth * 0.05, 0.2)
        
        return min(score, 1.0)
    
    def _evaluate_data_quality(self, observation: str) -> float:
        """评估数据质量"""
        if not observation:
            return 0.0
        
        score = 0.5
        
        try:
            if observation.startswith("{"):
                data = json.loads(observation)
                
                status = data.get("status", "")
                if status == "success":
                    score += 0.3
                elif status == "error":
                    score -= 0.3
                
                if data.get("data"):
                    score += 0.1
                if data.get("analysis"):
                    score += 0.1
                    
        except json.JSONDecodeError:
            if "错误" in observation:
                score -= 0.2
            elif len(observation) > 100:
                score += 0.2
        except Exception as e:
            logger.warning(f"评估数据质量时出错: {e}")
            score -= 0.1
        
        return max(0.0, min(score, 1.0))
    
    def _evaluate_exploration_potential(self, observation: str, context: Dict) -> float:
        """评估探索潜力"""
        score = 0.5
        
        if any(kw in observation for kw in ["发现", "检测到", "存在", "异常"]):
            score += 0.2
        
        if "根因" in observation and "确定" in observation:
            score -= 0.3
        
        depth = context.get("depth", 0)
        max_depth = context.get("max_depth", 10)
        if depth < max_depth * 0.5:
            score += 0.2
        elif depth > max_depth * 0.8:
            score -= 0.2
        
        return max(0.0, min(score, 1.0))
    
    def _evaluate_path_diversity(self, action: str, context: Dict) -> float:
        """评估路径多样性"""
        score = 0.5
        
        history = context.get("history_path", [])
        action_count = sum(1 for step in history if step.get("action") == action)
        
        if action_count == 0:
            score += 0.3
        elif action_count == 1:
            score += 0.1
        else:
            score -= 0.2
        
        return max(0.0, min(score, 1.0))
    
    def _evaluate_knowledge_value(self, observation: str) -> float:
        """评估知识积累价值"""
        score = 0.3
        
        for pattern in self._compiled_knowledge_patterns:
            if pattern.search(observation):
                score += 0.2
                break
        
        if "CREATE INDEX" in observation or "ALTER" in observation:
            score += 0.3
        
        return min(score, 1.0)
    
    def _evaluate_pruning_value(self, observation: str, context: Dict) -> float:
        """评估剪枝价值（是否值得继续探索）"""
        if any(kw in observation for kw in ["无异常", "正常", "无问题", "未发现"]):
            return 0.2
        
        if "错误" in observation or "失败" in observation:
            return 0.1
        
        if "Finish" in observation:
            return 0.3
        
        return 0.7
    
    def update_metrics(self, metrics: Dict):
        """更新指标快照，用于计算指标变化"""
        self._previous_metrics = metrics.copy()
    
    def calculate_metric_change(self, current_metrics: Dict) -> Dict:
        """计算指标变化"""
        if not self._previous_metrics:
            return {"change": 0, "direction": "unknown"}
        
        changes = {}
        for key, value in current_metrics.items():
            if key in self._previous_metrics:
                prev = self._previous_metrics[key]
                if isinstance(value, (int, float)) and isinstance(prev, (int, float)):
                    change = value - prev
                    changes[key] = {
                        "previous": prev,
                        "current": value,
                        "change": change,
                        "change_percent": (change / prev * 100) if prev != 0 else 0
                    }
        
        return changes
    
    def _calculate_selection_frequency(self, action: str, context: Dict) -> Tuple[float, Dict]:
        """
        @brief 计算选择频率（依据论文 Section 6.2）
        Selection frequency = max(ancestor selection count) + 1
        """
        breakdown = {
            "action_count_in_history": 0,
            "max_ancestor_count": 0,
            "frequency_penalty": 0.0
        }
        
        history = context.get("history_path", [])
        action_count = sum(1 for step in history if step.get("action") == action)
        breakdown["action_count_in_history"] = action_count
        
        # 论文：选择频率是祖先节点被选择的最大次数 + 1
        ancestor_counts = context.get("ancestor_selection_counts", {})
        max_ancestor = max(ancestor_counts.values()) if ancestor_counts else 0
        breakdown["max_ancestor_count"] = max_ancestor
        
        # 频率惩罚：如果该动作在历史中出现超过 2 次，给予惩罚
        penalty = 0.0
        if action_count >= 3:
            penalty = 0.3
        elif action_count == 2:
            penalty = 0.1
        breakdown["frequency_penalty"] = penalty
        
        return penalty, breakdown


def calculate_node_quality_score(node, previous_nodes=None):
    """
    @brief 计算节点质量分（对齐论文 Section 6 的三维度评分）
    @reference D-Bot Paper Section 6 - Node Quality Scoring
    评分范围：0.0 - 1.0，≥0.7 为高质量
    
    @param node: 当前节点对象（需有 observation, action 属性）
    @param previous_nodes: 前序节点列表
    @return: Dict 包含 score, should_prune, penalties. instant_benefit
    """
    if previous_nodes is None:
        previous_nodes = []
    
    score = 0.5  # 基础分
    penalties = 0.0
    
    # ==========================================
    # 维度 1：即时收益 (Instant Benefit) - 基于工具返回结果
    # ==========================================
    if hasattr(node, 'observation') and node.observation:
        obs = str(node.observation)
        
        # 情况 A：拿到了新的异常数据/慢查询 → 高分
        if 'slow_queries' in obs and len(obs) > 500:
            score += 0.3
        elif 'cpu_usage' in obs and 'abnormal' in obs.lower():
            score += 0.25
        elif 'active_sessions' in obs and len(obs) > 200:
            score += 0.2
        
        # 情况 B：数据重复/无关 → 低分
        elif 'cached' in obs.lower() or 'already' in obs.lower():
            score -= 0.2
            penalties += 0.2
        
        # 情况 C：工具调用失败/空结果 → 极低分
        elif 'error' in obs.lower() or 'fail' in obs.lower():
            score -= 0.3
            penalties += 0.3
    
    # ==========================================
    # 维度 2：选择频率惩罚 (Selection Frequency)
    # ==========================================
    if hasattr(node, 'action'):
        current_action = str(node.action)
        
        # 统计同一工具的调用次数
        same_tool_count = 0
        for prev_node in previous_nodes:
            if hasattr(prev_node, 'action') and str(prev_node.action) == current_action:
                same_tool_count += 1
        
        # 超过2次，每次扣0.15分
        if same_tool_count >= 2:
            penalties += (same_tool_count - 1) * 0.15
    
    # ==========================================
    # 维度 3：知识匹配度 (Knowledge Augmented)
    # ==========================================
    if hasattr(node, 'matched_knowledge') and node.matched_knowledge:
        if len(node.matched_knowledge) > 0:
            score += 0.1  # 有相关知识，加0.1分
    
    # ==========================================
    # 最终分数归一化 (0.0 - 1.0)
    # ==========================================
    final_score = max(0.0, min(1.0, score - penalties))
    
    # 标记是否需要剪枝
    should_prune = final_score < 0.3
    
    return {
                'score': round(final_score, 2),
                'should_prune': should_prune,
                'penalties': round(penalties, 2),
                'instant_benefit': round(score - 0.5, 2)
        }


node_benefit_evaluator = NodeBenefitEvaluator()


def evaluate_node_benefit(observation: str, action: str, context: Dict = None) -> BenefitScore:
    """
    @brief 便捷函数：评估节点收益
    @param observation: 观察结果
    @param action: 执行的动作
    @param context: 上下文信息
    @return: BenefitScore 收益评分
    """
    return node_benefit_evaluator.evaluate(observation, action, context)


__all__ = ['BenefitScore', 'NodeBenefitEvaluator', 'calculate_node_quality_score', 'evaluate_node_benefit', 'node_benefit_evaluator']
