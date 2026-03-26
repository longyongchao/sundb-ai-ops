#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@File    : sentence_embedding.py
@Author  : D-Bot Team
@Date    : 2024/01/01
@Desc    : Sentence-BERT 语义向量匹配模块
            Reference: D-Bot Paper Section 5.2 - API Retrieval
            
            数学理论支撑：
            1. 余弦相似度计算:
               sim(s, t_j) = emb(s) · emb(t_j) / (||emb(s)||_2 · ||emb(t_j)||_2)
            
            2. 交叉熵损失函数（模型微调）:
               L = -Σ[y_ij·log(p_ij) + (1-y_ij)·log(1-p_ij)]
"""
import os
import json
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("⚠️ sentence-transformers 未安装，将使用备用匹配方案")

try:
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class ToolRetriever:
    """
    @class ToolRetriever
    @brief 基于Sentence-BERT的工具语义检索器
    @reference D-Bot Paper Section 5.2 - API Retrieval
    
    实现论文中的语义向量匹配算法：
    1. 使用Sentence-BERT将工具描述编码为高维向量
    2. 计算异常上下文与工具向量的余弦相似度
    3. 返回Top-K最匹配的工具
    
    数学公式：
    sim(s, t_j) = emb(s) · emb(t_j) / (||emb(s)||_2 · ||emb(t_j)||_2)
    """
    
    DEFAULT_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'
    
    def __init__(self, model_name: str = None, use_fallback: bool = True):
        """
        @brief 初始化工具检索器
        @param model_name: Sentence-BERT模型名称
        @param use_fallback: 是否在模型不可用时使用备用方案
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.model = None
        self.use_fallback = use_fallback
        
        self.tools_corpus: List[str] = []
        self.tools_embeddings: Optional[np.ndarray] = None
        self.tool_metadata: List[Dict] = []
        
        self._initialize_model()
    
    def _initialize_model(self):
        """
        @brief 初始化Sentence-BERT模型
        @note 优先使用多语言模型，支持中英文混合场景
        """
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            if self.use_fallback:
                print("⚠️ Sentence-BERT不可用，将使用关键词匹配备用方案")
            return
        
        try:
            print(f"🔄 正在加载Sentence-BERT模型: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            print(f"✅ Sentence-BERT模型加载成功")
        except Exception as e:
            print(f"❌ Sentence-BERT模型加载失败: {e}")
            if self.use_fallback:
                print("⚠️ 将使用关键词匹配备用方案")
    
    def build_index(self, tools: List[Dict]) -> bool:
        """
        @brief 构建工具向量索引
        @param tools: 工具列表，格式: [{'name': 'get_cpu', 'desc': '获取CPU利用率', ...}, ...]
        @return: 是否成功构建索引
        
        @reference D-Bot Paper Section 5.2 - Tool Index Construction
        """
        if not tools:
            print("⚠️ 工具列表为空，无法构建索引")
            return False
        
        self.tool_metadata = tools
        self.tools_corpus = []
        
        for tool in tools:
            desc_parts = [
                tool.get('name', ''),
                tool.get('desc', tool.get('description', '')),
                tool.get('display_name', ''),
                ' '.join(tool.get('keywords', []))
            ]
            corpus_text = ' '.join([p for p in desc_parts if p])
            self.tools_corpus.append(corpus_text)
        
        if self.model is not None:
            try:
                print(f"🔄 正在编码 {len(self.tools_corpus)} 个工具描述...")
                self.tools_embeddings = self.model.encode(
                    self.tools_corpus,
                    convert_to_numpy=True,
                    show_progress_bar=False
                )
                print(f"✅ 工具向量索引构建完成，维度: {self.tools_embeddings.shape}")
                return True
            except Exception as e:
                print(f"❌ 工具向量编码失败: {e}")
                self.tools_embeddings = None
        
        return self.use_fallback
    
    def retrieve_tools(
        self, 
        anomaly_context: str, 
        top_k: int = 3,
        threshold: float = 0.3
    ) -> List[Dict]:
        """
        @brief 根据异常上下文检索最匹配的工具
        @param anomaly_context: 异常上下文描述
        @param top_k: 返回的最大工具数量
        @param threshold: 相似度阈值
        @return: 匹配的工具列表
        
        @reference D-Bot Paper Section 5.2 - Semantic Matching
        
        数学公式：
        sim(s, t_j) = emb(s) · emb(t_j) / (||emb(s)||_2 · ||emb(t_j)||_2)
        """
        if not self.tools_corpus:
            print("⚠️ 工具索引未构建，请先调用 build_index()")
            return []
        
        if self.model is not None and self.tools_embeddings is not None:
            return self._semantic_retrieve(anomaly_context, top_k, threshold)
        elif self.use_fallback:
            return self._keyword_retrieve(anomaly_context, top_k)
        else:
            return []
    
    def _semantic_retrieve(
        self, 
        anomaly_context: str, 
        top_k: int,
        threshold: float
    ) -> List[Dict]:
        """
        @brief 基于语义向量的工具检索
        @param anomaly_context: 异常上下文
        @param top_k: 返回数量
        @param threshold: 相似度阈值
        @return: 匹配工具列表
        """
        try:
            query_embedding = self.model.encode(
                [anomaly_context],
                convert_to_numpy=True,
                show_progress_bar=False
            )
            
            if SKLEARN_AVAILABLE:
                similarities = cosine_similarity(query_embedding, self.tools_embeddings)[0]
            else:
                similarities = self._compute_cosine_similarity(
                    query_embedding[0], 
                    self.tools_embeddings
                )
            
            top_k = min(top_k, len(similarities))
            top_k_indices = np.argsort(similarities)[-top_k:][::-1]
            
            matched_tools = []
            for idx in top_k_indices:
                sim_score = float(similarities[idx])
                if sim_score >= threshold:
                    matched_tools.append({
                        "tool_info": self.tool_metadata[idx],
                        "similarity_score": round(sim_score, 4),
                        "match_type": "semantic",
                        "corpus_text": self.tools_corpus[idx]
                    })
            
            return matched_tools
            
        except Exception as e:
            print(f"❌ 语义检索失败: {e}")
            return self._keyword_retrieve(anomaly_context, top_k)
    
    def _keyword_retrieve(self, anomaly_context: str, top_k: int) -> List[Dict]:
        """
        @brief 基于关键词的备用检索方案
        @param anomaly_context: 异常上下文
        @param top_k: 返回数量
        @return: 匹配工具列表
        """
        context_lower = anomaly_context.lower()
        keyword_scores = []
        
        for i, corpus in enumerate(self.tools_corpus):
            corpus_lower = corpus.lower()
            score = 0
            for word in context_lower.split():
                if word in corpus_lower:
                    score += 1
            keyword_scores.append((i, score))
        
        keyword_scores.sort(key=lambda x: x[1], reverse=True)
        
        matched_tools = []
        for idx, score in keyword_scores[:top_k]:
            if score > 0:
                matched_tools.append({
                    "tool_info": self.tool_metadata[idx],
                    "similarity_score": round(score / 10.0, 4),
                    "match_type": "keyword",
                    "corpus_text": self.tools_corpus[idx]
                })
        
        return matched_tools
    
    def _compute_cosine_similarity(
        self, 
        query_vec: np.ndarray, 
        corpus_matrix: np.ndarray
    ) -> np.ndarray:
        """
        @brief 手动计算余弦相似度
        @param query_vec: 查询向量
        @param corpus_matrix: 语料矩阵
        @return: 相似度数组
        """
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return np.zeros(len(corpus_matrix))
        
        query_normalized = query_vec / query_norm
        
        corpus_norms = np.linalg.norm(corpus_matrix, axis=1, keepdims=True)
        corpus_norms[corpus_norms == 0] = 1
        corpus_normalized = corpus_matrix / corpus_norms
        
        similarities = np.dot(corpus_normalized, query_normalized)
        return similarities
    
    def get_tool_embedding(self, tool_name: str) -> Optional[np.ndarray]:
        """
        @brief 获取指定工具的向量表示
        @param tool_name: 工具名称
        @return: 工具向量
        """
        if self.tools_embeddings is None:
            return None
        
        for i, tool in enumerate(self.tool_metadata):
            if tool.get('name') == tool_name:
                return self.tools_embeddings[i]
        
        return None
    
    def compute_tool_similarity(self, tool_name_1: str, tool_name_2: str) -> float:
        """
        @brief 计算两个工具之间的相似度
        @param tool_name_1: 工具1名称
        @param tool_name_2: 工具2名称
        @return: 相似度分数
        """
        emb1 = self.get_tool_embedding(tool_name_1)
        emb2 = self.get_tool_embedding(tool_name_2)
        
        if emb1 is None or emb2 is None:
            return 0.0
        
        if SKLEARN_AVAILABLE:
            return float(cosine_similarity([emb1], [emb2])[0, 0])
        else:
            return float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2)))


