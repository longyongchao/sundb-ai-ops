#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : reporter.py
@Author  : D-Bot Team
@Date    : 2024/01/01
@Desc    : 多智能体交叉审查报告生成器
            Reference: D-Bot Paper Section 7.3 - Cross Review
            
            实现论文中的多专家交叉审查机制：
            1. 收集各领域专家的独立诊断结果
            2. 识别专家结论之间的冲突和矛盾
            3. 证据链校验和权重评估
            4. 综合生成最终诊断报告
"""
import json
import time
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class ExpertReport:
    """
    @class ExpertReport
    @brief 专家诊断报告数据结构
    """
    expert_name: str
    expert_type: str
    conclusion: str
    confidence: float
    evidence: List[str] = field(default_factory=list)
    root_causes: List[Dict] = field(default_factory=list)
    solutions: List[Dict] = field(default_factory=list)
    reasoning_steps: List[Dict] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ReporterAgent:
    """
    @class ReporterAgent
    @brief 多智能体交叉审查报告生成器
    @reference D-Bot Paper Section 7.3 - Cross Review
    
    实现论文中的多专家交叉审查机制：
    1. 冲突识别：检测各专家结论是否存在矛盾
    2. 证据链校验：评估哪个专家的结论有更坚实的数据支撑
    3. 综合评估：建立跨领域的因果联系
    4. 报告生成：输出结构化的综合诊断报告
    """
    
    def __init__(self, llm_client=None):
        """
        @brief 初始化报告生成器
        @param llm_client: LLM客户端（用于生成最终报告）
        """
        self.llm_client = llm_client
        self.expert_reports: List[ExpertReport] = []
        
    def add_expert_report(self, report: ExpertReport):
        """
        @brief 添加专家诊断报告
        @param report: 专家报告
        """
        self.expert_reports.append(report)
        
    def add_expert_report_dict(self, report_dict: Dict):
        """
        @brief 从字典添加专家诊断报告
        @param report_dict: 专家报告字典
        """
        report = ExpertReport(
            expert_name=report_dict.get('expert_name', 'Unknown'),
            expert_type=report_dict.get('expert_type', 'general'),
            conclusion=report_dict.get('conclusion', ''),
            confidence=report_dict.get('confidence', 0.0),
            evidence=report_dict.get('evidence', []),
            root_causes=report_dict.get('root_causes', []),
            solutions=report_dict.get('solutions', []),
            reasoning_steps=report_dict.get('reasoning_steps', []),
            tools_used=report_dict.get('tools_used', [])
        )
        self.expert_reports.append(report)
    
    def clear_reports(self):
        """
        @brief 清空所有专家报告
        """
        self.expert_reports = []
    
    def cross_review_and_merge(self, anomaly_alert: str) -> Dict:
        """
        @brief 执行多专家交叉审查并生成最终诊断报告
        @param anomaly_alert: 异常告警信息
        @return: 综合诊断报告
        
        @reference D-Bot Paper Section 7.3 - Cross Review Algorithm
        """
        if not self.expert_reports:
            return {
                "status": "failed",
                "message": "未获取到有效的专家诊断报告",
                "final_report": None
            }
        
        conflicts = self._identify_conflicts()
        
        evidence_validation = self._validate_evidence_chains()
        
        causal_links = self._build_causal_links()
        
        merged_root_causes = self._merge_root_causes(conflicts, evidence_validation)
        merged_solutions = self._merge_solutions()
        
        if self.llm_client:
            final_report = self._generate_llm_report(
                anomaly_alert, conflicts, evidence_validation, 
                causal_links, merged_root_causes, merged_solutions
            )
        else:
            final_report = self._generate_structured_report(
                anomaly_alert, conflicts, evidence_validation,
                causal_links, merged_root_causes, merged_solutions
            )
        
        return {
            "status": "success",
            "expert_count": len(self.expert_reports),
            "conflicts": conflicts,
            "evidence_validation": evidence_validation,
            "causal_links": causal_links,
            "merged_root_causes": merged_root_causes,
            "merged_solutions": merged_solutions,
            "final_report": final_report,
            "timestamp": datetime.now().isoformat()
        }
    
    def _identify_conflicts(self) -> List[Dict]:
        """
        @brief 识别专家结论之间的冲突
        @return: 冲突列表
        
        @reference D-Bot Paper Section 7.3.1 - Conflict Detection
        """
        conflicts = []
        
        for i, report1 in enumerate(self.expert_reports):
            for j, report2 in enumerate(self.expert_reports[i+1:], i+1):
                conflict = self._check_pair_conflict(report1, report2)
                if conflict:
                    conflicts.append(conflict)
        
        return conflicts
    
    def _check_pair_conflict(self, report1: ExpertReport, report2: ExpertReport) -> Optional[Dict]:
        """
        @brief 检查两个专家报告之间是否存在冲突
        @param report1: 专家报告1
        @param report2: 专家报告2
        @return: 冲突信息（如果存在）
        """
        rc_types1 = set(rc.get('type', '') for rc in report1.root_causes)
        rc_types2 = set(rc.get('type', '') for rc in report2.root_causes)
        
        conflict_types = {
            ('cpu_high', 'io_bottleneck'),
            ('memory_leak', 'disk_full'),
            ('lock_contention', 'network_latency'),
            ('slow_query', 'connection_pool_exhausted')
        }
        
        for ct in conflict_types:
            if (ct[0] in rc_types1 and ct[1] in rc_types2) or \
               (ct[1] in rc_types1 and ct[0] in rc_types2):
                return {
                    "type": "potential_conflict",
                    "expert1": report1.expert_name,
                    "expert2": report2.expert_name,
                    "conflict_description": f"{report1.expert_name}认为根因是{list(rc_types1)}，而{report2.expert_name}认为是{list(rc_types2)}",
                    "resolution_hint": "需要进一步分析指标数据来确定主导因素"
                }
        
        return None
    
    def _validate_evidence_chains(self) -> Dict:
        """
        @brief 校验各专家的证据链强度
        @return: 证据链校验结果
        
        @reference D-Bot Paper Section 7.3.2 - Evidence Chain Validation
        """
        validation_results = {
            "expert_scores": {},
            "strongest_expert": None,
            "validation_details": []
        }
        
        for report in self.expert_reports:
            score = 0
            
            evidence_count = len(report.evidence)
            score += min(evidence_count * 10, 30)
            
            tools_count = len(report.tools_used)
            score += min(tools_count * 5, 20)
            
            score += report.confidence * 30
            
            steps_count = len(report.reasoning_steps)
            score += min(steps_count * 2, 20)
            
            validation_results["expert_scores"][report.expert_name] = {
                "score": score,
                "evidence_count": evidence_count,
                "tools_count": tools_count,
                "confidence": report.confidence,
                "steps_count": steps_count
            }
            
            validation_results["validation_details"].append({
                "expert": report.expert_name,
                "score": score,
                "has_solid_evidence": evidence_count >= 2,
                "used_multiple_tools": tools_count >= 2
            })
        
        if validation_results["expert_scores"]:
            strongest = max(
                validation_results["expert_scores"].items(),
                key=lambda x: x[1]["score"]
            )
            validation_results["strongest_expert"] = strongest[0]
        
        return validation_results
    
    def _build_causal_links(self) -> List[Dict]:
        """
        @brief 建立跨领域的因果联系
        @return: 因果链列表
        
        @reference D-Bot Paper Section 7.3.3 - Causal Link Building
        """
        causal_links = []
        
        causal_patterns = [
            {
                "pattern": ["memory_high", "io_bottleneck"],
                "link": "内存不足导致频繁Swap，进而引发IO瓶颈",
                "root_cause": "memory_insufficient",
                "confidence_boost": 0.1
            },
            {
                "pattern": ["slow_query", "cpu_high"],
                "link": "慢查询导致CPU计算密集，引发CPU使用率升高",
                "root_cause": "inefficient_query",
                "confidence_boost": 0.15
            },
            {
                "pattern": ["lock_contention", "slow_query"],
                "link": "锁竞争导致查询等待，表现为慢查询",
                "root_cause": "concurrency_issue",
                "confidence_boost": 0.12
            },
            {
                "pattern": ["missing_index", "slow_query"],
                "link": "缺少索引导致全表扫描，引发慢查询",
                "root_cause": "missing_index",
                "confidence_boost": 0.2
            }
        ]
        
        all_root_cause_types = set()
        for report in self.expert_reports:
            for rc in report.root_causes:
                rc_type = rc.get('type', '').lower().replace(' ', '_')
                all_root_cause_types.add(rc_type)
        
        for pattern_info in causal_patterns:
            pattern_set = set(pattern_info["pattern"])
            if pattern_set.issubset(all_root_cause_types) or \
               any(p in all_root_cause_types for p in pattern_set):
                causal_links.append({
                    "linked_causes": list(pattern_set & all_root_cause_types),
                    "explanation": pattern_info["link"],
                    "suggested_primary_cause": pattern_info["root_cause"],
                    "confidence_boost": pattern_info["confidence_boost"]
                })
        
        return causal_links
    
    def _merge_root_causes(
        self, 
        conflicts: List[Dict], 
        evidence_validation: Dict
    ) -> List[Dict]:
        """
        @brief 合并各专家的根因结果
        @param conflicts: 冲突列表
        @param evidence_validation: 证据校验结果
        @return: 合并后的根因列表
        """
        merged = {}
        strongest_expert = evidence_validation.get("strongest_expert")
        
        for report in self.expert_reports:
            for rc in report.root_causes:
                rc_type = rc.get('type', 'Unknown')
                
                if rc_type not in merged:
                    merged[rc_type] = {
                        "type": rc_type,
                        "description": rc.get('description', ''),
                        "confidence": rc.get('confidence', 0.0),
                        "evidence": rc.get('evidence', []),
                        "supporting_experts": [report.expert_name],
                        "is_primary": report.expert_name == strongest_expert
                    }
                else:
                    existing = merged[rc_type]
                    existing["supporting_experts"].append(report.expert_name)
                    
                    if rc.get('confidence', 0) > existing["confidence"]:
                        existing["confidence"] = rc.get('confidence', 0)
                        existing["description"] = rc.get('description', existing["description"])
                    
                    existing["evidence"].extend(rc.get('evidence', []))
        
        result = list(merged.values())
        result.sort(key=lambda x: (len(x["supporting_experts"]), x["confidence"]), reverse=True)
        
        if result:
            result[0]["is_primary"] = True
        
        return result[:5]
    
    def _merge_solutions(self) -> List[Dict]:
        """
        @brief 合并各专家的解决方案
        @return: 合并后的解决方案列表
        """
        merged = {}
        
        for report in self.expert_reports:
            for sol in report.solutions:
                sol_action = sol.get('action', 'Unknown')
                
                if sol_action not in merged:
                    merged[sol_action] = {
                        "action": sol_action,
                        "explanation": sol.get('explanation', ''),
                        "priority": sol.get('priority', 0),
                        "sql": sol.get('sql', ''),
                        "supporting_experts": [report.expert_name]
                    }
                else:
                    existing = merged[sol_action]
                    existing["supporting_experts"].append(report.expert_name)
                    if sol.get('priority', 0) > existing["priority"]:
                        existing["priority"] = sol.get('priority', 0)
        
        result = list(merged.values())
        result.sort(key=lambda x: (len(x["supporting_experts"]), x["priority"]), reverse=True)
        
        return result[:5]
    
    def _generate_llm_report(
        self,
        anomaly_alert: str,
        conflicts: List[Dict],
        evidence_validation: Dict,
        causal_links: List[Dict],
        merged_root_causes: List[Dict],
        merged_solutions: List[Dict]
    ) -> str:
        """
        @brief 使用LLM生成最终报告
        @param anomaly_alert: 异常告警
        @param conflicts: 冲突列表
        @param evidence_validation: 证据校验
        @param causal_links: 因果链
        @param merged_root_causes: 合并的根因
        @param merged_solutions: 合并的解决方案
        @return: 最终报告文本
        """
        reports_content = ""
        for report in self.expert_reports:
            reports_content += f"\n【{report.expert_name}的诊断意见】:\n"
            reports_content += f"结论: {report.conclusion}\n"
            reports_content += f"置信度: {report.confidence:.2%}\n"
            reports_content += f"证据: {', '.join(report.evidence[:3])}\n"
        
        review_prompt = f"""
