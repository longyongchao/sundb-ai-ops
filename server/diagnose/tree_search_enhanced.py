#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UCT Tree Search Implementation for Database Diagnosis

This module implements the tree search algorithm for LLM-based database diagnosis,
based on the MCTS (Monte Carlo Tree Search) framework with UCT (Upper Confidence Bound 
applied to Trees) selection strategy.

Key Features:
- MCTS four-step loop: Selection -> Expansion -> Simulation -> Backpropagation
- UCT-based node selection balancing exploration and exploitation
- Physical reward evaluation using database metrics
- Pruning mechanism for low-potential branches

Author: [Your Name]
Date: 2024
"""
import numpy as np
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from server.diagnose.tree_search_service import TreeNode, NodeType, ReasoningStep
from server.utils import get_ChatOpenAI, get_beijing_now_str


@dataclass
class UCTConfig:
    """
    Configuration parameters for UCT algorithm.
    
    Attributes:
        exploration_weight: Exploration constant C (sqrt(2) by default)
        max_iterations: Maximum number of MCTS iterations
        simulation_depth: Depth limit for simulation phase
        prune_threshold: Reward threshold for pruning low-potential branches
        min_visits_for_prune: Minimum visits before pruning check
    """
    exploration_weight: float = 1.414  # C = sqrt(2), balances exploration vs exploitation
    max_iterations: int = 10
    simulation_depth: int = 3
    prune_threshold: float = 0.1
    min_visits_for_prune: int = 3


class TrueUCTTreeSearch:
    """
    UCT-based tree search for database anomaly diagnosis.
    
    This class implements the MCTS algorithm to guide LLM through the diagnosis process,
    avoiding premature convergence and hallucination issues common in simple chain-of-thought.
    
    The algorithm consists of four phases:
        1. Selection: Traverse tree using UCT to find most promising leaf
        2. Expansion: Generate child nodes by LLM action proposals
        3. Simulation: Evaluate nodes through physical metrics and LLM scoring
        4. Backpropagation: Update statistics up the tree path
    """
    
    def __init__(self, llm, config: UCTConfig = None):
        self.llm = llm
        self.config = config or UCTConfig()
        self.node_counter = 0
        
    def search(self, root_node: TreeNode, anomaly_info: Dict, 
               relevant_knowledge: List[Dict]) -> Tuple[List[ReasoningStep], TreeNode]:
        """
        Execute UCT tree search to find optimal diagnosis path.
        
        Args:
            root_node: Root of the search tree
            anomaly_info: Current anomaly description and metrics
            relevant_knowledge: Retrieved knowledge chunks for context
            
        Returns:
            Tuple of (reasoning steps list, best terminal node)
        """
        print(f"\n{'='*60}")
        print(f"Starting UCT Tree Search (max iterations: {self.config.max_iterations})")
        print(f"{'='*60}\n")
        
        best_terminal_node = None
        best_score = -float('inf')
        
        # Main MCTS loop
        for iteration in range(self.config.max_iterations):
            print(f"\nIteration {iteration + 1}/{self.config.max_iterations}")
            
            # Phase 1: Selection - Navigate to most promising leaf
            selected_node = self._select_best_leaf(root_node)
            print(f"   Selected node: depth={selected_node.get_depth()}, "
                  f"visits={selected_node.visit_count}, "
                  f"UCT={selected_node.compute_uct_value():.3f}")
            
            if selected_node.is_terminal:
                print(f"   Terminal node reached, evaluating...")
                score = self._evaluate_terminal_node(selected_node)
                if score > best_score:
                    best_score = score
                    best_terminal_node = selected_node
                continue
            
            # Phase 2: Expansion - Create child nodes
            new_children = self._expand_node(selected_node, anomaly_info, relevant_knowledge)
            if not new_children:
                print(f"   No expansion possible, skipping")
                continue
            
            print(f"   Generated {len(new_children)} child nodes")
            
            # Phase 3: Simulation - Evaluate each child
            for child in new_children:
                if child.is_terminal:
                    # Direct evaluation for terminal nodes
                    instant_reward = self._get_terminal_reward(child)
                    llm_score = self._get_llm_evaluation(child, anomaly_info)
                else:
                    # Simulation for intermediate nodes
                    instant_reward = self._simulate_physical_reward(child, anomaly_info)
                    llm_score = self._get_llm_evaluation(child, anomaly_info)
                
                # Combine rewards: 70% physical metrics + 30% LLM evaluation
                # Physical metrics provide objective grounding, LLM provides semantic understanding
                total_reward = 0.7 * instant_reward + 0.3 * llm_score
                
                print(f"   Child evaluation: instant={instant_reward:.3f}, "
                      f"LLM={llm_score:.3f}, total={total_reward:.3f}")
                
                # Phase 4: Backpropagation - Update statistics up the tree
                self._backpropagate(child, total_reward)
                
                # Check if this branch should be pruned
                self._check_and_prune(child)
                
                # Track best terminal node found so far
                if child.is_terminal and total_reward > best_score:
                    best_score = total_reward
                    best_terminal_node = child
        
        # Extract the best path from root to best terminal node
        best_path = self._extract_best_path(root_node, best_terminal_node)
        
        print(f"\n{'='*60}")
        print(f"UCT Search Completed")
        print(f"   Best path depth: {len(best_path)}")
        print(f"   Best score: {best_score:.3f}")
        print(f"{'='*60}\n")
        
        return best_path, best_terminal_node
    
    def _select_best_leaf(self, node: TreeNode) -> TreeNode:
        """
        Selection phase: Traverse tree to find most promising leaf node.
        
        Uses UCT formula to balance exploration (unvisited nodes) and 
        exploitation (high-reward nodes).
        
        Args:
            node: Starting node (usually root)
            
        Returns:
            Most promising leaf node for expansion
        """
        current = node
        
        while current.children:
            # Filter out pruned branches
            active_children = [c for c in current.children if not c.pruned]
            
            if not active_children:
                break
            
            # Prioritize unvisited nodes for exploration
            unvisited = [c for c in active_children if c.visit_count == 0]
            if unvisited:
                current = unvisited[0]
            else:
                # All children visited, select by UCT value
                current = max(active_children, 
                            key=lambda c: c.compute_uct_value(self.config.exploration_weight))
        
        return current
    
    def _expand_node(self, node: TreeNode, anomaly_info: Dict, 
                     relevant_knowledge: List[Dict]) -> List[TreeNode]:
        """
        Expansion phase: Generate child nodes by LLM action proposals.
        
        Uses LLM to suggest 2-3 possible next actions based on current context.
        
        Args:
            node: Node to expand
            anomaly_info: Current anomaly description
            relevant_knowledge: Retrieved knowledge for context
            
        Returns:
            List of new child nodes
        """
        if node.is_terminal:
            return []
        
        # Build context for LLM
        context = self._build_expansion_context(node, anomaly_info, relevant_knowledge)
        
        # Generate candidate actions via LLM
        try:
            prompt = self._build_expansion_prompt(context)
            response = self.llm.generate_reasoning({"prompt": prompt})
            
            # Parse generated actions
            actions = self._parse_expansion_actions(response)
            
            children = []
            for action in actions[:3]:  # 最多3个子节点
                self.node_counter += 1
                child = TreeNode(
                    node_type=NodeType.ACTION.value,
                    thought=action.get("thought", ""),
                    action=action.get("action", ""),
                    action_input=action.get("action_input", {}),
                    parent=node
                )
                children.append(child)
                node.add_child(child)
            
            return children
            
        except Exception as e:
            print(f"[ERROR] 节点扩展失败: {e}")
            return []
    
    def _simulate_physical_reward(self, node: TreeNode, anomaly_info: Dict) -> float:
        """
        Simulation: 获取即时物理收益
        
        如果动作涉及索引建议，尝试使用 hypopg 评估 Cost 变化
        """
        action = node.action
        action_input = node.action_input
        
        # 默认收益
        default_reward = 0.5
        
        # 检查是否是索引相关动作
        if "index" in action.lower() or "CREATE INDEX" in str(action_input):
            return self._evaluate_index_benefit(action_input, anomaly_info)
        
        # 检查是否是查询优化
        if "explain" in action.lower() or "analyze" in action.lower():
            return 0.6  # 分析类动作有中等收益
        
        # 检查是否是终止动作
        if action == "Finish" or node.is_terminal:
            return self._evaluate_diagnosis_quality(node, anomaly_info)
        
        return default_reward
    
    def _evaluate_index_benefit(self, action_input: Dict, anomaly_info: Dict) -> float:
        """
        使用 hypopg 评估索引建议的收益
        
        Returns:
            0-1 之间的收益值
        """
        try:
            # 尝试导入 hypopg 评估工具
            from server.diagnose.db_tools import PostgresDiagnosticTools
            
            tools = PostgresDiagnosticTools()
            
            # 提取表名和列名
            sql = action_input.get("sql", "")
            
            # 简单的 SQL 解析提取表和列
            import re
            table_match = re.search(r'ON\s+(\w+)', sql, re.IGNORECASE)
            column_match = re.search(r'\((\w+)\)', sql)
            
            if not table_match or not column_match:
                return 0.5
            
            table_name = table_match.group(1)
            column_name = column_match.group(1)
            
            # 获取表统计信息
            stats = tools.get_table_statistics(table_name)
            if not stats:
                return 0.5
            
            # 基于表大小和列区分度估算收益
            table_info = stats[0] if isinstance(stats, list) else stats
            live_tuples = table_info.get('live_tuples', 0)
            
            # 大表 + 索引 = 高收益
            if live_tuples > 100000:  # 10万行以上
                return 0.85
            elif live_tuples > 10000:  # 1万行以上
                return 0.75
            else:
                return 0.65
                
        except Exception as e:
            print(f"[WARN] hypopg 评估失败，使用默认收益: {e}")
            return 0.6
    
    def _get_llm_evaluation(self, node: TreeNode, anomaly_info: Dict) -> float:
        """
        获取 LLM 对节点的长期收益评估
        
        Returns:
            0-1 之间的评分
        """
        try:
            prompt = f"""
