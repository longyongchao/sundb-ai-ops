#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识库加载器 - 诊断知识检索模块

本模块负责加载和管理数据库诊断领域知识，核心功能：
1. 知识加载 - 从 JSONL 文件加载 34 种根因知识
2. BM25 检索 - 基于关键词匹配的快速检索
3. 向量检索 - 基于语义相似度的深度检索
4. 混合检索 - 融合 BM25 和向量检索结果

知识来源：DB-GPT 内置知识库 + 用户上传知识库
"""
import os
import json
import glob
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
from collections import defaultdict

# 新增：BM25和中文分词依赖
try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    print("[WARN] jieba未安装，使用简单分词")

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    print("[WARN] rank_bm25未安装，使用简单关键词匹配")

try:
    from sklearn.preprocessing import MinMaxScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

KNOWLEDGE_BASE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "doc2knowledge",
    "root_causes_dbmind.jsonl"
)

USER_KB_ROOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "knowledge_base"
)


@dataclass
class KnowledgeChunk:
    """
    @class KnowledgeChunk
    @brief 知识块数据类 - 论文四要素完整实现
    @param cause_name: 根因名称 (Name)
    @param description: 根因描述 (Content)
    @param metrics: 相关指标列表 (Metrics)
    @param steps: 诊断步骤列表 (Steps) - 新增第四要素
    @param category: 根因类别（用于层次化组织）
    @param source: 知识来源（内置专家规则/用户上传/外部故障知识库）
    @param embedding: 语义嵌入向量（可选）
    @reference D-Bot Paper Section 4.1 - Knowledge Extraction
    @note 四要素：Name + Content + Metrics + Steps
    """
    cause_name: str
    description: str
    metrics: List[str]
    steps: List[str] = field(default_factory=list)
    category: str = ""
    source: str = "内置专家规则"
    embedding: Optional[np.ndarray] = None
    
    def to_dict(self) -> Dict:
        """
        @brief 转换为字典格式
        @return: 字典格式的知识块（包含四要素）
        """
        return {
            "cause_name": self.cause_name,
            "description": self.description,
            "metrics": self.metrics,
            "steps": self.steps,
            "category": self.category,
            "source": self.source
        }
    
    def get_steps_text(self) -> str:
        """
        @brief 获取步骤的文本描述
        @return: 格式化的步骤文本
        """
        if not self.steps:
            return ""
        return "\n".join([f"{i+1}. {step}" for i, step in enumerate(self.steps)])


@dataclass
class SummaryNode:
    """
    @class SummaryNode
    @brief Summary-Tree 节点
    @reference D-Bot Paper Section 4.1 - Summary-tree
    
    层次化知识组织结构：
    - 顶层：根因类别摘要
    - 中层：具体根因类型
    - 叶层：详细诊断步骤
    """
    summary: str
    keywords: List[str]
    level: int = 0
    children: List['SummaryNode'] = field(default_factory=list)
    knowledge_chunks: List[KnowledgeChunk] = field(default_factory=list)
    centroid: Optional[np.ndarray] = None
    
    def is_leaf(self) -> bool:
        return len(self.children) == 0
    
    def get_all_chunks(self) -> List[KnowledgeChunk]:
        """递归获取所有知识块"""
        chunks = list(self.knowledge_chunks)
        for child in self.children:
            chunks.extend(child.get_all_chunks())
        return chunks
    
    def to_dict(self) -> Dict:
        return {
            "summary": self.summary,
            "keywords": self.keywords,
            "level": self.level,
            "chunk_count": len(self.knowledge_chunks),
            "children": [c.to_dict() for c in self.children]
        }


class KnowledgeLoader:
    """
    @class KnowledgeLoader
    @brief 知识库加载器
    @details 实现知识库的加载、检索与匹配功能
             支持 BM25 风格的关键词检索
    @reference D-Bot Paper Section 4.1 - Knowledge Extraction
    """
    
    def __init__(self, knowledge_path: str = None):
        """
        @brief 初始化知识库加载器
        @param knowledge_path: 知识库文件路径（可选）
        """
        self.knowledge_path = knowledge_path or KNOWLEDGE_BASE_PATH
        self._knowledge_base: List[KnowledgeChunk] = []
        self._loaded = False
        
        # 新增：BM25相关初始化
        self.bm25 = None                # BM25检索器
        self.tokenized_corpus = []      # 分词后的知识库文本
        self.corpus_index_map = {}      # corpus索引→知识块的映射
        self.scaler = None              # 分数归一化器
    
    def load(self) -> bool:
        """
        @brief 加载知识库文件 - 融合加载内置知识 + 用户上传知识
        @return: 加载成功返回 True
        """
        if self._loaded:
            print(f"[DEBUG] 知识库已加载，跳过重复加载")
            return True
        
        builtin_count = 0
        user_count = 0
        
        print(f"[DEBUG] ========== 开始融合加载知识库 ==========")
        
        # 1. 加载内置专家知识（root_causes_dbmind.jsonl）
        builtin_loaded = self._load_builtin_knowledge()
        if builtin_loaded:
            builtin_count = len(self._knowledge_base)
            print(f"[OK] 内置专家知识加载完成: {builtin_count} 条")
        
        # 2. 加载用户上传的知识库文件
        user_loaded = self._load_user_uploaded_knowledge()
        if user_loaded:
            user_count = len(self._knowledge_base) - builtin_count
            print(f"[OK] 用户上传知识加载完成: {user_count} 条")
        
        total_count = len(self._knowledge_base)
        
        if total_count > 0:
            self._loaded = True
            
            # 新增：初始化BM25索引（对齐D-Bot论文Section5.1）
            self._init_bm25_index()
            
            print(f"")
            print(f"╔════════════════════════════════════════════════════════════╗")
            print(f"║  [OK] 知识库融合加载完成                                    ║")
            print(f"║  - 内置专家规则: {builtin_count:>4} 条                              ║")
            print(f"║  - 用户上传知识: {user_count:>4} 条                              ║")
            print(f"║  - 总计知识数量: {total_count:>4} 条                              ║")
            print(f"╚════════════════════════════════════════════════════════════╝")
            print(f"")
            return True
        else:
            print(f"[WARN] 知识库加载失败，无任何知识可用")
            return False

    def _load_builtin_knowledge(self) -> bool:
        """
        @brief 加载内置专家知识（root_causes_dbmind.jsonl）
        @return: 加载成功返回 True
        """
        print(f"[DEBUG] 尝试加载内置知识: {self.knowledge_path}")
        
        if not os.path.exists(self.knowledge_path):
            print(f"[WARNING] 内置知识文件不存在: {self.knowledge_path}")
            return False
        
        try:
            with open(self.knowledge_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"[DEBUG] 成功读取内置 JSON 文件，包含 {len(data) if isinstance(data, list) else '非列表'} 条数据")
            
            count_before = len(self._knowledge_base)
            
            for item in data:
                chunk = KnowledgeChunk(
                    cause_name=item.get("cause_name", ""),
                    description=item.get("desc", item.get("description", "")),
                    metrics=self._parse_metrics(item.get("metrics", "")),
                    steps=self._parse_steps(item.get("steps", item.get("diagnosis_steps", ""))),
                    category="内置专家规则"
                )
                self._knowledge_base.append(chunk)
            
            return True
        except Exception as e:
            import traceback
            print(f"[ERROR] 内置知识加载失败: {e}")
            traceback.print_exc()
            return False

    def _load_user_uploaded_knowledge(self) -> bool:
        """
        @brief 加载用户通过知识库管理界面上传的知识
        @details 遍历 knowledge_base/{kb_name}/content/ 目录下的所有文件
        @return: 加载成功返回 True
        """
        if not os.path.exists(USER_KB_ROOT_PATH):
            print(f"[DEBUG] 用户知识库根目录不存在: {USER_KB_ROOT_PATH}")
            return False
        
        print(f"[DEBUG] 扫描用户知识库目录: {USER_KB_ROOT_PATH}")
        
        count_before = len(self._knowledge_base)
        loaded_files = []
        
        try:
            # 遍历所有知识库目录
            for kb_name in os.listdir(USER_KB_ROOT_PATH):
                kb_path = os.path.join(USER_KB_ROOT_PATH, kb_name)
                
                # 跳过非目录和特殊目录
                if not os.path.isdir(kb_path):
                    continue
                if kb_name.startswith('.') or kb_name == '__pycache__':
                    continue
                
                content_path = os.path.join(kb_path, "content")
                if not os.path.exists(content_path):
                    continue
                
                print(f"[DEBUG] 扫描知识库 [{kb_name}] 的内容目录...")
                
                # 遍历 content 目录下的所有文件
                for file_name in os.listdir(content_path):
                    file_path = os.path.join(content_path, file_name)
                    
                    if not os.path.isfile(file_path):
                        continue
                    
                    # 根据文件类型加载
                    ext = os.path.splitext(file_name)[1].lower()
                    
                    try:
                        if ext == '.jsonl':
                            chunks = self._load_jsonl_file(file_path, kb_name)
                            self._knowledge_base.extend(chunks)
                            loaded_files.append(f"{kb_name}/{file_name} ({len(chunks)}条)")
                        elif ext == '.json':
                            chunks = self._load_json_file(file_path, kb_name)
                            self._knowledge_base.extend(chunks)
                            loaded_files.append(f"{kb_name}/{file_name} ({len(chunks)}条)")
                        elif ext in ['.md', '.markdown']:
                            chunks = self._load_markdown_file(file_path, kb_name)
                            self._knowledge_base.extend(chunks)
                            loaded_files.append(f"{kb_name}/{file_name} ({len(chunks)}条)")
                        elif ext == '.txt':
                            chunks = self._load_text_file(file_path, kb_name)
                            self._knowledge_base.extend(chunks)
                            loaded_files.append(f"{kb_name}/{file_name} ({len(chunks)}条)")
                        elif ext == '.pdf':
                            chunks = self._load_pdf_file(file_path, kb_name)
                            self._knowledge_base.extend(chunks)
                            if chunks:
                                loaded_files.append(f"{kb_name}/{file_name} ({len(chunks)}条)")
                    except Exception as e:
                        print(f"[WARN] 加载文件失败 {kb_name}/{file_name}: {e}")
                        continue
            
            user_count = len(self._knowledge_base) - count_before
            
            if loaded_files:
                print(f"[DEBUG] 用户知识文件加载详情:")
                for f in loaded_files:
                    print(f"       - {f}")
            
            return user_count > 0
            
        except Exception as e:
            import traceback
            print(f"[ERROR] 用户知识库扫描失败: {e}")
            traceback.print_exc()
            return False

    def _load_jsonl_file(self, file_path: str, kb_name: str) -> List['KnowledgeChunk']:
        """加载 JSONL 格式文件"""
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        chunk = KnowledgeChunk(
                            cause_name=item.get("cause_name", f"用户知识_{line_num}"),
                            description=item.get("desc", item.get("description", "")),
                            metrics=self._parse_metrics(item.get("metrics", "")),
                            steps=self._parse_steps(item.get("steps", "")),
                            category=f"用户上传/{kb_name}"
                        )
                        chunks.append(chunk)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"[WARN] JSONL 文件解析失败 {file_path}: {e}")
        return chunks

    def _load_json_file(self, file_path: str, kb_name: str) -> List['KnowledgeChunk']:
        """加载 JSON 格式文件"""
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list):
                for i, item in enumerate(data):
                    chunk = KnowledgeChunk(
                        cause_name=item.get("cause_name", f"用户知识_{i+1}"),
                        description=item.get("desc", item.get("description", "")),
                        metrics=self._parse_metrics(item.get("metrics", "")),
                        steps=self._parse_steps(item.get("steps", "")),
                        category=f"用户上传/{kb_name}"
                    )
                    chunks.append(chunk)
            elif isinstance(data, dict):
                chunk = KnowledgeChunk(
                    cause_name=data.get("cause_name", "用户知识"),
                    description=data.get("desc", data.get("description", "")),
                    metrics=self._parse_metrics(data.get("metrics", "")),
                    steps=self._parse_steps(data.get("steps", "")),
                    category=f"用户上传/{kb_name}"
                )
                chunks.append(chunk)
        except Exception as e:
            print(f"[WARN] JSON 文件解析失败 {file_path}: {e}")
        return chunks

    def _load_markdown_file(self, file_path: str, kb_name: str) -> List['KnowledgeChunk']:
        """加载 Markdown 文件"""
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 按 Markdown 标题分割
            sections = content.split('\n## ')
            
            for i, section in enumerate(sections):
                if not section.strip():
                    continue
                
                lines = section.strip().split('\n')
                title = lines[0].replace('#', '').strip() if lines else f"知识块_{i+1}"
                body = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""
                
                if title or body:
                    chunk = KnowledgeChunk(
                        cause_name=title[:100] if len(title) > 100 else title,
                        description=body[:2000] if len(body) > 2000 else body,
                        metrics=[],
                        steps=[],
                        category=f"用户上传/{kb_name}"
                    )
                    chunks.append(chunk)
        except Exception as e:
            print(f"[WARN] Markdown 文件解析失败 {file_path}: {e}")
        return chunks

    def _load_text_file(self, file_path: str, kb_name: str) -> List['KnowledgeChunk']:
        """加载纯文本文件"""
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 按段落分割（空行分隔）
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            
            if not paragraphs:
                paragraphs = [content.strip()]
            
            for i, para in enumerate(paragraphs):
                if len(para) < 20:  # 过滤太短的段落
                    continue
                
                chunk = KnowledgeChunk(
                    cause_name=f"文本知识_{i+1}",
                    description=para[:2000] if len(para) > 2000 else para,
                    metrics=[],
                    steps=[],
                    category=f"用户上传/{kb_name}"
                )
                chunks.append(chunk)
        except Exception as e:
            print(f"[WARN] 文本文件解析失败 {file_path}: {e}")
        return chunks

    def _load_pdf_file(self, file_path: str, kb_name: str) -> List['KnowledgeChunk']:
        """加载 PDF 文件"""
        chunks = []
        try:
            # 尝试使用 PyPDFLoader
            try:
                from langchain.document_loaders import PyPDFLoader
                loader = PyPDFLoader(file_path)
                docs = loader.load()
                
                for i, doc in enumerate(docs):
                    text = doc.page_content.strip()
                    if len(text) < 50:  # 过滤太短的页面
                        continue
                    
                    chunk = KnowledgeChunk(
                        cause_name=f"PDF知识_第{i+1}页",
                        description=text[:2000] if len(text) > 2000 else text,
                        metrics=[],
                        steps=[],
                        category=f"用户上传/{kb_name}"
                    )
                    chunks.append(chunk)
            except ImportError:
                print(f"[WARN] PyPDFLoader 未安装，跳过 PDF 文件: {file_path}")
        except Exception as e:
            print(f"[WARN] PDF 文件解析失败 {file_path}: {e}")
        return chunks
    
    def _parse_metrics(self, metrics_str: str) -> List[str]:
        """
        @brief 解析指标字符串
        @param metrics_str: 原始指标字符串
        @return: 解析后的指标列表
        @note 支持多种格式：列表项、逗号分隔等
        """
        if not metrics_str:
            return []
        
        metrics = []
        for line in metrics_str.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                metrics.append(line[2:])
            elif line.startswith('• '):
                metrics.append(line[2:])
            elif line and not line[0].isdigit():
                for m in line.split(','):
                    m = m.strip()
                    if m and not m[0].isdigit():
                        metrics.append(m)
        
        return [m.strip() for m in metrics if m.strip()]
    
    def _parse_steps(self, steps_str) -> List[str]:
        """
        @brief 解析诊断步骤字符串
        @param steps_str: 原始步骤字符串或列表
        @return: 解析后的步骤列表
        @note 支持多种格式：列表项、编号列表、JSON数组等
        """
        if not steps_str:
            return []
        
        if isinstance(steps_str, list):
            return [str(s).strip() for s in steps_str if s]
        
        if isinstance(steps_str, str):
            steps = []
            for line in steps_str.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('- '):
                    steps.append(line[2:])
                elif line.startswith('• '):
                    steps.append(line[2:])
                elif line and line[0].isdigit():
                    parts = line.split('.', 1)
                    if len(parts) > 1:
                        steps.append(parts[1].strip())
                    else:
                        steps.append(line)
                elif line:
                    steps.append(line)
            return [s.strip() for s in steps if s.strip()]
        
        return []
    
    def get_all_causes(self) -> List[KnowledgeChunk]:
        """
        @brief 获取所有根因知识
        @return: 根因知识列表
        """
        if not self._loaded:
            self.load()
        return self._knowledge_base
    
    def search_by_metrics(self, metrics: List[str]) -> List[KnowledgeChunk]:
        """
        @brief 根据指标搜索相关根因
        @param metrics: 指标名称列表
        @return: 匹配的根因知识列表
        """
        if not self._loaded:
            self.load()
        
        results = []
        for chunk in self._knowledge_base:
            for metric in metrics:
                metric_lower = metric.lower()
                if any(metric_lower in m.lower() for m in chunk.metrics):
                    results.append(chunk)
                    break
                if metric_lower in chunk.description.lower():
                    results.append(chunk)
                    break
        
        return results
    
    def _init_bm25_index(self):
        """
        @brief 初始化BM25索引（对齐D-Bot论文Section5.1）
        @details 1. 对知识库文本做中文分词+预处理 2. 构建BM25索引
        """
        if not self._knowledge_base:
            print(f"[WARN] 知识库为空，无法初始化BM25索引")
            return
        
        if not BM25_AVAILABLE or not JIEBA_AVAILABLE:
            print(f"[WARN] BM25或jieba未安装，跳过BM25索引初始化")
            return
        
        print(f"[DEBUG] 开始初始化BM25索引...")
        
        # Step1：预处理每个知识块的文本（标签+关键词+原文）
        processed_texts = []
        self.corpus_index_map = {}  # 索引→知识块的映射
        
        stop_words = {'的', '了', '是', '在', '有', '就', '都', '而', '及', '与', '也', '还', '个', '中', '到', '对', '为', '等', '能', '可', '这', '那', '上', '下', '不', '会', '要', '以'}
        
        for idx, chunk in enumerate(self._knowledge_base):
            # 结构化文本：标签 + 根因名称 + 指标 + 描述 + 步骤
            structured_text = f"""
            标签：{chunk.category}
            根因：{chunk.cause_name}
            指标：{','.join(chunk.metrics)}
            描述：{chunk.description}
            步骤：{chunk.get_steps_text()}
            """
            # Chinese tokenization with stop words removal
            tokens = [word for word in jieba.lcut(structured_text.lower()) 
                     if word.strip() and word not in stop_words]
            
            if tokens:
                self.tokenized_corpus.append(tokens)
                self.corpus_index_map[len(self.tokenized_corpus)-1] = chunk
        
        # Initialize BM25 with parameters from D-Bot paper: k1=1.5, b=0.7
        # k1 controls term frequency saturation (higher = more saturation)
        # b controls document length normalization (0=no norm, 1=full norm)
        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus, k1=1.5, b=0.7)
            print(f"[OK] BM25 index initialized with {len(self.tokenized_corpus)} documents")
            
            # Pre-compute score normalization to map BM25 scores to [0,1]
            if SKLEARN_AVAILABLE:
                self.scaler = MinMaxScaler()
                dummy_scores = np.array([self.bm25.get_scores(["cpu", "high"]) 
                                        for _ in range(min(10, len(self.tokenized_corpus)))])
                if dummy_scores.size > 0:
                    self.scaler.fit(dummy_scores.reshape(-1, 1))
        else:
            print(f"[WARN] No valid tokenized text, BM25 initialization failed")
    
    def search_by_keywords(self, keywords: List[str]) -> List[KnowledgeChunk]:
        """
        @brief 根据关键词搜索根因
        @param keywords: 关键词列表
        @return: 匹配的根因知识列表
        """
        if not self._loaded:
            self.load()
        
        results = []
        for chunk in self._knowledge_base:
            text = f"{chunk.cause_name} {chunk.description}".lower()
            if any(kw.lower() in text for kw in keywords):
                results.append(chunk)
        
        return results
    
    def get_cause_by_name(self, name: str) -> Optional[KnowledgeChunk]:
        """
        @brief 根据名称获取根因
        @param name: 根因名称
        @return: 匹配的根因知识，未找到返回 None
        """
        if not self._loaded:
            self.load()
        
        for chunk in self._knowledge_base:
            if chunk.cause_name == name:
                return chunk
        return None
    
    def match_anomaly(self, anomaly_type: str, anomaly_desc: str) -> List[Dict]:
        """
        @brief 匹配异常与根因（完全对齐D-Bot论文Section5.1）
        @param anomaly_type: 异常类型
        @param anomaly_desc: 异常描述
        @return: 匹配的根因列表，包含BM25分数+相关性等级
        @reference D-Bot Paper Section 5.1 - Knowledge Retrieval
        """
        if not self._loaded:
            self.load()
        
        # 如果BM25可用，使用真正的BM25检索
        if self.bm25 and BM25_AVAILABLE and JIEBA_AVAILABLE:
            return self._match_anomaly_bm25(anomaly_type, anomaly_desc)
        
        # 降级：使用简单关键词匹配
        return self._match_anomaly_simple(anomaly_type, anomaly_desc)
    
    def _match_anomaly_bm25(self, anomaly_type: str, anomaly_desc: str) -> List[Dict]:
        """
        @brief 使用BM25进行异常匹配（对齐D-Bot论文Section5.1）
        """
        # Step1：构造结构化Query（对齐D-Bot论文的LLM增强Query）
        structured_query = self._build_enhanced_query(anomaly_type, anomaly_desc)
        print(f"[DEBUG] 结构化BM25 Query: {structured_query[:100]}...")
        
        # Step2：Query分词
        stop_words = {'的', '了', '是', '在', '有', '就', '都', '而', '及', '与', '也', '还', '个', '中', '到', '对', '为', '等', '能', '可', '这', '那', '上', '下', '不', '会', '要', '以'}
        query_tokens = [word for word in jieba.lcut(structured_query.lower()) if word.strip() and word not in stop_words]
        
        if not query_tokens:
            return []
        
        # Step3：BM25检索（核心！真正的BM25分数计算）
        bm25_scores = self.bm25.get_scores(query_tokens)
        
        # Step4：分数归一化（0-1）+ 过滤低分数
        if self.scaler and SKLEARN_AVAILABLE:
            normalized_scores = self.scaler.transform(bm25_scores.reshape(-1, 1)).flatten()
        else:
            max_score = max(bm25_scores) if max(bm25_scores) > 0 else 1
            normalized_scores = bm25_scores / max_score
        
        # Step5：整理结果（对齐论文的高/中/低相关阈值）
        results = []
        HIGH_THRESHOLD = 0.5   # 高相关
        MEDIUM_THRESHOLD = 0.2  # 中相关
        
        for idx, score in enumerate(normalized_scores):
            if idx not in self.corpus_index_map:
                continue
            
            chunk = self.corpus_index_map[idx]
            score_rounded = round(score, 3)
            
            # 判定相关性等级
            if score_rounded >= HIGH_THRESHOLD:
                relevance = "高相关"
            elif score_rounded >= MEDIUM_THRESHOLD:
                relevance = "中相关"
            else:
                relevance = "低相关"
            
            results.append({
                "cause_name": chunk.cause_name,
                "description": chunk.description[:200] + "...",
                "metrics": chunk.metrics,
                "bm25_score": score_rounded,  # 真正的BM25分数
                "relevance": relevance,       # 相关性等级
                "source": chunk.source
            })
        
        # Step6：按BM25分数降序排序，返回Top5
        results.sort(key=lambda x: x["bm25_score"], reverse=True)
        return results[:5]
    
    def _match_anomaly_simple(self, anomaly_type: str, anomaly_desc: str) -> List[Dict]:
        """
        @brief 简单关键词匹配（降级方案）
        """
        keyword_mapping = {
            "cpu": ["cpu", "workload", "process"],
            "memory": ["memory", "mem", "swap"],
            "io": ["io", "disk", "spill"],
            "slow": ["slow", "query", "scan", "index"],
            "lock": ["lock", "wait", "contention"],
            "dead": ["dead", "tuple", "bloat"],
            "index": ["index", "missing", "redundant"]
        }
        
        text = f"{anomaly_type} {anomaly_desc}".lower()
        matched_keywords = []
        for key, keywords in keyword_mapping.items():
            if any(kw in text for kw in keywords):
                matched_keywords.extend(keywords)
        
        matched_causes = self.search_by_keywords(matched_keywords)
        
        results = []
        for cause in matched_causes:
            score = 0
            cause_text = f"{cause.cause_name} {cause.description}".lower()
            for kw in matched_keywords:
                if kw in cause_text:
                    score += 1
            
            results.append({
                "cause_name": cause.cause_name,
                "description": cause.description[:200] + "...",
                "metrics": cause.metrics,
                "match_score": score / max(len(matched_keywords), 1),
                "relevance": "中相关",
                "source": cause.source
            })
        
        results.sort(key=lambda x: x["match_score"], reverse=True)
        return results[:5]
    
    def _build_enhanced_query(self, anomaly_type: str, anomaly_desc: str) -> str:
        """
        @brief 构建增强型Query（对齐D-Bot论文Section5.1）
        @details 异常类型 + 核心指标 + 潜在根因关键词
        
        【任务三增强】添加 LLM Query Rewrite 功能
        在检索前先让 LLM 提取核心数据库特征关键词，提升检索精度
        """
        raw_text = f"{anomaly_type} {anomaly_desc}".lower()
        
        enhanced_keywords = self._extract_db_features_with_llm(anomaly_type, anomaly_desc)
        
        root_cause_mapping = {
            "cpu高": ["cpu", "使用率", "高", "大表扫描", "全表扫描", "索引缺失", "workload", "process"],
            "内存高": ["memory", "内存", "mem", "swap", "溢出", "缓存", "泄漏"],
            "io高": ["io", "磁盘", "spill", "读写", "存储", "吞吐量"],
            "慢查询": ["slow", "query", "慢查询", "扫描", "索引", "sql优化"],
            "锁等待": ["lock", "wait", "锁等待", "死锁", "并发", "contention"],
            "数据膨胀": ["dead", "tuple", "bloat", "膨胀", "碎片"],
            "索引问题": ["index", "索引", "缺失", "冗余", "失效"]
        }
        
        matched_keywords = []
        for cause, keywords in root_cause_mapping.items():
            if any(kw in raw_text for kw in keywords):
                matched_keywords.extend(keywords)
        
        all_keywords = list(set(matched_keywords + enhanced_keywords))
        
        enhanced_query = f"{anomaly_type} {anomaly_desc} {' '.join(all_keywords)}"
        
        return enhanced_query.strip()
    
    def _extract_db_features_with_llm(self, anomaly_type: str, anomaly_desc: str) -> List[str]:
        """
        【任务三】LLM Query Rewrite - 提取核心数据库特征关键词
        
        在进行 Hybrid Search 之前，先让 LLM 做一次特征提取，
        而不是直接用原始报错日志去检索，大幅提升检索精度。
        
        @param anomaly_type: 异常类型
        @param anomaly_desc: 异常描述
        @return: 提取的核心数据库特征关键词列表
        """
        default_keywords = ["PostgreSQL", "performance", "database"]
        
        try:
            from server.utils import get_ChatOpenAI
            from configs import TEMPERATURE
            
            prompt = f"""提取以下数据库异常描述的核心数据库特征关键词（只输出关键词，用逗号分隔）：