你现在是数据库首席DBA (Chief DBA)。系统发生了以下告警：
[告警信息]: {anomaly_alert}

以下是多个领域专家通过树搜索独立得出的诊断意见：
{reports_content}

请你执行"交叉审查 (Cross Review)"任务：
1. 识别冲突：检查各专家的结论是否存在矛盾
2. 证据链校验：评估哪个专家的结论拥有更坚实的监控指标数据支撑
3. 综合评估：如果根本原因是跨领域的，请建立因果联系
4. 输出最终报告：请输出一份结构化的综合诊断报告

已识别的冲突: {json.dumps(conflicts, ensure_ascii=False, indent=2)}
证据链校验结果: {json.dumps(evidence_validation, ensure_ascii=False, indent=2)}
因果链分析: {json.dumps(causal_links, ensure_ascii=False, indent=2)}

【输出语言强制要求】：
无论你参考的上下文、工具描述或知识块是何种语言，你输出的最终诊断报告（尤其是"根因名称"和"根因描述"字段）**必须全部翻译为流畅且专业的中文**。
例如：不要输出 "too_many_index"，请输出 "索引过多"；不要输出英文描述，请翻译成中文解释。

请输出最终诊断报告。
"""
        
        try:
            if hasattr(self.llm_client, 'invoke'):
                response = self.llm_client.invoke(review_prompt)
                return response.content if hasattr(response, 'content') else str(response)
            elif hasattr(self.llm_client, 'generate'):
                return self.llm_client.generate(review_prompt)
            else:
                return self._generate_structured_report(
                    anomaly_alert, conflicts, evidence_validation,
                    causal_links, merged_root_causes, merged_solutions
                )
        except Exception as e:
            print(f"⚠️ LLM报告生成失败: {e}")
            return self._generate_structured_report(
                anomaly_alert, conflicts, evidence_validation,
                causal_links, merged_root_causes, merged_solutions
            )
    
    def _generate_structured_report(
        self,
        anomaly_alert: str,
        conflicts: List[Dict],
        evidence_validation: Dict,
        causal_links: List[Dict],
        merged_root_causes: List[Dict],
        merged_solutions: List[Dict]
    ) -> str:
        """
        @brief 生成结构化的诊断报告（不依赖LLM）
        @return: Markdown格式的报告
        """
        report_lines = [
            "# 数据库诊断综合报告",
            "",
            f"**诊断时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**参与专家数**: {len(self.expert_reports)}",
            f"**最强证据专家**: {evidence_validation.get('strongest_expert', 'N/A')}",
            "",
            "## 一、异常描述",
            "",
            anomaly_alert,
            "",
            "## 二、专家诊断汇总",
            ""
        ]
        
        for report in self.expert_reports:
            report_lines.extend([
                f"### {report.expert_name} ({report.expert_type})",
                f"- **结论**: {report.conclusion}",
                f"- **置信度**: {report.confidence:.2%}",
                f"- **使用工具**: {', '.join(report.tools_used) if report.tools_used else '无'}",
                ""
            ])
        
        if conflicts:
            report_lines.extend([
                "## 三、冲突识别",
                ""
            ])
            for i, conflict in enumerate(conflicts, 1):
                report_lines.extend([
                    f"### 冲突 {i}",
                    f"- **类型**: {conflict.get('type', '未知')}",
                    f"- **涉及专家**: {conflict.get('expert1', '')} vs {conflict.get('expert2', '')}",
                    f"- **描述**: {conflict.get('conflict_description', '')}",
                    ""
                ])
        
        if causal_links:
            report_lines.extend([
                "## 四、因果链分析",
                ""
            ])
            for link in causal_links:
                report_lines.extend([
                    f"- **关联根因**: {', '.join(link.get('linked_causes', []))}",
                    f"- **解释**: {link.get('explanation', '')}",
                    ""
                ])
        
        report_lines.extend([
            "## 五、最终根因",
            ""
        ])
        
        for i, rc in enumerate(merged_root_causes[:3], 1):
            primary_mark = " ⭐ [主要根因]" if rc.get('is_primary') else ""
            report_lines.extend([
                f"### {i}. {rc.get('type', 'Unknown')}{primary_mark}",
                f"- **描述**: {rc.get('description', '')}",
                f"- **置信度**: {rc.get('confidence', 0):.2%}",
                f"- **支持专家**: {', '.join(rc.get('supporting_experts', []))}",
                ""
            ])
        
        report_lines.extend([
            "## 六、解决方案建议",
            ""
        ])
        
        for i, sol in enumerate(merged_solutions[:3], 1):
            report_lines.extend([
                f"### {i}. {sol.get('action', 'Unknown')}",
                f"- **说明**: {sol.get('explanation', '')}",
                f"- **支持专家**: {', '.join(sol.get('supporting_experts', []))}",
                ""
            ])
        
        report_lines.extend([
            "---",
            f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        ])
        
        return "\n".join(report_lines)


def create_reporter_agent(llm_client=None) -> ReporterAgent:
    """
    @brief 创建报告生成器的工厂函数
    @param llm_client: LLM客户端
    @return: ReporterAgent实例
    """
    return ReporterAgent(llm_client=llm_client)


def run_cross_review(
    expert_reports: List[Dict],
    anomaly_alert: str,
    llm_client=None
) -> Dict:
    """
    @brief 执行交叉审查的便捷函数
    @param expert_reports: 专家报告列表
    @param anomaly_alert: 异常告警
    @param llm_client: LLM客户端
    @return: 交叉审查结果
    """
    reporter = ReporterAgent(llm_client=llm_client)
    
    for report in expert_reports:
        reporter.add_expert_report_dict(report)
    
    return reporter.cross_review_and_merge(anomaly_alert)
