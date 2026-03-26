#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : semantic_matcher.py
@Author  : LI
@Date    : 2026
@Desc    : 语义工具匹配器
            Reference: D-Bot Paper Section 5.1 - Tool Retrieval
            
            实现基于向量相似度的工具检索：
            1. 使用 TF-IDF 或 Sentence-BERT 进行语义编码
            2. 使用余弦相似度进行工具匹配
            3. 替换原有的硬编码关键词匹配
"""
import os
import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import numpy as np

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("[WARNING] sklearn 未安装，将使用简化匹配算法")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("[INFO] sentence-transformers 未安装，使用 TF-IDF 替代")


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    keywords: List[str]
    category: str
    parameters: Dict
    
    def get_text_for_embedding(self) -> str:
        """获取用于嵌入的文本"""
        return f"{self.name}: {self.description}. Keywords: {', '.join(self.keywords)}"


class SemanticToolMatcher:
    """
    @class SemanticToolMatcher
    @brief 语义工具匹配器
    @reference D-Bot Paper Section 5.1 - Tool Retrieval
    
    支持两种模式：
    1. Sentence-BERT 模式（推荐，需要安装 sentence-transformers）
    2. TF-IDF 模式（降级方案，需要安装 sklearn）
    3. 简化模式（无依赖，仅关键词匹配）
    """
    
    # 预定义的诊断工具
    DEFAULT_TOOLS = [
        ToolDefinition(
            name="check_active_sessions",
            description="检查长时间运行的活跃数据库会话，识别阻塞或长时间执行的查询",
            keywords=["CPU", "会话", "进程", "活跃", "阻塞", "长时间"],
            category="session",
            parameters={"threshold_seconds": 60}
        ),
        ToolDefinition(
            name="get_slow_queries",
            description="获取执行缓慢的SQL查询，分析查询性能问题",
            keywords=["查询", "SQL", "慢查询", "性能", "执行时间"],
            category="query",
            parameters={"top_n": 5, "threshold_ms": 100}
        ),
        ToolDefinition(
            name="check_locks",
            description="检查数据库锁等待情况，识别锁竞争和死锁",
            keywords=["锁", "等待", "阻塞", "死锁", "竞争", "lock"],
            category="lock",
            parameters={}
        ),
        ToolDefinition(
            name="check_storage_stats",
            description="检查数据库存储统计，包括表大小、死元组、索引膨胀",
            keywords=["存储", "磁盘", "空间", "膨胀", "死元组", "IO"],
            category="storage",
            parameters={}
        ),
        ToolDefinition(
            name="check_memory_usage",
            description="检查数据库内存使用情况，包括缓冲区命中率",
            keywords=["内存", "memory", "缓冲区", "缓存", "命中率"],
            category="memory",
            parameters={}
        ),
        ToolDefinition(
            name="check_index_usage",
            description="检查索引使用情况，识别缺失或冗余索引",
            keywords=["索引", "index", "缺失", "冗余", "扫描"],
            category="index",
            parameters={}
        ),
        ToolDefinition(
            name="analyze_execution_plan",
            description="分析SQL执行计划，识别全表扫描、嵌套循环等问题",
            keywords=["执行计划", "explain", "全表扫描", "成本"],
            category="plan",
            parameters={"query_id": None}
        ),
        ToolDefinition(
            name="Finish",
            description="完成诊断，输出最终结论和建议",
            keywords=["完成", "结束", "结论", "结果", "finish"],
            category="terminal",
            parameters={}
        )
    ]
    
    def __init__(self, tools: List[ToolDefinition] = None, use_bert: bool = True):
        """
        @brief 初始化语义匹配器
        @param tools: 工具列表（默认使用预定义工具）
        @param use_bert: 是否使用 Sentence-BERT（如果可用）
        """
        self.tools = tools or self.DEFAULT_TOOLS
        self.use_bert = use_bert and SENTENCE_TRANSFORMERS_AVAILABLE
        
        self._embeddings: Optional[np.ndarray] = None
        self._vectorizer = None
        self._model = None
        
        self._initialize()
    
    def _initialize(self):
        """初始化嵌入模型"""
        if self.use_bert:
            self._init_bert()
        elif SKLEARN_AVAILABLE:
            self._init_tfidf()
        else:
            print("[INFO] 使用简化关键词匹配模式")
    
    def _init_bert(self):
        """初始化 Sentence-BERT 模型"""
        try:
            # 使用多语言模型，支持中英文
            model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            self._model = SentenceTransformer(model_name)
            
            # 编码所有工具
            texts = [t.get_text_for_embedding() for t in self.tools]
            self._embeddings = self._model.encode(texts)
            
            print(f"[[OK]] Sentence-BERT 初始化成功，已编码 {len(self.tools)} 个工具")
            
        except Exception as e:
            print(f"[WARNING] Sentence-BERT 初始化失败: {e}，降级到 TF-IDF")
            self.use_bert = False
            if SKLEARN_AVAILABLE:
                self._init_tfidf()
    
    def _init_tfidf(self):
        """初始化 TF-IDF 向量化器"""
        texts = [t.get_text_for_embedding() for t in self.tools]
        self._vectorizer = TfidfVectorizer()
        self._embeddings = self._vectorizer.fit_transform(texts).toarray()
        print(f"[[OK]] TF-IDF 初始化成功，已编码 {len(self.tools)} 个工具")
    
    def match(self, query: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """
        @brief 语义匹配工具
        @param query: 查询文本（如异常描述）
        @param top_k: 返回前 k 个匹配结果
        @return: [(工具名称, 相似度分数), ...]
        
        @example
        >>> matcher = SemanticToolMatcher()
        >>> matcher.match("数据库CPU使用率过高", top_k=3)
        [('check_active_sessions', 0.85), ('get_slow_queries', 0.72), ('check_memory_usage', 0.45)]
        """
        if self._embeddings is None:
            return self._simple_match(query, top_k)
        
        # 获取查询向量
        query_vec = self._get_query_vector(query)
        
        # 计算余弦相似度
        similarities = []
        for i, tool_emb in enumerate(self._embeddings):
            sim = np.dot(query_vec, tool_emb) / (
                np.linalg.norm(query_vec) * np.linalg.norm(tool_emb) + 1e-8
            )
            similarities.append((self.tools[i].name, float(sim)))
        
        # 排序并返回 top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def _get_query_vector(self, query: str) -> np.ndarray:
        """获取查询向量"""
        if self.use_bert and self._model:
            return self._model.encode([query])[0]
        elif self._vectorizer:
            return self._vectorizer.transform([query]).toarray()[0]
        else:
            return np.zeros(128)
    
    def _simple_match(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """
        @brief 简化匹配（无依赖时的降级方案）
        """
        query_lower = query.lower()
        scores = []
        
        for tool in self.tools:
            score = 0
            for kw in tool.keywords:
                if kw.lower() in query_lower:
                    score += 1
            
            # 归一化分数
            max_score = len(tool.keywords)
            normalized_score = score / max_score if max_score > 0 else 0
            scores.append((tool.name, normalized_score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """根据名称获取工具定义"""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
    
    def register_tool(self, tool: ToolDefinition):
        """注册新工具"""
        self.tools.append(tool)
        # 重新初始化嵌入
        self._initialize()


class ExpertMatcher:
    """
    @class ExpertMatcher
    @brief 专家匹配器 - 基于语义相似度分配专家
    @reference D-Bot Paper Section 7.1 - Expert Assignment
    """
    
    EXPERT_DEFINITIONS = {
        "cpu_expert": ToolDefinition(
            name="cpu_expert",
            description="CPU专家，专注于CPU使用率、进程调度、负载均衡等问题",
            keywords=["CPU", "进程", "负载", "使用率", "workload", "process"],
            category="expert",
            parameters={}
        ),
        "memory_expert": ToolDefinition(
            name="memory_expert",
            description="内存专家，专注于内存泄漏、缓冲区管理、交换空间等问题",
            keywords=["内存", "memory", "缓冲区", "缓存", "swap", "泄漏"],
            category="expert",
            parameters={}
        ),
        "io_expert": ToolDefinition(
            name="io_expert",
            description="I/O专家，专注于磁盘I/O、存储性能、文件系统等问题",
            keywords=["IO", "磁盘", "存储", "读写", "disk", "storage"],
            category="expert",
            parameters={}
        ),
        "workload_expert": ToolDefinition(
            name="workload_expert",
            description="工作负载专家，专注于查询优化、并发控制、事务处理等问题",
            keywords=["查询", "SQL", "并发", "事务", "workload", "query"],
            category="expert",
            parameters={}
        ),
        "database_expert": ToolDefinition(
            name="database_expert",
            description="数据库专家，专注于数据库配置、架构设计、整体性能等问题",
            keywords=["数据库", "配置", "架构", "database", "config", "参数"],
            category="expert",
            parameters={}
        )
    }
    
    def __init__(self):
        self.matcher = SemanticToolMatcher(
            tools=list(self.EXPERT_DEFINITIONS.values()),
            use_bert=True
        )
    
    def assign_experts(self, anomaly_info: Dict, top_k: int = 2) -> List[Tuple[str, float]]:
        """
        @brief 分配专家
        @param anomaly_info: 异常信息
        @param top_k: 返回前 k 个专家
        @return: [(专家名称, 置信度), ...]
        
        @example
        >>> matcher = ExpertMatcher()
        >>> matcher.assign_experts({"alert_type": "slow_sql", "description": "CPU使用率高"})
        [('cpu_expert', 0.85), ('workload_expert', 0.72)]
        """
        query = f"{anomaly_info.get('alert_type', '')} {anomaly_info.get('description', '')}"
        return self.matcher.match(query, top_k)


# 全局实例
semantic_matcher = SemanticToolMatcher()
expert_matcher = ExpertMatcher()


def match_tools(query: str, top_k: int = 3) -> List[Tuple[str, float]]:
    """
    @brief 便捷函数：匹配工具
    @param query: 查询文本
    @param top_k: 返回数量
    @return: [(工具名称, 相似度), ...]
    """
    return semantic_matcher.match(query, top_k)


def assign_experts(anomaly_info: Dict, top_k: int = 2) -> List[Tuple[str, float]]:
    """
    @brief 便捷函数：分配专家
    @param anomaly_info: 异常信息
    @param top_k: 返回数量
    @return: [(专家名称, 置信度), ...]
    """
    return expert_matcher.assign_experts(anomaly_info, top_k)
