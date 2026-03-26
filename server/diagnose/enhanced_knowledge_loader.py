"""
增强知识库加载器 - BM25 + 语义级知识召回
Reference: D-Bot Paper Section 5.1 - Knowledge Retrieval

实现功能：
1. BM25 精确关键词匹配
2. Sentence-BERT 语义级匹配
3. 混合召回策略
4. 动态索引构建
5. 【2024修复】融合加载内置知识 + 用户上传知识
"""
import json
import os
import time
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from rank_bm25 import BM25Okapi
import re

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    print("[WARN] Sentence-BERT 未安装，将仅使用 BM25 匹配")

from server.diagnose.knowledge_loader import KnowledgeChunk, KnowledgeLoader, USER_KB_ROOT_PATH


@dataclass
class EnhancedKnowledgeChunk:
    """增强知识块 - 包含语义信息"""
    cause_name: str
    description: str
    metrics: List[str]
    steps: str = ""
    embedding: Optional[np.ndarray] = None
    category: str = "general"
    source: str = "内置专家规则"
    
    def to_dict(self) -> Dict:
        return {
            "cause_name": self.cause_name,
            "description": self.description,
            "metrics": self.metrics,
            "steps": self.steps,
            "category": self.category,
            "source": self.source
        }


class BM25Index:
    """BM25 索引 - 增强版"""
    
    def __init__(self):
        self.knowledge_chunks: List[EnhancedKnowledgeChunk] = []
        self.bm25_index = None
        self.tokenized_corpus = []
        self.chunk_to_index = {}
        
    def build_index(self, knowledge_chunks: List[EnhancedKnowledgeChunk]):
        """构建增强 BM25 索引"""
        self.knowledge_chunks = knowledge_chunks
        
        corpus = []
        for i, chunk in enumerate(knowledge_chunks):
            text_parts = [
                chunk.cause_name,
                chunk.description,
                " ".join(chunk.metrics),
                chunk.steps,
                chunk.category
            ]
            full_text = " ".join(part for part in text_parts if part.strip())
            corpus.append(full_text)
            self.chunk_to_index[i] = chunk
        
        self.tokenized_corpus = []
        for doc in corpus:
            tokens = self._tokenize_text(doc)
            self.tokenized_corpus.append(tokens)
        
        self.bm25_index = BM25Okapi(self.tokenized_corpus)
        
        print(f"[OK] BM25 索引构建完成，共 {len(knowledge_chunks)} 条知识")
    
    def _tokenize_text(self, text: str) -> List[str]:
        """中英文混合分词"""
        tokens = []
        
        # 中文停用词
        chinese_stop_words = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        # 英文停用词
        english_stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare', 'ought', 'used', 'it', 'its', 'this', 'that', 'these', 'those'}
        
        # 提取英文单词
        english_words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        for word in english_words:
            if word not in english_stop_words and len(word) > 1:
                tokens.append(word)
        
        # 提取中文词汇（简单按字符分割，后续可接入jieba等分词工具）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for chars in chinese_chars:
            # 简单处理：每2-4个字符作为一个词
            if len(chars) <= 4:
                if chars not in chinese_stop_words:
                    tokens.append(chars)
            else:
                # 长文本按2-4字符切分
                for i in range(0, len(chars), 2):
                    word = chars[i:i+4]
                    if word not in chinese_stop_words and len(word) > 1:
                        tokens.append(word)
        
        return tokens
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """BM25 搜索最相关的知识块"""
        if not self.bm25_index:
            return []
        
        processed_query = self._process_query(query)
        tokenized_query = processed_query.split()
        
        bm25_scores = self.bm25_index.get_scores(tokenized_query)
        normalized_scores = self._normalize_scores(bm25_scores)
        
        top_indices = np.argsort(normalized_scores)[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            if normalized_scores[idx] > 0:
                chunk = self.chunk_to_index[idx]
                results.append({
                    "chunk": chunk,
                    "bm25_score": float(normalized_scores[idx]),
                    "rank": len(results) + 1,
                    "match_type": "bm25"
                })
        
        return results
    
    def _process_query(self, query: str) -> str:
        processed = re.sub(r'[^\w\s]', ' ', query)
        processed = processed.lower()
        processed = re.sub(r'\s+', ' ', processed).strip()
        return processed
    
    def _normalize_scores(self, scores: np.ndarray) -> np.ndarray:
        if len(scores) == 0:
            return scores
        
        min_score = np.min(scores)
        max_score = np.max(scores)
        
        if max_score == min_score:
            return np.ones_like(scores)
        
        normalized = (scores - min_score) / (max_score - min_score)
        return normalized


class SemanticIndex:
    """语义索引 - 基于 Sentence-BERT"""
    
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self.model = None
        self.knowledge_chunks: List[EnhancedKnowledgeChunk] = []
        self.embeddings: Optional[np.ndarray] = None
        self.chunk_to_index = {}
        
        if not HAS_SENTENCE_TRANSFORMERS:
            print("[WARN] 语义索引不可用，请安装 sentence-transformers")
            return
        
        self._load_model()
    
    def _load_model(self):
        try:
            print(f"[REFLECT] 加载语义模型: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            print(f"[OK] 语义模型加载成功")
        except Exception as e:
            print(f"[ERROR] 语义模型加载失败: {e}")
            self.model = None
    
    def build_index(self, knowledge_chunks: List[EnhancedKnowledgeChunk]):
        if not self.model:
            print("[WARN] 语义模型不可用，跳过语义索引构建")
            return
        
        self.knowledge_chunks = knowledge_chunks
        
        texts = []
        for i, chunk in enumerate(knowledge_chunks):
            text_parts = [
                chunk.cause_name,
                chunk.description,
                " ".join(chunk.metrics),
                chunk.steps
            ]
            full_text = " ".join(part for part in text_parts if part.strip())
            texts.append(full_text)
            self.chunk_to_index[i] = chunk
        
        print(f"[REFLECT] 生成 {len(texts)} 个文本嵌入...")
        start_time = time.time()
        
        try:
            self.embeddings = self.model.encode(texts, show_progress_bar=True)
            embedding_time = time.time() - start_time
            print(f"[OK] 语义索引构建完成，耗时 {embedding_time:.2f}s")
        except Exception as e:
            print(f"[ERROR] 嵌入生成失败: {e}")
            self.embeddings = None
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        if not self.model or self.embeddings is None:
            return []
        
        try:
            query_embedding = self.model.encode([query])
            similarities = cosine_similarity(query_embedding, self.embeddings)[0]
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            results = []
            for idx in top_indices:
                if similarities[idx] > 0.3:
                    chunk = self.chunk_to_index[idx]
                    results.append({
                        "chunk": chunk,
                        "semantic_score": float(similarities[idx]),
                        "rank": len(results) + 1,
                        "match_type": "semantic"
                    })
            
            return results
            
        except Exception as e:
            print(f"[ERROR] 语义搜索失败: {e}")
            return []


class HybridKnowledgeRetriever:
    """混合知识检索器 - BM25 + 语义搜索"""
    
    def __init__(self, bm25_weight: float = 0.7, semantic_weight: float = 0.3):
        self.bm25_index = BM25Index()
        self.semantic_index = SemanticIndex()
        self.bm25_weight = bm25_weight
        self.semantic_weight = semantic_weight
        self.knowledge_chunks: List[EnhancedKnowledgeChunk] = []
        
    def build_index(self, knowledge_chunks: List[EnhancedKnowledgeChunk]):
        self.knowledge_chunks = knowledge_chunks
        
        self.bm25_index.build_index(knowledge_chunks)
        self.semantic_index.build_index(knowledge_chunks)
        
        print(f"[OK] 混合索引构建完成，共 {len(knowledge_chunks)} 条知识")
    
    def search(self, query: str, top_k: int = 5, use_hybrid: bool = True) -> List[Dict]:
        if use_hybrid:
            return self._hybrid_search(query, top_k)
        else:
            return self.bm25_index.search(query, top_k)
    
    def _hybrid_search(self, query: str, top_k: int = 5) -> List[Dict]:
        bm25_results = self.bm25_index.search(query, top_k * 2)
        semantic_results = self.semantic_index.search(query, top_k * 2)
        combined_results = self._combine_results(bm25_results, semantic_results, top_k)
        return combined_results
    
    def _combine_results(self, bm25_results: List[Dict], semantic_results: List[Dict], top_k: int) -> List[Dict]:
        chunk_scores = {}
        
        for result in bm25_results:
            chunk = result["chunk"]
            chunk_key = f"{chunk.cause_name}_{chunk.source}"
            if chunk_key not in chunk_scores:
                chunk_scores[chunk_key] = {"chunk": chunk, "bm25": 0, "semantic": 0, "matches": []}
            chunk_scores[chunk_key]["bm25"] = result["bm25_score"]
            chunk_scores[chunk_key]["matches"].append(result["match_type"])
        
        for result in semantic_results:
            chunk = result["chunk"]
            chunk_key = f"{chunk.cause_name}_{chunk.source}"
            if chunk_key not in chunk_scores:
                chunk_scores[chunk_key] = {"chunk": chunk, "bm25": 0, "semantic": 0, "matches": []}
            chunk_scores[chunk_key]["semantic"] = result["semantic_score"]
            chunk_scores[chunk_key]["matches"].append(result["match_type"])
        
        final_results = []
        for chunk_key, scores in chunk_scores.items():
            hybrid_score = (scores["bm25"] * self.bm25_weight + 
                           scores["semantic"] * self.semantic_weight)
            
            final_results.append({
                "chunk": scores["chunk"],
                "hybrid_score": hybrid_score,
                "bm25_score": scores["bm25"],
                "semantic_score": scores["semantic"],
                "match_types": list(set(scores["matches"])),
                "rank": 0
            })
        
        final_results.sort(key=lambda x: x["hybrid_score"], reverse=True)
        
        for i, result in enumerate(final_results):
            result["rank"] = i + 1
        
        return final_results[:top_k]
    
    def search_by_category(self, query: str, category: str, top_k: int = 3) -> List[Dict]:
        all_results = self.search(query, top_k * 3)
        
        category_results = []
        for result in all_results:
            if result["chunk"].category == category:
                category_results.append(result)
        
        return category_results[:top_k]
    
    def get_similar_chunks(self, chunk: EnhancedKnowledgeChunk, top_k: int = 3) -> List[Dict]:
        query = f"{chunk.cause_name} {chunk.description} {' '.join(chunk.metrics)}"
        return self.search(query, top_k)


class EnhancedKnowledgeLoader:
    """增强知识库加载器 - 支持融合加载"""
    
    def __init__(self, knowledge_path: str = None):
        self.knowledge_path = knowledge_path or self._get_default_path()
        self.retriever = HybridKnowledgeRetriever()
        self._loaded = False
        
    def _get_default_path(self) -> str:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "doc2knowledge",
            "root_causes_dbmind.jsonl"
        )
    
    def load(self) -> bool:
        """加载知识库 - 融合加载内置知识 + 用户上传知识"""
        if self._loaded:
            return True
        
        builtin_count = 0
        user_count = 0
        
        print(f"[DEBUG] ========== 开始融合加载增强知识库 ==========")
        
        enhanced_chunks = []
        
        builtin_loaded, builtin_chunks = self._load_builtin_knowledge()
        if builtin_loaded:
            enhanced_chunks.extend(builtin_chunks)
            builtin_count = len(builtin_chunks)
            print(f"[OK] 内置专家知识加载完成: {builtin_count} 条")
        
        user_loaded, user_chunks = self._load_user_uploaded_knowledge()
        if user_loaded:
            enhanced_chunks.extend(user_chunks)
            user_count = len(user_chunks)
            print(f"[OK] 用户上传知识加载完成: {user_count} 条")
        
        total_count = len(enhanced_chunks)
        
        if total_count > 0:
            self.retriever.build_index(enhanced_chunks)
            self._loaded = True
            print(f"")
            print(f"╔════════════════════════════════════════════════════════════╗")
            print(f"║  [OK] 增强知识库融合加载完成                                ║")
            print(f"║  - 内置专家规则: {builtin_count:>4} 条                              ║")
            print(f"║  - 用户上传知识: {user_count:>4} 条                              ║")
            print(f"║  - 总计知识数量: {total_count:>4} 条                              ║")
            print(f"╚════════════════════════════════════════════════════════════╝")
            print(f"")
            return True
        else:
            print(f"[WARN] 增强知识库加载失败，无任何知识可用")
            return False
    
    def _load_builtin_knowledge(self) -> Tuple[bool, List[EnhancedKnowledgeChunk]]:
        """加载内置专家知识 - 支持JSON和JSONL两种格式"""
        chunks = []
        
        if not os.path.exists(self.knowledge_path):
            print(f"[WARNING] 内置知识文件不存在: {self.knowledge_path}")
            return False, chunks
        
        try:
            with open(self.knowledge_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            # 判断文件格式：JSONL（每行一个JSON对象）或 JSON（整个文件一个JSON数组）
            if content.startswith('['):
                # JSON 数组格式
                data = json.loads(content)
                for item in data:
                    chunk = EnhancedKnowledgeChunk(
                        cause_name=item.get("cause_name", ""),
                        description=item.get("desc", item.get("description", "")),
                        metrics=self._parse_metrics(item.get("metrics", "")),
                        steps=item.get("steps", ""),
                        category=self._categorize_chunk(item),
                        source="内置专家规则"
                    )
                    chunks.append(chunk)
            else:
                # JSONL 格式（每行一个JSON对象）
                for line_num, line in enumerate(content.split('\n'), 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        chunk = EnhancedKnowledgeChunk(
                            cause_name=item.get("cause_name", ""),
                            description=item.get("desc", item.get("description", "")),
                            metrics=self._parse_metrics(item.get("metrics", "")),
                            steps=item.get("steps", ""),
                            category=self._categorize_chunk(item),
                            source="内置专家规则"
                        )
                        chunks.append(chunk)
                    except json.JSONDecodeError as e:
                        print(f"[WARN] 内置知识第{line_num}行解析失败: {e}")
                        continue
            
            return True, chunks
        except Exception as e:
            print(f"[ERROR] 内置知识加载失败: {e}")
            return False, chunks
    
    def _load_user_uploaded_knowledge(self) -> Tuple[bool, List[EnhancedKnowledgeChunk]]:
        """加载用户上传的知识"""
        chunks = []
        
        if not os.path.exists(USER_KB_ROOT_PATH):
            print(f"[DEBUG] 用户知识库根目录不存在: {USER_KB_ROOT_PATH}")
            return False, chunks
        
        print(f"[DEBUG] 扫描用户知识库目录: {USER_KB_ROOT_PATH}")
        
        loaded_files = []
        
        try:
            for kb_name in os.listdir(USER_KB_ROOT_PATH):
                kb_path = os.path.join(USER_KB_ROOT_PATH, kb_name)
                
                if not os.path.isdir(kb_path):
                    continue
                if kb_name.startswith('.') or kb_name == '__pycache__':
                    continue
                
                content_path = os.path.join(kb_path, "content")
                if not os.path.exists(content_path):
                    continue
                
                print(f"[DEBUG] 扫描知识库 [{kb_name}] 的内容目录...")
                
                for file_name in os.listdir(content_path):
                    file_path = os.path.join(content_path, file_name)
                    
                    if not os.path.isfile(file_path):
                        continue
                    
                    ext = os.path.splitext(file_name)[1].lower()
                    
                    try:
                        if ext == '.jsonl':
                            file_chunks = self._load_jsonl_file(file_path, kb_name)
                            chunks.extend(file_chunks)
                            loaded_files.append(f"{kb_name}/{file_name} ({len(file_chunks)}条)")
                        elif ext == '.json':
                            file_chunks = self._load_json_file(file_path, kb_name)
                            chunks.extend(file_chunks)
                            loaded_files.append(f"{kb_name}/{file_name} ({len(file_chunks)}条)")
                        elif ext in ['.md', '.markdown']:
                            file_chunks = self._load_markdown_file(file_path, kb_name)
                            chunks.extend(file_chunks)
                            loaded_files.append(f"{kb_name}/{file_name} ({len(file_chunks)}条)")
                        elif ext == '.txt':
                            file_chunks = self._load_text_file(file_path, kb_name)
                            chunks.extend(file_chunks)
                            loaded_files.append(f"{kb_name}/{file_name} ({len(file_chunks)}条)")
                        elif ext == '.pdf':
                            file_chunks = self._load_pdf_file(file_path, kb_name)
                            if file_chunks:
                                chunks.extend(file_chunks)
                                loaded_files.append(f"{kb_name}/{file_name} ({len(file_chunks)}条)")
                    except Exception as e:
                        print(f"[WARN] 加载文件失败 {kb_name}/{file_name}: {e}")
                        continue
            
            if loaded_files:
                print(f"[DEBUG] 用户知识文件加载详情:")
                for f in loaded_files:
                    print(f"       - {f}")
            
            return len(chunks) > 0, chunks
            
        except Exception as e:
            print(f"[ERROR] 用户知识库扫描失败: {e}")
            return False, chunks
    
    def _load_jsonl_file(self, file_path: str, kb_name: str) -> List[EnhancedKnowledgeChunk]:
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        chunk = EnhancedKnowledgeChunk(
                            cause_name=item.get("cause_name", f"用户知识_{line_num}"),
                            description=item.get("desc", item.get("description", "")),
                            metrics=self._parse_metrics(item.get("metrics", "")),
                            steps=item.get("steps", ""),
                            category=self._categorize_chunk(item),
                            source=f"用户上传/{kb_name}"
                        )
                        chunks.append(chunk)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"[WARN] JSONL 文件解析失败 {file_path}: {e}")
        return chunks
    
    def _load_json_file(self, file_path: str, kb_name: str) -> List[EnhancedKnowledgeChunk]:
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            items = data if isinstance(data, list) else [data]
            
            for i, item in enumerate(items):
                chunk = EnhancedKnowledgeChunk(
                    cause_name=item.get("cause_name", f"用户知识_{i+1}"),
                    description=item.get("desc", item.get("description", "")),
                    metrics=self._parse_metrics(item.get("metrics", "")),
                    steps=item.get("steps", ""),
                    category=self._categorize_chunk(item),
                    source=f"用户上传/{kb_name}"
                )
                chunks.append(chunk)
        except Exception as e:
            print(f"[WARN] JSON 文件解析失败 {file_path}: {e}")
        return chunks
    
    def _load_markdown_file(self, file_path: str, kb_name: str) -> List[EnhancedKnowledgeChunk]:
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            sections = content.split('\n## ')
            
            for i, section in enumerate(sections):
                if not section.strip():
                    continue
                
                lines = section.strip().split('\n')
                title = lines[0].replace('#', '').strip() if lines else f"知识块_{i+1}"
                body = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""
                
                if title or body:
                    chunk = EnhancedKnowledgeChunk(
                        cause_name=title[:100] if len(title) > 100 else title,
                        description=body[:2000] if len(body) > 2000 else body,
                        metrics=[],
                        steps="",
                        category="markdown",
                        source=f"用户上传/{kb_name}"
                    )
                    chunks.append(chunk)
        except Exception as e:
            print(f"[WARN] Markdown 文件解析失败 {file_path}: {e}")
        return chunks
    
    def _load_text_file(self, file_path: str, kb_name: str) -> List[EnhancedKnowledgeChunk]:
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            
            if not paragraphs:
                paragraphs = [content.strip()]
            
            for i, para in enumerate(paragraphs):
                if len(para) < 20:
                    continue
                
                chunk = EnhancedKnowledgeChunk(
                    cause_name=f"文本知识_{i+1}",
                    description=para[:2000] if len(para) > 2000 else para,
                    metrics=[],
                    steps="",
                    category="text",
                    source=f"用户上传/{kb_name}"
                )
                chunks.append(chunk)
        except Exception as e:
            print(f"[WARN] 文本文件解析失败 {file_path}: {e}")
        return chunks
    
    def _load_pdf_file(self, file_path: str, kb_name: str) -> List[EnhancedKnowledgeChunk]:
        chunks = []
        try:
            try:
                from langchain.document_loaders import PyPDFLoader
                loader = PyPDFLoader(file_path)
                docs = loader.load()
                
                for i, doc in enumerate(docs):
                    text = doc.page_content.strip()
                    if len(text) < 50:
                        continue
                    
                    chunk = EnhancedKnowledgeChunk(
                        cause_name=f"PDF知识_第{i+1}页",
                        description=text[:2000] if len(text) > 2000 else text,
                        metrics=[],
                        steps="",
                        category="pdf",
                        source=f"用户上传/{kb_name}"
                    )
                    chunks.append(chunk)
            except ImportError:
                print(f"[WARN] PyPDFLoader 未安装，跳过 PDF 文件: {file_path}")
        except Exception as e:
            print(f"[WARN] PDF 文件解析失败 {file_path}: {e}")
        return chunks
    
    def _parse_metrics(self, metrics_str: str) -> List[str]:
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
    
    def _categorize_chunk(self, item: Dict) -> str:
        cause_name = item.get("cause_name", "").lower()
        description = item.get("desc", "").lower()
        
        categories = {
            "cpu": ["cpu", "process", "workload", "usage"],
            "memory": ["memory", "mem", "swap", "cache"],
            "io": ["io", "disk", "storage", "spill"],
            "index": ["index", "missing", "redundant"],
            "lock": ["lock", "wait", "contention"],
            "dead": ["dead", "tuple", "bloat"],
            "general": ["query", "performance", "slow", "optimization"]
        }
        
        text = f"{cause_name} {description}"
        for category, keywords in categories.items():
            if any(keyword in text for keyword in keywords):
                return category
        
        return "general"
    
    def search(self, query: str, top_k: int = 5, use_hybrid: bool = True) -> List[Dict]:
        if not self._loaded:
            self.load()
        
        return self.retriever.search(query, top_k, use_hybrid)
    
    def search_by_category(self, query: str, category: str, top_k: int = 3) -> List[Dict]:
        if not self._loaded:
            self.load()
        
        return self.retriever.search_by_category(query, category, top_k)
    
    def get_all_causes(self) -> List[EnhancedKnowledgeChunk]:
        if not self._loaded:
            self.load()
        
        return self.retriever.knowledge_chunks
    
    def get_cause_by_name(self, name: str) -> Optional[EnhancedKnowledgeChunk]:
        if not self._loaded:
            self.load()
        
        for chunk in self.retriever.knowledge_chunks:
            if chunk.cause_name == name:
                return chunk
        return None
    
    def get_similar_chunks(self, chunk: EnhancedKnowledgeChunk, top_k: int = 3) -> List[Dict]:
        if not self._loaded:
            self.load()
        
        return self.retriever.get_similar_chunks(chunk, top_k)


enhanced_knowledge_loader = EnhancedKnowledgeLoader()


def load_enhanced_knowledge() -> bool:
    return enhanced_knowledge_loader.load()


def search_knowledge(query: str, top_k: int = 5, use_hybrid: bool = True) -> List[Dict]:
    return enhanced_knowledge_loader.search(query, top_k, use_hybrid)


def search_knowledge_by_category(query: str, category: str, top_k: int = 3) -> List[Dict]:
    return enhanced_knowledge_loader.search_by_category(query, category, top_k)


def get_all_enhanced_causes() -> List[Dict]:
    return [chunk.to_dict() for chunk in enhanced_knowledge_loader.get_all_causes()]


def test_enhanced_knowledge_loader():
    print("Testing Enhanced Knowledge Loader...")
    
    success = load_enhanced_knowledge()
    if not success:
        print("[ERROR] Knowledge loading failed")
        return
    
    test_queries = [
        "CPU usage high",
        "memory leak",
        "missing index",
        "lock wait",
        "dead tuple"
    ]
    
    for query in test_queries:
        print(f"\n[SEARCH] Query: {query}")
        results = search_knowledge(query, top_k=3)
        
        for i, result in enumerate(results):
            chunk = result["chunk"]
            print(f"  {i+1}. {chunk.cause_name} (score: {result['hybrid_score']:.3f})")
            print(f"     Source: {chunk.source}")
            print(f"     Category: {chunk.category}")


if __name__ == "__main__":
    test_enhanced_knowledge_loader()