class KnowledgeRetriever:
    """
    @class KnowledgeRetriever
    @brief 基于Sentence-BERT的知识块检索器
    @reference D-Bot Paper Section 5.1 - Knowledge Retrieval
    
    扩展工具检索能力到知识库领域，支持：
    1. 根因知识块语义匹配
    2. 专家领域知识检索
    3. 跨语言知识检索
    """
    
    def __init__(self, model_name: str = None):
        """
        @brief 初始化知识检索器
        @param model_name: 模型名称
        """
        self.tool_retriever = ToolRetriever(model_name=model_name)
        self.knowledge_chunks: List[Dict] = []
        self.knowledge_embeddings: Optional[np.ndarray] = None
    
    def build_knowledge_index(self, knowledge_chunks: List) -> bool:
        """
        @brief 构建知识块向量索引
        @param knowledge_chunks: 知识块列表
        @return: 是否成功
        """
        if not knowledge_chunks:
            return False
        
        self.knowledge_chunks = []
        corpus = []
        
        for chunk in knowledge_chunks:
            chunk_dict = chunk.to_dict() if hasattr(chunk, 'to_dict') else chunk
            
            text_parts = [
                chunk_dict.get('cause_name', ''),
                chunk_dict.get('description', ''),
                ' '.join(chunk_dict.get('metrics', [])),
                ' '.join(chunk_dict.get('steps', []))
            ]
            corpus_text = ' '.join([p for p in text_parts if p])
            
            self.knowledge_chunks.append(chunk_dict)
            corpus.append(corpus_text)
        
        if self.tool_retriever.model is not None:
            try:
                self.knowledge_embeddings = self.tool_retriever.model.encode(
                    corpus,
                    convert_to_numpy=True,
                    show_progress_bar=False
                )
                print(f"✅ 知识块向量索引构建完成: {len(self.knowledge_chunks)} 条")
                return True
            except Exception as e:
                print(f"❌ 知识块向量编码失败: {e}")
        
        return False
    
    def retrieve_knowledge(
        self, 
        query: str, 
        top_k: int = 5,
        threshold: float = 0.2
    ) -> List[Dict]:
        """
        @brief 检索相关知识块
        @param query: 查询文本
        @param top_k: 返回数量
        @param threshold: 相似度阈值
        @return: 匹配的知识块列表
        """
        if self.knowledge_embeddings is None or not self.knowledge_chunks:
            return []
        
        try:
            query_embedding = self.tool_retriever.model.encode(
                [query],
                convert_to_numpy=True,
                show_progress_bar=False
            )
            
            if SKLEARN_AVAILABLE:
                similarities = cosine_similarity(query_embedding, self.knowledge_embeddings)[0]
            else:
                similarities = self.tool_retriever._compute_cosine_similarity(
                    query_embedding[0],
                    self.knowledge_embeddings
                )
            
            top_k = min(top_k, len(similarities))
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            results = []
            for idx in top_indices:
                sim_score = float(similarities[idx])
                if sim_score >= threshold:
                    result = self.knowledge_chunks[idx].copy()
                    result['semantic_score'] = round(sim_score, 4)
                    result['match_type'] = 'semantic'
                    results.append(result)
            
            return results
            
        except Exception as e:
            print(f"❌ 知识检索失败: {e}")
            return []


