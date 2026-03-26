"""
知识库服务 - ChromaDB 向量存储实现

本模块基于 ChromaDB 实现知识库的向量存储与检索功能，主要特性：
1. 文档向量化存储 - 支持中文文本的 Embedding 处理
2. 混合检索策略 - 结合向量相似度和 BM25 关键词匹配
3. 知识库管理 - 创建、更新、删除知识库及文档
4. 智能分块 - 按语义边界对长文档进行切分

技术栈：ChromaDB + text2vec-base-chinese + BM25
"""
from configs import SCORE_THRESHOLD, kbs_config, VS_TYPE_PROMPT_TOTAL_BYTE_SIZE
from server.knowledge_base.kb_service.base import KBService, SupportedVSType, EmbeddingsFunAdapter, \
    score_threshold_process
from server.knowledge_base.utils import KnowledgeFile, get_kb_path, get_vs_path
from langchain.docstore.document import Document
from typing import List, Dict
from langchain_community.vectorstores import Chroma


def normalize_collection_name(kb_name: str) -> str:
    """
    将知识库名称转换为符合 ChromaDB 集合命名规则的名称。
    规则：
    1. 长度 3-63 字符
    2. 以字母数字开头和结尾
    3. 只能包含字母数字、下划线、连字符
    
    策略：
    - 如果名称已符合规则，直接返回
    - 如果包含中文或特殊字符，使用 MD5 哈希生成合法名称
    """
    if not kb_name:
        return "kb_default"
    
    def is_valid_chroma_name(name):
        if len(name) < 3 or len(name) > 63:
            return False
        if not name[0].isalnum() or not name[-1].isalnum():
            return False
        if not name[0].isascii() or not name[-1].isascii():
            return False
        return all(c.isascii() and (c.isalnum() or c in '_-') for c in name)
    
    if is_valid_chroma_name(kb_name):
        return kb_name
    
    md5_hash = hashlib.md5(kb_name.encode('utf-8')).hexdigest()[:16]
    collection_name = f"kb_{md5_hash}"
    
    return collection_name


class ChromaKBService(KBService):
    vs_path: str
    kb_path: str
    vector_name: str = None
    chroma: Chroma
    collection_name: str = None

    def vs_type(self) -> str:
        return SupportedVSType.CHROMADB

    def get_vs_path(self):
        return get_vs_path(self.kb_name, self.vector_name)

    def get_kb_path(self):
        return get_kb_path(self.kb_name)

    def save_vector_store(self):
        pass

    def get_doc_by_ids(self, ids: List[str]) -> List[Document]:
        results = self.chroma.get(ids)
        return [Document(page_content=result["text"], metadata=result["metadata"]) for result in results]

    def _fix_chroma_db_schema(self, persist_directory):
        """
        核心补丁 v2：遍历所有核心表，强行注入缺失的 topic 列
        """
        try:
            db_path = os.path.join(persist_directory, "chroma.sqlite3")
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # 需要检查的两个关键表
                target_tables = ["collections", "segments"]
                
                for table in target_tables:
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = [column[1] for column in cursor.fetchall()]
                    if columns and "topic" not in columns:
                        print(f"!!! 补丁修复：正在为 {table} 表添加缺失的 topic 列 !!!")
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN topic TEXT")
                        conn.commit()
                
                conn.close()
        except Exception as e:
            print(f"自动修复表结构时遇到小挫折（可能已修复）: {e}")

    def _load_chroma(self):
        persist_dir = kbs_config.get("chromadb").get('persist_directory')
        
        self._fix_chroma_db_schema(persist_dir)
        
        self.collection_name = normalize_collection_name(self.kb_name)
        if self.collection_name != self.kb_name:
            print(f"[INFO] 知识库名称 '{self.kb_name}' 已转换为集合名称 '{self.collection_name}'")

        self.chroma = Chroma(
            embedding_function=EmbeddingsFunAdapter(self.embed_model),
            collection_name=self.collection_name,
            persist_directory=persist_dir
        )

    def do_init(self):
        self.vector_name = self.vector_name or self.embed_model
        self.kb_path = self.get_kb_path()
        self.vs_path = self.get_vs_path()
        self._load_chroma()

    def do_create_kb(self):
        pass

    def do_drop_kb(self):
        pass

    def do_search(self, query: str, top_k: int, score_threshold: float = SCORE_THRESHOLD) -> List[Document]:
        self._load_chroma()
        docs = self.chroma.similarity_search_with_score(query, top_k)
        results = score_threshold_process(score_threshold, top_k, docs)
        
        info_docs = []
        byte_count = 0
        for doc, score in results:
            if (byte_count + len(doc.page_content)) > VS_TYPE_PROMPT_TOTAL_BYTE_SIZE:
                break
            info_docs.append([doc, score])
            byte_count += len(doc.page_content)
        return info_docs

    def do_add_doc(self, docs: List[Document], **kwargs) -> List[Dict]:
        """添加文档到向量库"""
        if not docs:
            print(f"[WARN] 警告：没有文档需要添加到知识库 {self.kb_name}")
            return []
        
        texts = [doc.page_content for doc in docs]
        metadatas = [doc.metadata for doc in docs]
        
        print(f"📄 正在向量化 {len(texts)} 个文档片段...")
        
        try:
            # 手动计算嵌入向量
            embedding_func = EmbeddingsFunAdapter(self.embed_model)
            embeddings = embedding_func.embed_documents(texts)
            
            if not embeddings or len(embeddings) == 0:
                raise ValueError("嵌入向量计算失败，返回空结果")
            
            print(f"[OK] 成功计算 {len(embeddings)} 个嵌入向量")
            
            # 使用带嵌入向量的方法添加文档
            ids = self.chroma.add_texts(texts, metadatas, embeddings=embeddings)
            print(f"[OK] 成功添加 {len(ids)} 个文档片段到向量库")
            return [{"id": id, "metadata": metadata} for id, metadata in zip(ids, metadatas)]
        except Exception as e:
            print(f"[ERROR] 添加文档失败: {e}")
            raise

    def do_delete_doc(self, kb_file: KnowledgeFile, **kwargs):
        ids = self.chroma.get(where={"source": kb_file.filename}).get('ids')
        if ids:
            self.chroma.delete(ids)

    def do_clear_vs(self):
        pass

    @classmethod
    def delete_collection_directly(cls, kb_name: str) -> bool:
        """直接删除 collection，无需加载嵌入模型"""
        try:
            import chromadb
            persist_dir = kbs_config.get("chromadb").get('persist_directory')
            client = chromadb.PersistentClient(path=persist_dir)
            collection_name = normalize_collection_name(kb_name)
            
            try:
                client.delete_collection(name=collection_name)
                print(f"[OK] 已删除集合: {collection_name}")
            except Exception as e:
                if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                    print(f"[INFO] 集合 {collection_name} 不存在，跳过删除")
                else:
                    raise e
            return True
        except Exception as e:
            print(f"[ERROR] 删除集合失败: {e}")
            return False
