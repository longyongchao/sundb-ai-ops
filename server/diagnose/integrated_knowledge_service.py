"""
集成知识服务 - 将增强知识库集成到诊断流程中
Reference: D-Bot Paper Section 5.1 - Knowledge Integration

实现功能：
1. 集成 BM25 + 语义搜索到树搜索
2. 集成到多专家协作机制
3. 动态知识检索和上下文构建
"""
import json
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# 导入现有组件
from server.diagnose.enhanced_knowledge_loader import (
    EnhancedKnowledgeLoader, 
    search_knowledge, 
    search_knowledge_by_category,
    HybridKnowledgeRetriever
)
from server.diagnose.collaborative_executor import ExpertAssigner, ExpertType
from server.utils import get_ChatOpenAI
from configs import TEMPERATURE, MAX_TOKENS


@dataclass
class KnowledgeContext:
    """知识上下文"""
    relevant_chunks: List[Dict]
    bm25_matches: List[Dict]
    semantic_matches: List[Dict]
    hybrid_score: float
    category_matches: Dict[str, List[Dict]]
    
    def to_prompt_text(self) -> str:
        """转换为提示文本"""
        prompt_parts = []
        
        if self.relevant_chunks:
            prompt_parts.append("【相关知识块】")
            for i, result in enumerate(self.relevant_chunks[:3]):
                chunk = result["chunk"]
                prompt_parts.append(f"""
知识块 {i+1} (匹配度: {result['hybrid_score']:.3f}):
- 名称: {chunk.cause_name}
- 描述: {chunk.description}
- 指标: {', '.join(chunk.metrics)}
- 步骤: {chunk.steps}
- 类别: {chunk.category}
""")
        
        if self.category_matches:
            prompt_parts.append("【类别相关分析】")
            for category, matches in self.category_matches.items():
                if matches:
                    prompt_parts.append(f"- {category}类问题: {len(matches)}个匹配")
        
        return "\n".join(prompt_parts)