异常类型: {anomaly_type}
异常描述: {anomaly_desc}

请提取与以下类别相关的关键词：
1. 数据库组件（如：Shared Buffers, WAL, Checkpoint, Index, Table）
2. 性能指标（如：CPU, Memory, I/O, Latency, Throughput）
3. 操作类型（如：SELECT, INSERT, UPDATE, DELETE, VACUUM, ANALYZE）
4. 问题类型（如：Lock, Deadlock, Bloat, Missing Index, Slow Query）

只输出关键词，不要解释："""

            llm = get_ChatOpenAI(
                model_name="deepseek-chat",
                temperature=0.1,
                max_tokens=100,
                streaming=False
            )
            
            response = llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            keywords = [kw.strip() for kw in content.replace('，', ',').split(',') if kw.strip()]
            
            if keywords:
                print(f"[Query Rewrite] 提取关键词: {keywords}")
                return keywords
            
        except Exception as e:
            print(f"[WARN] LLM Query Rewrite 失败，使用默认关键词: {e}")
        
        return default_keywords


class KnowledgeSummaryTree:
    """
    @class KnowledgeSummaryTree
    @brief Summary-Tree 层次化知识组织
    @reference D-Bot Paper Section 4.1 - Summary-tree
    
    实现基于层次聚类的知识树构建：
    1. 使用 TF-IDF 向量化知识描述
    2. 使用 AgglomerativeClustering 进行层次聚类
    3. 构建从粗到细的检索树
    """
    
    def __init__(self, chunks: List[KnowledgeChunk], n_clusters: int = 5):
        """
        @brief 初始化 Summary-Tree
        @param chunks: 知识块列表
        @param n_clusters: 聚类数量
        """
        self.chunks = chunks
        self.n_clusters = n_clusters
        self.root: Optional[SummaryNode] = None
        self._embeddings: Optional[np.ndarray] = None
        
        if chunks:
            self._build_tree()
    
    def _get_embeddings(self) -> np.ndarray:
        """
        @brief 获取知识块的嵌入向量
        @return: 嵌入矩阵 (n_chunks, embedding_dim)
        """
        if self._embeddings is not None:
            return self._embeddings
        
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            # 使用 TF-IDF 作为嵌入
            texts = [f"{c.cause_name} {c.description}" for c in self.chunks]
            vectorizer = TfidfVectorizer(max_features=128)
            self._embeddings = vectorizer.fit_transform(texts).toarray()
            
        except ImportError:
            # 降级：使用简单的词袋模型
            print("[WARNING] sklearn 未安装，使用简化嵌入")
            self._embeddings = self._simple_embeddings()
        
        return self._embeddings
    
    def _simple_embeddings(self) -> np.ndarray:
        """简化的嵌入方法"""
        all_words = set()
        for c in self.chunks:
            all_words.update(c.cause_name.lower().split())
            all_words.update(c.description.lower().split())
        
        word_list = list(all_words)[:100]
        embeddings = []
        
        for c in self.chunks:
            text = f"{c.cause_name} {c.description}".lower()
            vec = [1.0 if word in text else 0.0 for word in word_list]
            embeddings.append(vec)
        
        return np.array(embeddings)
    
    def _build_tree(self):
        """
        @brief 构建层次化知识树
        @reference D-Bot Paper Section 4.1
        """
        if not self.chunks:
            return
        
        embeddings = self._get_embeddings()
        
        try:
            from sklearn.cluster import AgglomerativeClustering
            
            # 层次聚类
            clustering = AgglomerativeClustering(
                n_clusters=min(self.n_clusters, len(self.chunks)),
                linkage='average'
            )
            labels = clustering.fit_predict(embeddings)
            
        except ImportError:
            # 降级：按类别分组
            labels = self._simple_clustering()
        
        # 构建树结构
        self.root = self._build_tree_from_labels(labels, embeddings)
        print(f"[[OK]] Summary-Tree 构建完成，根节点包含 {len(self.chunks)} 个知识块")
    
    def _simple_clustering(self) -> np.ndarray:
        """简化的聚类方法：按关键词分组"""
        category_keywords = {
            0: ["cpu", "process", "workload"],
            1: ["memory", "mem", "swap"],
            2: ["io", "disk", "storage"],
            3: ["lock", "wait", "contention"],
            4: ["query", "sql", "scan"]
        }
        
        labels = []
        for c in self.chunks:
            text = f"{c.cause_name} {c.description}".lower()
            label = 4  # 默认类别
            for cat, keywords in category_keywords.items():
                if any(kw in text for kw in keywords):
                    label = cat
                    break
            labels.append(label)
        
        return np.array(labels)
    
    def _build_tree_from_labels(self, labels: np.ndarray, embeddings: np.ndarray) -> SummaryNode:
        """根据聚类标签构建树"""
        # 创建根节点
        root = SummaryNode(
            summary="数据库根因知识库",
            keywords=["database", "root cause", "diagnosis"],
            level=0
        )
        
        # 按类别分组
        clusters = defaultdict(list)
        for i, label in enumerate(labels):
            clusters[label].append(i)
        
        # 为每个聚类创建子节点
        for label, indices in clusters.items():
            cluster_chunks = [self.chunks[i] for i in indices]
            cluster_embeddings = embeddings[indices]
            
            # 计算聚类中心
            centroid = np.mean(cluster_embeddings, axis=0)
            
            # 提取聚类关键词
            keywords = self._extract_cluster_keywords(cluster_chunks)
            
            # 创建子节点
            child = SummaryNode(
                summary=self._generate_cluster_summary(cluster_chunks),
                keywords=keywords,
                level=1,
                knowledge_chunks=cluster_chunks,
                centroid=centroid
            )
            
            # 设置知识块的类别
            for chunk in cluster_chunks:
                chunk.category = child.summary
            
            root.children.append(child)
        
        return root
    
    def _extract_cluster_keywords(self, chunks: List[KnowledgeChunk]) -> List[str]:
        """提取聚类的关键词"""
        all_metrics = []
        for c in chunks:
            all_metrics.extend(c.metrics)
        
        # 统计词频
        word_freq = defaultdict(int)
        for m in all_metrics:
            for word in m.lower().split():
                word_freq[word] += 1
        
        # 返回高频词
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:5]]
    
    def _generate_cluster_summary(self, chunks: List[KnowledgeChunk]) -> str:
        """生成聚类摘要"""
        if not chunks:
            return "未知类别"
        
        # 基于第一个知识块的名称生成摘要
        first_name = chunks[0].cause_name
        if "cpu" in first_name.lower():
            return "CPU相关问题"
        elif "memory" in first_name.lower():
            return "内存相关问题"
        elif "io" in first_name.lower() or "disk" in first_name.lower():
            return "I/O相关问题"
        elif "lock" in first_name.lower():
            return "锁相关问题"
        elif "query" in first_name.lower() or "sql" in first_name.lower():
            return "查询相关问题"
        else:
            return f"其他问题 ({len(chunks)}条)"
    
    def retrieve(self, query: str, top_k: int = 5) -> List[KnowledgeChunk]:
        """
        @brief 从粗到细的检索
        @param query: 查询文本
        @param top_k: 返回数量
        @return: 匹配的知识块列表
        """
        if not self.root:
            return []
        
        # 第一层：找到最相关的子树
        query_vec = self._get_query_vector(query)
        
        best_child = None
        best_similarity = -1
        
        for child in self.root.children:
            if child.centroid is not None:
                similarity = np.dot(query_vec, child.centroid) / (
                    np.linalg.norm(query_vec) * np.linalg.norm(child.centroid) + 1e-8
                )
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_child = child
        
        # 第二层：在子树中检索
        if best_child:
            return best_child.knowledge_chunks[:top_k]
        
        return []
    
    def _get_query_vector(self, query: str) -> np.ndarray:
        """获取查询向量"""
        if self._embeddings is None or len(self._embeddings) == 0:
            return np.zeros(128)
        
        # 使用知识块嵌入的平均作为查询向量（简化）
        query_words = set(query.lower().split())
        scores = []
        
        for i, c in enumerate(self.chunks):
            text = f"{c.cause_name} {c.description}".lower()
            score = sum(1 for w in query_words if w in text)
            scores.append(score)
        
        # 加权平均
        weights = np.array(scores) / (sum(scores) + 1e-8)
        return np.average(self._embeddings, axis=0, weights=weights)


knowledge_loader = KnowledgeLoader()


def load_knowledge() -> bool:
    """
    @brief 加载知识库
    @return: 加载成功返回 True
    """
    return knowledge_loader.load()


def get_all_root_causes() -> List[Dict]:
    """
    @brief 获取所有根因知识
    @return: 根因知识字典列表
    """
    return [c.to_dict() for c in knowledge_loader.get_all_causes()]


def match_anomaly_to_cause(anomaly_type: str, anomaly_desc: str) -> List[Dict]:
    """
    @brief 匹配异常到根因
    @param anomaly_type: 异常类型
    @param anomaly_desc: 异常描述
    @return: 匹配的根因列表
    """
    return knowledge_loader.match_anomaly(anomaly_type, anomaly_desc)


def extract_root_cause_type(anomaly_desc: str) -> str:
    """
    @brief 从异常描述中提取根因类型
    @param anomaly_desc: 异常描述
    @return: 根因类型
    """
    desc_lower = anomaly_desc.lower()
    
    root_cause_keywords = {
        "CPU高": ["cpu", "使用率", "workload", "process", "大表扫描"],
        "内存高": ["memory", "内存", "mem", "swap", "溢出"],
        "IO高": ["io", "磁盘", "spill", "读写", "存储"],
        "慢查询": ["slow", "query", "慢查询", "扫描", "sql"],
        "锁等待": ["lock", "wait", "锁等待", "死锁", "并发"],
        "数据膨胀": ["dead", "tuple", "bloat", "膨胀", "碎片"],
        "索引缺失": ["index", "索引", "缺失", "missing"]
    }
    
    for cause_type, keywords in root_cause_keywords.items():
        if any(kw in desc_lower for kw in keywords):
            return cause_type
    
    return "其他"


def generate_dynamic_prompt(anomaly_desc: str, summary_tree: Dict = None) -> str:
    """
    @brief 动态匹配知识，生成Prompt（对齐论文Section 5.1）
    @param anomaly_desc: 异常描述
    @param summary_tree: 摘要树（可选）
    @return: 生成的Prompt
    """
    if summary_tree is None:
        matched = knowledge_loader.match_anomaly("unknown", anomaly_desc)
        matched_chunks = matched[:2] if matched else []
    else:
        root_cause_type = extract_root_cause_type(anomaly_desc)
        matched_node = summary_tree.get(root_cause_type, {})
        matched_chunks = matched_node.get("chunks", [])[:2]
    
    knowledge_text = ""
    if matched_chunks:
        for i, chunk in enumerate(matched_chunks, 1):
            if isinstance(chunk, dict):
                knowledge_text += f"{i}. {chunk.get('cause_name', '未知')}: {chunk.get('description', '')[:200]}\n"
            else:
                knowledge_text += f"{i}. {chunk.cause_name}: {chunk.description[:200]}\n"
    
    prompt = f"""