def create_tool_retriever(tools: List[Dict] = None, model_name: str = None) -> ToolRetriever:
    """
    @brief 创建工具检索器的工厂函数
    @param tools: 工具列表
    @param model_name: 模型名称
    @return: ToolRetriever实例
    """
    retriever = ToolRetriever(model_name=model_name)
    
    if tools:
        retriever.build_index(tools)
    
    return retriever


def get_default_diagnosis_tools() -> List[Dict]:
    """
    @brief 获取默认的诊断工具列表
    @return: 工具列表
    """
    return [
        {
            "name": "obtain_metric_values",
            "desc": "获取数据库系统指标，包括CPU使用率、内存使用率、I/O统计等",
            "display_name": "获取系统指标",
            "keywords": ["cpu", "memory", "io", "metrics", "指标", "性能"]
        },
        {
            "name": "query_pg_stat_statements",
            "desc": "查询pg_stat_statements视图，获取慢查询统计信息",
            "display_name": "查询SQL执行统计",
            "keywords": ["slow", "query", "sql", "慢查询", "统计"]
        },
        {
            "name": "explain_query",
            "desc": "分析指定查询的执行计划，识别性能瓶颈",
            "display_name": "分析SQL执行计划",
            "keywords": ["explain", "plan", "执行计划", "分析"]
        },
        {
            "name": "check_lock_status",
            "desc": "检查数据库锁状态，识别锁竞争和死锁问题",
            "display_name": "检查锁状态",
            "keywords": ["lock", "deadlock", "锁", "死锁", "阻塞"]
        },
        {
            "name": "get_database_size",
            "desc": "获取数据库和各表的存储大小信息",
            "display_name": "获取数据库大小",
            "keywords": ["size", "storage", "大小", "存储"]
        },
        {
            "name": "check_active_sessions",
            "desc": "检查当前活跃的数据库会话，识别长时间运行的查询",
            "display_name": "检查活跃会话",
            "keywords": ["session", "active", "会话", "活跃", "连接"]
        },
        {
            "name": "check_storage_stats",
            "desc": "检查表和索引的存储统计，识别死元组和膨胀问题",
            "display_name": "检查存储统计",
            "keywords": ["storage", "tuple", "dead", "存储", "死元组"]
        },
        {
            "name": "optimize_index_selection",
            "desc": "分析表并给出索引优化建议",
            "display_name": "索引优化建议",
            "keywords": ["index", "optimize", "索引", "优化"]
        }
    ]