class IntegratedKnowledgeService:
    """集成知识服务"""
    
    def __init__(self):
        self.loader = EnhancedKnowledgeLoader()
        self.expert_assigner = ExpertAssigner()
        self._loaded = False
        
        # 加载知识库
        self.load()
    
    def load(self) -> bool:
        """加载知识库"""
        if self._loaded:
            return True
        
        success = self.loader.load()
        if success:
            self._loaded = True
            print("[OK] 集成知识服务初始化成功")
        else:
            print("[ERROR] 集成知识服务初始化失败")
        
        return success
    
    def retrieve_knowledge_for_diagnosis(self, anomaly_info: Dict, expert_type: Optional[ExpertType] = None) -> KnowledgeContext:
        """
        为诊断检索相关知识
        """
        query = self._build_diagnosis_query(anomaly_info, expert_type)
        
        # 基础混合搜索
        relevant_chunks = search_knowledge(query, top_k=5, use_hybrid=True)
        
        # 按类别搜索（如果有专家类型）
        category_matches = {}
        if expert_type:
            category = self._expert_to_category(expert_type)
            category_matches[category] = search_knowledge_by_category(query, category, top_k=3)
        
        # 分离 BM25 和语义匹配
        bm25_matches = [r for r in relevant_chunks if "bm25" in r.get("match_types", [])]
        semantic_matches = [r for r in relevant_chunks if "semantic" in r.get("match_types", [])]
        
        # 计算平均混合分数
        hybrid_score = sum(r["hybrid_score"] for r in relevant_chunks) / len(relevant_chunks) if relevant_chunks else 0
        
        return KnowledgeContext(
            relevant_chunks=relevant_chunks,
            bm25_matches=bm25_matches,
            semantic_matches=semantic_matches,
            hybrid_score=hybrid_score,
            category_matches=category_matches
        )
    
    def _build_diagnosis_query(self, anomaly_info: Dict, expert_type: Optional[ExpertType] = None) -> str:
        """构建诊断查询"""
        query_parts = [
            anomaly_info.get("alert_type", ""),
            anomaly_info.get("description", "")
        ]
        
        # 添加专家类型关键词
        if expert_type:
            expert_keywords = {
                ExpertType.CPU: ["CPU", "进程", "负载", "使用率"],
                ExpertType.MEMORY: ["内存", "mem", "交换", "缓存"],
                ExpertType.IO: ["io", "磁盘", "存储", "文件系统"],
                ExpertType.WORKLOAD: ["查询", "锁", "连接", "事务"],
                ExpertType.DATABASE: ["索引", "表结构", "配置", "架构"]
            }
            query_parts.extend(expert_keywords.get(expert_type, []))
        
        # 组合查询
        query = " ".join(part for part in query_parts if part.strip())
        return query
    
    def _expert_to_category(self, expert_type: ExpertType) -> str:
        """专家类型转换为类别"""
        mapping = {
            ExpertType.CPU: "cpu",
            ExpertType.MEMORY: "memory",
            ExpertType.IO: "io",
            ExpertType.WORKLOAD: "general",
            ExpertType.DATABASE: "index"
        }
        return mapping.get(expert_type, "general")
    
    def build_enhanced_reasoning_prompt(self, anomaly_info: Dict, knowledge_context: KnowledgeContext, history: List[Dict] = None) -> str:
        """
        构建增强推理提示
        """
        # 基础提示
        base_prompt = f"""
你是一个专业的数据库诊断专家，请基于以下信息进行推理分析：

【异常信息】
- 类型: {anomaly_info.get('alert_type', '未知')}
- 描述: {anomaly_info.get('description', '无描述')}
- 严重程度: {anomaly_info.get('severity', '中等')}

"""
        
        # 添加知识上下文
        if knowledge_context.relevant_chunks:
            base_prompt += knowledge_context.to_prompt_text()
        
        # 添加历史路径
        if history and len(history) > 0:
            base_prompt += "\n【历史推理路径】\n"
            for i, step in enumerate(history[-3:]):  # 只使用最近3步
                base_prompt += f"""
步骤 {step.get('step', 0)}:
- 思路: {step.get('thought', '')}
- 动作: {step.get('action', '')}
- 观察: {step.get('observation', '')}
"""
        
        # 添加推理指导
        base_prompt += """

【推理指导】
1. 结合相关知识块进行分析，重点关注高匹配度(>0.8)的知识
2. 如果多个知识块结论一致，则增加置信度
3. 如果知识块存在矛盾，优先选择专家相关的类别
4. 结合历史路径避免重复推理
5. 优先考虑最可能的根因，同时考虑其他可能性

请按照以下格式输出你的推理：
Thought: [你的分析思路，考虑异常特征、相关知识和历史路径]
Action: [选择合适的工具，可选: obtain_metric_values, query_pg_stat_statements, explain_query, optimize_index_selection, check_lock_status, get_database_size, Finish]
Action Input: [工具参数，JSON格式]
"""
        
        return base_prompt
    
    def generate_knowledge_insights(self, anomaly_info: Dict, knowledge_context: KnowledgeContext) -> Dict:
        """
        生成知识洞察
        """
        if not knowledge_context.relevant_chunks:
            return {
                "insights": ["未找到相关知识，建议检查异常描述是否准确"],
                "confidence": 0.0,
                "recommendations": ["请提供更详细的异常信息"]
            }
        
        # 分析知识匹配情况
        insights = []
        high_confidence_chunks = [r for r in knowledge_context.relevant_chunks if r["hybrid_score"] > 0.8]
        medium_confidence_chunks = [r for r in knowledge_context.relevant_chunks if 0.5 <= r["hybrid_score"] <= 0.8]
        
        if high_confidence_chunks:
            insights.append(f"发现 {len(high_confidence_chunks)} 个高置信度({knowledge_context.hybrid_score:.2f})相关知识")
        
        if medium_confidence_chunks:
            insights.append(f"发现 {len(medium_confidence_chunks)} 个中等置信度相关知识")
        
        # 分析类别分布
        if knowledge_context.category_matches:
            for category, matches in knowledge_context.category_matches.items():
                if matches:
                    insights.append(f"{category}类问题有 {len(matches)} 个匹配")
        
        # 生成建议
        recommendations = []
        if not high_confidence_chunks:
            recommendations.append("建议检查异常描述是否准确，或提供更多上下文")
        
        if len(knowledge_context.relevant_chunks) < 3:
            recommendations.append("相关知识较少，建议扩展知识库")
        
        recommendations.append("基于现有知识进行诊断，但可能需要进一步验证")
        
        return {
            "insights": insights,
            "confidence": knowledge_context.hybrid_score,
            "recommendations": recommendations,
            "matched_count": len(knowledge_context.relevant_chunks),
            "high_confidence_count": len(high_confidence_chunks)
        }
    
    def cross_validate_with_knowledge(self, diagnosis_result: Dict, knowledge_context: KnowledgeContext) -> Dict:
        """
        使用知识库交叉验证诊断结果
        """
        validation_result = {
            "validated": True,
            "confidence": diagnosis_result.get("confidence", 0.5),
            "validation_details": [],
            "suggestions": []
        }
        
        # 检查诊断结果与知识的匹配度
        root_causes = diagnosis_result.get("root_causes", [])
        
        for cause in root_causes:
            cause_type = cause.get("type", "")
            cause_description = cause.get("description", "")
            
            # 在知识库中查找匹配的根因
            matching_chunks = []
            for result in knowledge_context.relevant_chunks:
                chunk = result["chunk"]
                if (cause_type.lower() in chunk.cause_name.lower() or 
                    cause_type.lower() in chunk.description.lower() or
                    any(keyword in cause_description.lower() for keyword in chunk.metrics)):
                    matching_chunks.append((chunk, result["hybrid_score"]))
            
            if matching_chunks:
                best_match = max(matching_chunks, key=lambda x: x[1])
                validation_result["validation_details"].append({
                    "root_cause": cause_type,
                    "knowledge_match": best_match[0].cause_name,
                    "match_score": best_match[1],
                    "status": "validated"
                })
            else:
                validation_result["validation_details"].append({
                    "root_cause": cause_type,
                    "knowledge_match": None,
                    "match_score": 0,
                    "status": "no_knowledge_support"
                })
                validation_result["suggestions"].append(f"根因 '{cause_type}' 缺少知识库支持，建议进一步验证")
        
        # 计算总体验证分数
        total_match_score = sum(detail["match_score"] for detail in validation_result["validation_details"])
        validation_result["confidence"] = min(1.0, validation_result["confidence"] + total_match_score / len(root_causes) * 0.2)
        
        return validation_result