评估以下诊断步骤的质量（0-100分）：

异常信息: {anomaly_info.get('description', '')}
当前动作: {node.action}
动作输入: {node.action_input}
思考过程: {node.thought}

评分标准：
- 90-100: 动作精准，直接针对根因
- 70-89: 动作合理，有助于诊断
- 50-69: 动作一般，信息增益有限
- 0-49: 动作不当，可能偏离目标

只返回数字分数（0-100）："""
            
            response = self.llm.generate_reasoning({"prompt": prompt})
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 提取数字
            import re
            numbers = re.findall(r'\d+', content)
            if numbers:
                score = int(numbers[0])
                return min(100, max(0, score)) / 100.0
            
            return 0.5
            
        except Exception as e:
            print(f"[WARN] LLM 评估失败: {e}")
            return 0.5
    
    def _get_terminal_reward(self, node: TreeNode) -> float:
        """获取终止节点的最终收益"""
        return self._evaluate_diagnosis_quality(node, {})
    
    def _evaluate_diagnosis_quality(self, node: TreeNode, anomaly_info: Dict) -> float:
        """评估诊断质量"""
        # 基于观察结果评估
        observation = node.observation
        
        if not observation:
            return 0.3
        
        # 检查是否包含关键信息
        score = 0.5
        
        if "root_cause" in observation.lower():
            score += 0.2
        if "solution" in observation.lower() or "建议" in observation:
            score += 0.2
        if "confidence" in observation.lower() or "置信度" in observation:
            score += 0.1
        
        return min(1.0, score)
    
    def _backpropagate(self, node: TreeNode, reward: float):
        """
        Backpropagation: 向上回溯更新路径上所有节点的统计信息
        """
        current = node
        while current:
            current.visit_count += 1
            current.values.append(reward)
            current = current.parent
    
    def _check_and_prune(self, node: TreeNode):
        """
        剪枝策略：
        1. 连续多次访问收益低于阈值
        2. 节点深度过大
        """
        if node.visit_count < self.config.min_visits_for_prune:
            return
        
        # 检查最近几次的收益
        recent_values = node.values[-self.config.min_visits_for_prune:]
        avg_reward = np.mean(recent_values)
        
        if avg_reward < self.config.prune_threshold:
            node.pruned = True
            print(f"   ✂️ 剪枝节点: 平均收益 {avg_reward:.3f} < 阈值 {self.config.prune_threshold}")
    
    def _extract_best_path(self, root: TreeNode, terminal_node: TreeNode) -> List[ReasoningStep]:
        """提取从根到最佳终止节点的路径"""
        if not terminal_node:
            # 如果没有找到终止节点，选择访问次数最多的路径
            terminal_node = self._find_best_terminal_node(root)
        
        if not terminal_node:
            return []
        
        # 回溯路径
        path_nodes = []
        current = terminal_node
        while current and current != root:
            path_nodes.append(current)
            current = current.parent
        
        path_nodes.reverse()
        
        # 转换为 ReasoningStep
        steps = []
        for i, node in enumerate(path_nodes, 1):
            step = ReasoningStep(
                step=i,
                thought=node.thought,
                action=node.action,
                action_input=node.action_input,
                observation=node.observation
            )
            steps.append(step)
        
        return steps
    
    def _find_best_terminal_node(self, root: TreeNode) -> Optional[TreeNode]:
        """找到最佳的终止节点"""
        best_node = None
        best_score = -float('inf')
        
        def traverse(node: TreeNode):
            nonlocal best_node, best_score
            
            if node.is_terminal and node.values:
                score = np.mean(node.values)
                if score > best_score:
                    best_score = score
                    best_node = node
            
            for child in node.children:
                traverse(child)
        
        traverse(root)
        return best_node
    
    def _evaluate_terminal_node(self, node: TreeNode) -> float:
        """评估终止节点的最终得分"""
        if not node.values:
            return 0.0
        return np.mean(node.values)
    
    def _build_expansion_context(self, node: TreeNode, anomaly_info: Dict, 
                                 relevant_knowledge: List[Dict]) -> Dict:
        """构建扩展上下文"""
        return {
            "anomaly_info": anomaly_info,
            "current_depth": node.get_depth(),
            "current_thought": node.thought,
            "parent_observation": node.parent.observation if node.parent else "",
            "relevant_knowledge": relevant_knowledge
        }
    
    def _build_expansion_prompt(self, context: Dict) -> str:
        """构建扩展提示词"""
        return f"""