_default_retriever: Optional[ToolRetriever] = None


def sentence_embedding(text: str, model_name: str = None) -> np.ndarray:
    """
    @brief 获取文本的语义嵌入向量（兼容旧接口）
    @param text: 输入文本
    @param model_name: 模型名称（可选）
    @return: 嵌入向量
    
    @note 此函数用于兼容现有代码中的 sentence_embedding 调用
    """
    global _default_retriever
    
    if _default_retriever is None:
        _default_retriever = ToolRetriever(model_name=model_name)
    
    if _default_retriever.model is None:
        return np.zeros(384)
    
    try:
        embedding = _default_retriever.model.encode([text], convert_to_numpy=True)
        return embedding[0]
    except Exception as e:
        print(f"⚠️ 获取文本嵌入失败: {e}")
        return np.zeros(384)


def get_text_similarity(text1: str, text2: str) -> float:
    """
    @brief 计算两个文本之间的语义相似度
    @param text1: 文本1
    @param text2: 文本2
    @return: 相似度分数 (0-1)
    """
    emb1 = sentence_embedding(text1)
    emb2 = sentence_embedding(text2)
    
    if SKLEARN_AVAILABLE:
        return float(cosine_similarity([emb1], [emb2])[0, 0])
    else:
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(emb1, emb2) / (norm1 * norm2))