# 全局实例
integrated_knowledge_service = IntegratedKnowledgeService()


def get_knowledge_context(anomaly_info: Dict, expert_type: Optional[str] = None) -> KnowledgeContext:
    """获取知识上下文"""
    from server.diagnose.collaborative_executor import ExpertType
    
    expert_enum = None
    if expert_type:
        try:
            expert_enum = ExpertType(expert_type)
        except ValueError:
            pass
    
    return integrated_knowledge_service.retrieve_knowledge_for_diagnosis(anomaly_info, expert_enum)


def build_enhanced_prompt(anomaly_info: Dict, knowledge_context: KnowledgeContext, history: List[Dict] = None) -> str:
    """构建增强提示"""
    return integrated_knowledge_service.build_enhanced_reasoning_prompt(anomaly_info, knowledge_context, history)


def generate_knowledge_insights(anomaly_info: Dict, knowledge_context: KnowledgeContext) -> Dict:
    """生成知识洞察"""
    return integrated_knowledge_service.generate_knowledge_insights(anomaly_info, knowledge_context)


def cross_validate_diagnosis(diagnosis_result: Dict, knowledge_context: KnowledgeContext) -> Dict:
    """交叉验证诊断结果"""
    return integrated_knowledge_service.cross_validate_with_knowledge(diagnosis_result, knowledge_context)


# 测试函数
def test_integrated_knowledge_service():
    """测试集成知识服务"""
    print("🧪 测试集成知识服务...")
    
    # 测试异常信息
    test_anomaly = {
        "alert_type": "CPU High",
        "description": "CPU使用率异常升高至95%，系统响应缓慢，查询性能下降",
        "severity": "high"
    }
    
    # 获取知识上下文
    context = get_knowledge_context(test_anomaly)
    
    print(f"\n[STATS] 知识匹配结果:")
    print(f"- 相关知识块: {len(context.relevant_chunks)}")
    print(f"- BM25匹配: {len(context.bm25_matches)}")
    print(f"- 语义匹配: {len(context.semantic_matches)}")
    print(f"- 混合分数: {context.hybrid_score:.3f}")
    
    # 生成知识洞察
    insights = generate_knowledge_insights(test_anomaly, context)
    print(f"\n[SEARCH] 知识洞察:")
    for insight in insights["insights"]:
        print(f"  - {insight}")
    print(f"置信度: {insights['confidence']:.3f}")
    
    # 构建增强提示
    prompt = build_enhanced_prompt(test_anomaly, context)
    print(f"\n📝 增强提示 (前500字符):")
    print(prompt[:500] + "...")
    
    # 模拟诊断结果验证
    mock_diagnosis = {
        "root_causes": [
            {"type": "CPU Issue", "description": "CPU使用率过高", "confidence": 0.8}
        ],
        "confidence": 0.8
    }
    
    validation = cross_validate_diagnosis(mock_diagnosis, context)
    print(f"\n[OK] 交叉验证结果:")
    print(f"- 验证状态: {validation['validated']}")
    print(f"- 最终置信度: {validation['confidence']:.3f}")
    for detail in validation["validation_details"]:
        print(f"- {detail['root_cause']}: {detail['status']} (分数: {detail['match_score']:.3f})")


if __name__ == "__main__":
    test_integrated_knowledge_service()