基于当前诊断状态，生成 2-3 个可能的下一步动作。

异常信息: {context['anomaly_info'].get('description', '')}
当前深度: {context['current_depth']}
当前思考: {context['current_thought']}

【输出语言强制要求】：
无论你参考的上下文、工具描述或知识块是何种语言，你输出的所有内容（尤其是"thought"字段）**必须全部使用流畅且专业的中文**。

请生成候选动作（JSON格式）：
[
    {{
        "thought": "为什么采取这个动作",
        "action": "动作名称",
        "action_input": {{"参数": "值"}}
    }}
]
"""
    
    def _parse_expansion_actions(self, response: str) -> List[Dict]:
        """解析扩展动作"""
        try:
            # 尝试解析 JSON
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            
            actions = json.loads(response.strip())
            if isinstance(actions, list):
                return actions
            elif isinstance(actions, dict):
                return [actions]
            return []
        except:
            # 降级处理：返回默认动作
            return [
                {
                    "thought": "分析系统指标",
                    "action": "check_metrics",
                    "action_input": {"metric_type": "cpu"}
                }
            ]


class IncrementalSummarizer:
    """
    增量摘要器 - 防止 Token 溢出
    Reference: D-Bot Paper Section 7.2
    """
    
    def __init__(self, max_entries: int = 10, llm=None):
        self.summary_log = []
        self.max_entries = max_entries
        self.llm = llm
        
    def update_summary(self, expert_name: str, action: str, observation: str) -> str:
        """
        将专家的每一个动作抽象为一句话摘要
        """
        # 提取关键信息（前100字符）
        brief_obs = observation[:100] + "..." if len(observation) > 100 else observation
        
        brief_info = f"[{expert_name}] 执行 {action}, 观察到: {brief_obs}"
        self.summary_log.append(brief_info)
        
        # 如果摘要过长，进行压缩
        if len(self.summary_log) > self.max_entries:
            return self._compress_summary()
        
        return "\n".join(self.summary_log)
    
    def _compress_summary(self) -> str:
        """使用 LLM 压缩摘要"""
        if not self.llm:
            # 简单压缩：保留最近的一半
            self.summary_log = self.summary_log[-self.max_entries//2:]
            return "\n".join(self.summary_log)
        
        try:
            prompt = f"""
将以下诊断日志压缩为简洁的摘要，保留关键指标和已排除的假设：

{chr(10).join(self.summary_log)}

要求：
1. 保留关键数值指标
2. 保留已确认的根因
3. 保留已排除的可能性
4. 压缩为3-5条要点

压缩摘要："""
            
            response = self.llm.generate_reasoning({"prompt": prompt})
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 更新日志
            self.summary_log = [f"[压缩摘要] {line}" for line in content.strip().split('\n') if line.strip()]
            
            return "\n".join(self.summary_log)
            
        except Exception as e:
            print(f"[WARN] 摘要压缩失败: {e}")
            # 降级：保留最近的一半
            self.summary_log = self.summary_log[-self.max_entries//2:]
            return "\n".join(self.summary_log)
    
    def get_summary(self) -> str:
        """获取当前摘要"""
        return "\n".join(self.summary_log)
    
    def clear(self):
        """清空摘要"""
        self.summary_log = []


# 便捷函数
def create_uct_searcher(llm, **kwargs) -> TrueUCTTreeSearch:
    """创建 UCT 搜索器"""
    config = UCTConfig(**kwargs)
    return TrueUCTTreeSearch(llm, config)