角色：数据库诊断专家
异常描述：{anomaly_desc}
相关知识：
{knowledge_text}
要求：基于上述知识和工具返回结果推理，禁止无意义重复调用工具。
"""
    return prompt.strip()


def build_summary_tree(knowledge_chunks: List[Dict] = None) -> Dict:
    """
    @brief 构建简单版摘要树（对齐论文核心逻辑）
    @param knowledge_chunks: 知识块列表（可选，默认使用已加载的知识库）
    @return: 摘要树字典
    """
    if knowledge_chunks is None:
        knowledge_chunks = get_all_root_causes()
    
    summary_tree = {}
    
    root_cause_types = ["CPU高", "锁等待", "慢查询", "大表", "索引缺失", "内存高", "IO高", "数据膨胀"]
    
    for rct in root_cause_types:
        related_chunks = []
        for chunk in knowledge_chunks:
            tags = chunk.get("tags", [])
            cause_name = chunk.get("cause_name", "").lower()
            description = chunk.get("description", "").lower()
            
            if rct.lower() in cause_name or rct.lower() in description:
                related_chunks.append(chunk)
        
        if related_chunks:
            summary = f"{rct}相关知识：" + "; ".join([c.get("cause_name", "未知") for c in related_chunks[:3]])
            summary_tree[rct] = {
                "summary": summary,
                "chunks": related_chunks
            }
    
    return summary_tree


__all__ = [
    'KnowledgeLoader', 'KnowledgeChunk', 'SummaryTree',
    'knowledge_loader', 'load_knowledge', 'get_all_root_causes',
    'match_anomaly_to_cause', 'extract_root_cause_type',
    'generate_dynamic_prompt', 'build_summary_tree'
]
